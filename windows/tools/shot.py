"""开发用：把 Tk 窗口自身渲染成 PNG（不依赖屏幕可见，锁屏也能截）。"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import runtime  # noqa: E402

runtime.bootstrap()

from app.ui.main_window import App  # noqa: E402

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def capture(hwnd: int) -> Image.Image:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetWindowDC(hwnd)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(memdc, bitmap)
    user32.PrintWindow(hwnd, memdc, 2)

    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0

    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memdc, bitmap, 0, height, buffer, ctypes.byref(info), 0)

    image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1).convert("RGB")
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)
    return image


def main() -> int:
    page = sys.argv[1] if len(sys.argv) > 1 else "crawl"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / f"_ui_{page}.png"

    app = App()
    if page != "crawl":
        app._show(page)
    app.update_idletasks()
    app.update()
    if len(sys.argv) > 3:
        try:
            app.settings_scroll.canvas.yview_moveto(float(sys.argv[3]))
        except Exception:
            pass
        app.update_idletasks()
        app.update()

    hwnd = int(app.winfo_id())
    image = capture(hwnd)
    image.save(out)
    print(f"saved {out} {image.size}")
    app.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
