"""开发用：验证「关闭应用后任务列表可见 + 未完成自动续跑」。"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HOME = tempfile.mkdtemp(prefix="jmresume2_")
os.environ["JMCLIENT_HOME"] = HOME

from app import runtime  # noqa: E402

runtime.bootstrap()

import app.ui.main_window as mw  # noqa: E402
from app import queue_state  # noqa: E402
from app.history import History  # noqa: E402


class FakePipeline:
    def __init__(self, cfg, emit, history=None):
        self.cfg = cfg
        self.emit = emit
        self.history = history or History()
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run_one(self, jm_id):
        if self.cancelled:
            raise mw.Cancelled()
        self.emit({"type": "task", "jm_id": jm_id, "status": "下载中",
                   "title": f"示例 {jm_id}", "progress": 0.4, "detail": "12/30 页"})
        for _ in range(10):
            if self.cancelled:
                raise mw.Cancelled()
            time.sleep(0.05)
        self.emit({"type": "task", "jm_id": jm_id, "status": "完成",
                   "progress": 1.0, "detail": "30 页"})
        return {"jm_id": jm_id, "title": f"示例 {jm_id}", "pages": 30, "pdf": ""}


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        try:
            app.update()
        except Exception:
            return
        time.sleep(0.02)


def rows(app):
    return [
        (app.task_tree.item(i, "values")[0], app.task_tree.item(i, "values")[2])
        for i in app.task_tree.get_children()
    ]


def close(app):
    app._on_close()


def main() -> int:
    mw.Pipeline = FakePipeline
    mw.messagebox.askyesno = lambda *a, **k: True
    mw.messagebox.showinfo = lambda *a, **k: None
    mw.messagebox.showwarning = lambda *a, **k: None

    print("---- A. 跑一半直接关窗口 ----")
    app = mw.App()
    app.input.set("jm4001 jm4002 jm4003")
    app._submit()
    pump(app, 0.3)
    print("运行中:", app.running, rows(app))
    close(app)
    saved = queue_state.load()
    print("关闭后保存:", [(t["jm_id"], t["status"]) for t in saved])

    app2 = mw.App()
    pump(app2, 0.2)
    print("重开可见:", rows(app2), "| 待继续:", len(app2._restored))
    for _ in range(400):
        pump(app2, 0.05)
        if not app2.running and not app2._restored:
            break
    print("续跑结束:", rows(app2), "| overall:", app2.overall_label.cget("text"))

    print("---- B. 全部完成后关闭 ----")
    close(app2)
    print("完成后保存:", [(t["jm_id"], t["status"]) for t in queue_state.load()])
    app3 = mw.App()
    pump(app3, 0.3)
    print("重开可见:", rows(app3), "| 待继续:", len(app3._restored),
          "| running:", app3.running)

    print("---- C. 停止后关闭 ----")
    app3.input.set("jm5001 jm5002")
    app3._submit()
    pump(app3, 0.3)
    app3._stop()
    for _ in range(200):
        pump(app3, 0.05)
        if not app3.running:
            break
    print("停止后:", rows(app3))
    close(app3)
    app4 = mw.App()
    pump(app4, 0.2)
    print("重开可见:", rows(app4), "| 待继续:", len(app4._restored))

    print("---- D. 清空列表 ----")
    app4._clear_task_list()
    pump(app4, 0.2)
    print("清空后行数:", len(app4.task_tree.get_children()),
          "| 队列文件:", queue_state.path().exists())
    close(app4)
    app5 = mw.App()
    pump(app5, 0.2)
    print("再重开行数:", len(app5.task_tree.get_children()),
          "| 队列文件:", queue_state.path().exists())
    app5.destroy()
    print("HOME", HOME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
