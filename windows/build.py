"""打包为单文件 exe（PyInstaller）。

用法： .venv\\Scripts\\python.exe build.py
产物： dist\\JMComicClient.exe
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
NAME = "JMComicClient"
VERSION = "1.4.1"

VERSION_FILE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 4, 1, 0),
    prodvers=(1, 4, 1, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404B0', [
        StringStruct('CompanyName', 'JMComic Client'),
        StringStruct('FileDescription', 'JMComic 番号下载 / PDF 合成客户端'),
        StringStruct('FileVersion', '1.4.1'),
        StringStruct('InternalName', 'JMComicClient'),
        StringStruct('OriginalFilename', 'JMComicClient.exe'),
        StringStruct('ProductName', 'JMComic 客户端'),
        StringStruct('ProductVersion', '1.4.1')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def make_icon() -> Path:
    from PIL import Image, ImageDraw, ImageFont

    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        ratio = y / size
        draw.line(
            [(0, y), (size, y)],
            fill=(
                int(255 * (1 - ratio) + 206 * ratio),
                int(70 * (1 - ratio) + 38 * ratio),
                int(102 * (1 - ratio) + 88 * ratio),
                255,
            ),
        )

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=58, fill=255)
    image.putalpha(mask)

    font = None
    for candidate in ("msyhbd.ttc", "arialbd.ttf", "segoeuib.ttf", "segoeui.ttf"):
        try:
            font = ImageFont.truetype(candidate, 108)
            break
        except Exception:
            continue
    if font is not None:
        text = "JM"
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(
            ((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1] - 6),
            text,
            font=font,
            fill=(255, 255, 255, 255),
        )

    BUILD.mkdir(parents=True, exist_ok=True)
    icon = BUILD / "icon.ico"
    image.save(
        icon,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return icon


def backup_user_data() -> Path | None:
    """打包前备份 exe 同级的 config（含爬取历史），避免覆盖丢数据。"""
    source = DIST / "config"
    if not source.exists():
        return None
    target = ROOT / "backups" / f"config-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
    except Exception as e:
        print(f"[warn] 配置备份失败：{e}")
        return None

    # 只保留最近 10 份
    backups = sorted((ROOT / "backups").glob("config-*"))
    for old in backups[:-10]:
        shutil.rmtree(old, ignore_errors=True)
    return target


def main() -> int:
    BUILD.mkdir(parents=True, exist_ok=True)
    backup = backup_user_data()
    if backup:
        print(f"已备份配置：{backup}")
    else:
        print("未发现 dist/config，跳过备份")
    icon = make_icon()
    version_file = BUILD / "version_info.txt"
    version_file.write_text(VERSION_FILE, encoding="utf-8")

    if (DIST / f"{NAME}.exe").exists():
        (DIST / f"{NAME}.exe").unlink()

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", NAME,
        "--icon", str(icon),
        "--version-file", str(version_file),
        "--collect-all", "jmcomic",
        "--collect-all", "curl_cffi",
        "--collect-all", "certifi",
        "--exclude-module", "numpy",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pandas",
        "--exclude-module", "scipy",
        "--exclude-module", "pypdf",
        "--exclude-module", "PyInstaller",
        "--exclude-module", "tkinter.test",
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyi"),
        "--specpath", str(BUILD),
        str(ROOT / "main.py"),
    ]
    print("$", " ".join(args))
    code = subprocess.call(args, cwd=str(ROOT))
    if code != 0:
        print("打包失败，退出码", code)
        return code

    exe = DIST / f"{NAME}.exe"
    if exe.exists():
        print(f"\n完成：{exe}  ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
