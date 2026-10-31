"""开发用：用假流水线跑一遍 UI 事件流，检查任务列表 / 进度 / 日志联动。"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JMCLIENT_HOME", tempfile.mkdtemp(prefix="jmui_"))

from app import runtime  # noqa: E402

runtime.bootstrap()

import app.ui.main_window as mw  # noqa: E402
from tools.shot import capture  # noqa: E402


class FakePipeline:
    def __init__(self, cfg, emit, history=None):
        self.emit = emit
        self.cfg = cfg
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self, ids):
        for index, jm_id in enumerate(ids):
            self.emit({"type": "task", "jm_id": jm_id, "status": "下载中",
                       "title": f"示例标题 {jm_id}", "progress": 0.2, "detail": "8/35 页"})
            time.sleep(0.05)
            self.emit({"type": "task", "jm_id": jm_id, "status": "打包 ZIP", "progress": 0.78})
            time.sleep(0.05)
            self.emit({"type": "task", "jm_id": jm_id, "status": "生成 PDF", "progress": 0.95,
                       "detail": "35/35 页"})
            time.sleep(0.05)
            self.emit({"type": "task", "jm_id": jm_id, "status": "完成", "progress": 1.0,
                       "detail": "35 页"})
            self.emit({"type": "overall", "done": index + 1, "total": len(ids)})
        runtime.log_line("假流水线：全部完成")
        return {"total": len(ids), "ok": len(ids), "fail": 0, "skip": 0,
                "cancelled": False, "seconds": 1.2, "last_pdf": ""}


def main() -> int:
    mw.Pipeline = FakePipeline
    app = mw.App()
    app.input.set("jm54747电梯（极品）\njm28650体育用具储藏室（极品）\n47228，118983，152470")
    app._auto_parse()
    app._start()
    for _ in range(120):
        app.update()
        time.sleep(0.02)
    app.update()
    capture(int(app.winfo_id())).save(ROOT / "_ui_running.png")
    print("running state:", app.running, "| overall:", app.overall_label.cget("text"))
    print("rows:", [app.task_tree.item(i, "values") for i in app.task_tree.get_children()][:3])
    app.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
