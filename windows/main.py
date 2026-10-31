"""入口：先重定向标准流，再加载界面（windowed exe 下 stdout 为 None）。"""
from __future__ import annotations

import sys


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> int:
    _enable_dpi_awareness()

    from app import runtime

    runtime.bootstrap()

    if "--selftest" in sys.argv:
        from app.selftest import run

        return run()

    from app.ui.main_window import App

    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
