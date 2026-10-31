"""自检：番号解析 / 配置生成 / PDF 合成 / 依赖导入。

打包后的 exe 可执行：JMComicClient.exe --selftest
"""
from __future__ import annotations

import re
import shutil
import sys
import traceback

from . import config as config_mod
from . import parser, runtime
from .pdf import build_pdf

CASES = [
    ("jm54747电梯（极品）", ["54747"]),
    ("jm28650体育用具储藏室（极品）", ["28650"]),
    ("47228，118983，152470，197393", ["47228", "118983", "152470", "197393"]),
    ("JM-54747 / jm 28650 / [JM100]", ["54747", "28650", "100"]),
    ("https://18comic.vip/album/54747/", ["54747"]),
    ("54747 电梯", ["54747"]),
    ("2024年10月 第2话 12345", ["12345"]),
    ("jm54747 jm54747", ["54747"]),
    ("47228,118983,152470", ["47228", "118983", "152470"]),
    ("JM54747\nJM28650", ["54747", "28650"]),
    # 紧贴括号注释的连写形式
    ("142176(母子大车)404477(长篇大车，经典作品)404098(狐娘)431896(熟女)",
     ["142176", "404477", "404098", "431896"]),
    ("142176（母子大车）404477", ["142176", "404477"]),
    ("142176【母子大车】404477", ["142176", "404477"]),
    ("推荐142176(母子大车)", ["142176"]),
    ("142176(母子大车),404477", ["142176", "404477"]),
    ("jm54747电梯（极品）jm28650体育用具储藏室（极品）", ["54747", "28650"]),
    # h 前缀（合集/对照表常见写法）
    ("h540931(瞬)-h499835(幼瞬)✔️", ["540931", "499835"]),
    ("h486483(日奈)-h479035(日奈)", ["486483", "479035"]),
    ("500703(柚子)-h559091(柚子)", ["500703", "559091"]),
    ("h568725(心奈)", ["568725"]),
    # 分类标题里的计数不能被当成番号
    ("【格黑娜】22\n【千年】36", []),
]


def _check_parser() -> list[str]:
    errors = []
    for text, expected in CASES:
        got = parser.parse_ids(text)
        if got != expected:
            errors.append(f"解析失败：{text!r} → {got}，期望 {expected}")
    for noise in (
        "2024年10月 第2话",
        "18comic.vip",
        "2024-10-26 10:30 版本2.5.36 (C88)",
        "h264 编码 H100 显卡 4h30m",
    ):
        if parser.parse_ids(noise):
            errors.append(f"普通数字被误识别为番号：{noise!r} → {parser.parse_ids(noise)}")
    return errors


def _check_config() -> list[str]:
    errors = []
    try:
        cfg = config_mod.sanitize(config_mod.load())
        path = config_mod.build_option(cfg)
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data["client"]["impl"] != cfg["client_impl"]:
            errors.append("option.yml 的 client.impl 不正确")
        if "dir_rule" not in data or "base_dir" not in data["dir_rule"]:
            errors.append("option.yml 缺少 dir_rule.base_dir")

        import jmcomic

        option = jmcomic.create_option_by_file(str(path))
        if option is None:
            errors.append("jmcomic 无法加载 option.yml")
        from .pipeline import HookDownloader  # noqa: F401

        _ = jmcomic.JmDownloader
    except Exception:
        errors.append("配置检查异常：\n" + traceback.format_exc(limit=6))
    return errors


def _check_pdf() -> list[str]:
    errors = []
    base = runtime.home() / "_selftest"
    try:
        from PIL import Image, ImageDraw

        if base.exists():
            shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True, exist_ok=True)

        paths = []
        for index, mode in enumerate(("RGB", "RGBA", "L")):
            img = Image.new("RGB", (900, 1300), (250, 250, 250))
            draw = ImageDraw.Draw(img)
            draw.rectangle([40, 40, 860, 200], fill=(255, 77, 109))
            draw.text((60, 90), f"PAGE {index + 1}", fill=(0, 0, 0))
            if mode == "RGBA":
                img = img.convert("RGBA")
                file = base / f"{index + 1:03d}.png"
            elif mode == "L":
                img = img.convert("L")
                file = base / f"{index + 1:03d}.png"
            else:
                file = base / f"{index + 1:03d}.jpg"
            img.save(file)
            paths.append(file)

        out, pages = build_pdf(paths, base / "test.pdf", quality=88, title="测试 PDF")
        raw = out.read_bytes()
        if not raw.startswith(b"%PDF"):
            errors.append("PDF 文件头不正确")
        if pages != 3:
            errors.append(f"PDF 页数不正确：{pages}")
        match = re.search(rb"/Count (\d+)", raw)
        if not match or int(match.group(1)) != 3:
            errors.append("PDF /Count 不正确")
        if b"startxref" not in raw or not raw.rstrip().endswith(b"%%EOF"):
            errors.append("PDF 尾部结构不完整")
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(out))
            if len(reader.pages) != 3:
                errors.append("pypdf 校验页数不符")
        except ImportError:
            pass
    except Exception:
        errors.append("PDF 检查异常：\n" + traceback.format_exc(limit=6))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return errors


def _check_network() -> list[str]:
    """--network 时执行：只取本子详情，不下载图片。"""
    errors = []
    try:
        import jmcomic

        cfg = config_mod.load()
        path = config_mod.build_option(cfg)
        option = jmcomic.create_option_by_file(str(path))
        album = option.new_jm_client().get_album_detail("54747")
        if album is None or str(album.id) != "54747":
            errors.append("接口返回的本子信息不正确")
        else:
            print(f"       连通正常：JM{album.id}，章节 {len(album)}，共 {getattr(album, 'page_count', '?')} 页")
    except Exception:
        errors.append("网络检查失败（可能需要代理/更换域名）：\n" + traceback.format_exc(limit=4))
    return errors


def run() -> int:
    print(f"=== {runtime.APP_NAME} 自检 v{runtime.VERSION} ===")
    print(f"frozen={runtime.is_frozen()} home={runtime.home()}")
    print(f"python={sys.version.split()[0]}")

    groups = {
        "番号解析": _check_parser(),
        "配置与依赖": _check_config(),
        "PDF 合成": _check_pdf(),
    }
    if "--network" in sys.argv:
        groups["网络连通"] = _check_network()
    failed = 0
    for name, errors in groups.items():
        if errors:
            failed += len(errors)
            print(f"[FAIL] {name}")
            for err in errors:
                print("   -", err.replace("\n", "\n     "))
        else:
            print(f"[ OK ] {name}")

    print("=== 自检通过 ===" if failed == 0 else f"=== 自检失败 {failed} 项 ===")
    return 0 if failed == 0 else 1
