"""开发用：按 Java 版计划实现的参考客户端，用来验证协议理解是否正确。

对比对象：jmcomic 自己下载并还原的图片。
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from Crypto.Cipher import AES
from PIL import Image, ImageChops

UA = ("Mozilla/5.0 (Linux; Android 9; V1938CT Build/PQ3A.190705.11211812; wv) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 "
      "Safari/537.36")
SECRET = "185Hcomic3PAPP7R"
APP_VER = "2.1.12"
API_DOMAINS = ["www.cdnhjk.net", "www.cdnutc.cc", "www.cdngwc.net", "www.cdngwc.club"]
IMG_DOMAINS = [
    "cdn-msp.jmapiproxy1.cc", "cdn-msp.jmapiproxy2.cc", "cdn-msp2.jmapiproxy2.cc",
    "cdn-msp3.jmapiproxy2.cc", "cdn-msp.jmapinodeudzn.net", "cdn-msp3.jmapinodeudzn.net",
]
SCRAMBLE_268850 = 268850
SCRAMBLE_421926 = 421926
SCRAMBLE_220980 = 220980


def md5hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _get(url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def api_get(path: str, params: dict) -> dict:
    ts = str(int(time.time()))
    headers = {
        "user-agent": UA,
        "token": md5hex(ts + SECRET),
        "tokenparam": f"{ts},{APP_VER}",
        "Accept-Encoding": "identity",
    }
    last = None
    for attempt in range(3):
        for domain in API_DOMAINS:
            url = f"https://{domain}{path}?{urllib.parse.urlencode(params)}"
            try:
                raw = _get(url, headers)
                obj = json.loads(raw)
                if obj.get("code") != 200:
                    raise RuntimeError(f"code={obj.get('code')} msg={obj.get('msg')}")
                data = obj["data"]
                key = md5hex(ts + SECRET).encode()
                plain = AES.new(key, AES.MODE_ECB).decrypt(base64.b64decode(data))
                plain = plain[: -plain[-1]]
                return json.loads(plain.decode("utf-8"))
            except Exception as e:  # noqa: BLE001
                last = e
                continue
        time.sleep(0.6)
    raise RuntimeError(f"API 全部失败: {last}")


def get_scramble_id(photo_id: str) -> int:
    ts = str(int(time.time()))
    headers = {
        "user-agent": UA,
        "token": md5hex(ts + SECRET),
        "tokenparam": f"{ts},{APP_VER}",
        "Accept-Encoding": "identity",
    }
    params = {"id": photo_id, "mode": "vertical", "page": "0",
              "app_img_shunt": "1", "express": "off", "v": ts}
    for domain in API_DOMAINS:
        url = f"https://{domain}/chapter_view_template?{urllib.parse.urlencode(params)}"
        try:
            text = _get(url, headers).decode("utf-8", "ignore")
            m = re.search(r"var scramble_id = (\d+);", text)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    return SCRAMBLE_220980


def decode_num(scramble_id: int, aid: int, filename: str) -> int:
    if aid < scramble_id:
        return 0
    if aid < SCRAMBLE_268850:
        return 10
    x = 10 if aid < SCRAMBLE_421926 else 8
    digest = hashlib.md5(f"{aid}{filename}".encode()).hexdigest()
    return (ord(digest[-1]) % x) * 2 + 2


def decode_image(raw: bytes, num: int) -> Image.Image:
    src = Image.open(__import__("io").BytesIO(raw)).convert("RGB")
    if num == 0:
        return src
    w, h = src.size
    out = Image.new("RGB", (w, h))
    over = h % num
    for i in range(num):
        move = h // num
        y_src = h - move * (i + 1) - over
        y_dst = move * i
        if i == 0:
            move += over
        else:
            y_dst += over
        out.paste(src.crop((0, y_src, w, y_src + move)), (0, y_dst, w, y_dst + move))
    return out


def download_image(photo_id: str, filename: str) -> bytes:
    headers = {
        "user-agent": UA,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "X-Requested-With": "com.JMComic3.app",
        "Referer": f"https://{API_DOMAINS[0]}",
        "Accept-Encoding": "identity",
    }
    domains = IMG_DOMAINS[:]
    random.shuffle(domains)
    last = None
    for domain in domains:
        url = f"https://{domain}/media/photos/{photo_id}/{filename}"
        try:
            return _get(url, headers, timeout=40)
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"图片下载失败: {last}")


def main() -> int:
    import sys

    jm_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    aid = sys.argv[2] if len(sys.argv) > 2 else "54747"

    album = api_get("/album", {"id": aid})
    print("album:", album["id"], "photos:", album.get("total_photos"),
          "series_id:", album.get("series_id"), "name_len:", len(album.get("name", "")))

    series_id = str(album.get("series_id") or "")
    photo_id = series_id if series_id not in ("", "0") else aid
    chapter = api_get("/chapter", {"id": photo_id})
    images = chapter["images"]
    print("chapter:", chapter["id"], "images:", len(images), "first:", images[0])

    scramble = get_scramble_id(photo_id)
    print("scramble_id:", scramble)
    num = decode_num(scramble, int(photo_id), images[0])
    print("decode num:", num)

    raw = download_image(photo_id, images[0])
    print("raw bytes:", len(raw))
    decoded = decode_image(raw, num)
    out = Path("_proto_decoded.jpg")
    decoded.save(out, quality=92)
    print("decoded:", decoded.size, "->", out)

    if jm_dir and jm_dir.exists():
        refs = sorted(jm_dir.rglob(images[0].rsplit(".", 1)[0] + ".jpg"))
        if refs:
            ref = Image.open(refs[0]).convert("RGB")
            if ref.size != decoded.size:
                print("尺寸不一致:", ref.size, decoded.size)
            else:
                diff = ImageChops.difference(ref, decoded)
                stat = diff.convert("L").resize((64, 64))
                pixels = list(stat.getdata())
                print("平均差异(缩小后):", round(sum(pixels) / len(pixels), 2),
                      "最大:", max(pixels))
        else:
            print("没找到参考图")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
