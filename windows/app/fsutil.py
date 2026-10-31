"""文件相关小工具。"""
from __future__ import annotations

import re
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".jfif"}

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SPACES = re.compile(r"\s+")


def natural_key(value: str):
    """让 2.jpg 排在 10.jpg 前面。"""
    parts = re.split(r"(\d+)", str(value))
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def collect_images(root) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    files = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.stat().st_size > 0
    ]
    files.sort(key=lambda p: natural_key(str(p.relative_to(root)).replace("\\", "/")))
    return files


def safe_filename(name: str, max_len: int = 110) -> str:
    text = _ILLEGAL.sub(" ", str(name or ""))
    text = _SPACES.sub(" ", text).strip(" .")
    if len(text) > max_len:
        text = text[:max_len].rstrip(" .")
    return text or "untitled"


def is_within(child, parent) -> bool:
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except Exception:
        return False


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"
