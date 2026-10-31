"""一键发布：创建 GitHub Release 并上传 exe / apk。

用法：
    python tools/release.py v1.0.2 "修复了 xxx"
    python tools/release.py v1.0.2 --notes-file notes.md --dry-run

凭据来自 Git Credential Manager（git credential fill），无需手动填 token。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "MCGGBread/JMComicDownloader"
ASSETS = [
    ("windows/dist/JMComicClient.exe", "Windows 10/11"),
    ("android/dist/JMComicClient.apk", "Android 10+"),
]


def token() -> str:
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("拿不到 GitHub 凭据，请先执行：git push（或 git credential-manager github login）")


def api(method: str, url: str, tok: str, data=None, raw: bytes | None = None, ctype="application/json"):
    headers = {
        "Authorization": "token " + tok,
        "Accept": "application/vnd.github+json",
        "User-Agent": "jmcomic-release",
    }
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    if body is not None:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def main() -> int:
    parser = argparse.ArgumentParser(description="发布 JMComicDownloader 新版本")
    parser.add_argument("tag", help="版本号，例如 v1.0.2")
    parser.add_argument("notes", nargs="?", default="", help="更新说明（Markdown）")
    parser.add_argument("--notes-file", help="从文件读取更新说明")
    parser.add_argument("--name", help="Release 标题，默认与 tag 相同")
    parser.add_argument("--dry-run", action="store_true", help="只检查，不真正发布")
    args = parser.parse_args()

    notes = Path(args.notes_file).read_text(encoding="utf-8") if args.notes_file else args.notes
    if not notes.strip():
        notes = f"## {args.tag}\n\n详见 [README](https://github.com/{REPO}#readme)。"

    missing = [p for p, _ in ASSETS if not (ROOT / p).is_file()]
    if missing:
        raise SystemExit("缺少构建产物，请先打包：\n  " + "\n  ".join(missing))

    tok = token()
    print(f"仓库：{REPO}")
    print(f"版本：{args.tag}")
    for path, platform in ASSETS:
        size = (ROOT / path).stat().st_size
        print(f"  {platform:<12} {path}  {size / 1024 / 1024:.1f} MB")

    if args.dry_run:
        print("\n[dry-run] 检查通过，未创建 Release。")
        return 0

    status, release = api("POST", f"https://api.github.com/repos/{REPO}/releases", tok, {
        "tag_name": args.tag,
        "name": args.name or args.tag,
        "body": notes,
        "draft": False,
        "prerelease": False,
    })
    if status not in (200, 201):
        raise SystemExit(f"创建 Release 失败 {status}: {release.get('message') or release}")

    print(f"\nRelease: {release['html_url']}")
    upload_url = release["upload_url"].split("{")[0]
    for path, _ in ASSETS:
        file = ROOT / path
        status, asset = api("POST", f"{upload_url}?name={file.name}", tok,
                            raw=file.read_bytes(), ctype="application/octet-stream")
        if status not in (200, 201):
            print(f"[FAIL] {file.name}: {status} {asset.get('message') or asset}")
            continue
        print(f"[ OK ] {asset['name']}  {asset['size'] / 1024 / 1024:.1f} MB")

    print(f"\n下载直链（永远指向最新版）：")
    for path, _ in ASSETS:
        name = Path(path).name
        print(f"  https://github.com/{REPO}/releases/latest/download/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
