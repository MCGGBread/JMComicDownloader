"""开发用：验证「运行中追加任务」的队列行为。"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JMCLIENT_HOME", tempfile.mkdtemp(prefix="jmq_"))

from app import runtime  # noqa: E402

runtime.bootstrap()

import app.ui.main_window as mw  # noqa: E402
from app.history import History  # noqa: E402


class FakePipeline:
    created = 0

    def __init__(self, cfg, emit, history=None):
        FakePipeline.created += 1
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
                   "title": f"示例 {jm_id}", "progress": 0.3, "detail": "10/30 页"})
        for _ in range(12):
            if self.cancelled:
                raise mw.Cancelled()
            time.sleep(0.05)
        self.emit({"type": "task", "jm_id": jm_id, "status": "完成",
                   "progress": 1.0, "detail": "30 页"})
        return {"jm_id": jm_id, "title": f"示例 {jm_id}", "pages": 30, "pdf": ""}


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def main() -> int:
    mw.Pipeline = FakePipeline
    app = mw.App()

    # 1) 先起两个任务
    app.input.set("jm1001，jm1002")
    app._submit()
    pump(app, 0.4)
    print("started:", app.running, "| total:", app._total_added,
          "| btn:", app.btn_start.cget("text"), "| overall:", app.overall_label.cget("text"))

    # 2) 运行中追加两个（此时第一个还没跑完）
    app.input.set("jm1003(追加) jm1004")
    app._submit()
    pump(app, 0.2)
    print("after append:", app.running, "| total:", app._total_added,
          "| pending:", app.pending_ids.qsize(), "| overall:", app.overall_label.cget("text"))

    # 3) 重复追加应被忽略
    app.input.set("jm1001 jm1003")
    app._submit()
    pump(app, 0.1)
    print("after dup:", app._total_added, "| pending:", app.pending_ids.qsize())

    # 4) 等全部结束
    for _ in range(400):
        pump(app, 0.05)
        if not app.running:
            break
    rows = [app.task_tree.item(i, "values") for i in app.task_tree.get_children()]
    print("finished:", not app.running, "| overall:", app.overall_label.cget("text"))
    print("rows:", rows)
    print("pipelines created:", FakePipeline.created, "| btn:", app.btn_start.cget("text"))

    # 5) 停止测试：再起 3 个，立刻停止
    app.input.set("jm2001 jm2002 jm2003")
    app._submit()
    pump(app, 0.25)
    app._stop()
    for _ in range(200):
        pump(app, 0.05)
        if not app.running:
            break
    print("stop ->", app.running, "| status:", app.status_var.get())
    print("stop rows:", [app.task_tree.item(i, "values")[2] for i in app.task_tree.get_children()])

    app.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
