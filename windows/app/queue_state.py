"""任务队列持久化：关掉应用再打开，没跑完的任务可以接着跑。

文件放在 config/queue_state.json，只在还有未完成任务时写入；
全部结束（或用户停止）后自动清空，避免下次启动看到一堆过期任务。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import runtime

FILE_NAME = "queue_state.json"
MAX_TASKS = 2000

# 还没结束的状态（重启后需要继续）
ACTIVE_STATES = {"等待", "准备", "下载中", "打包 ZIP", "解包", "生成 PDF"}
# 已经结束的状态（重启后不再重跑）
TERMINAL_STATES = {"完成", "失败", "跳过", "已取消"}

_FIELDS = ("jm_id", "title", "status", "detail")


def path() -> Path:
    return runtime.config_dir() / FILE_NAME


def save(tasks) -> None:
    records = []
    for task in tasks:
        jm_id = str(task.get("jm_id") or "").strip()
        if not jm_id:
            continue
        records.append({
            "jm_id": jm_id,
            "title": str(task.get("title") or ""),
            "status": str(task.get("status") or "等待"),
            "detail": str(task.get("detail") or ""),
        })
        if len(records) >= MAX_TASKS:
            break

    payload = {
        "version": 1,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": records,
    }
    target = path()
    tmp = target.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
    except Exception as e:
        runtime.log_line(f"任务队列保存失败：{e}", "warn")


def load() -> list[dict]:
    target = path()
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as e:
        runtime.log_line(f"任务队列读取失败：{e}", "warn")
        return []

    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list):
        return []

    result: list[dict] = []
    seen: set[str] = set()
    for item in tasks:
        if not isinstance(item, dict):
            continue
        jm_id = str(item.get("jm_id") or "").strip()
        if not jm_id.isdigit() or jm_id in seen:
            continue
        seen.add(jm_id)
        record = {field: str(item.get(field) or "") for field in _FIELDS}
        if record["status"] not in ACTIVE_STATES | TERMINAL_STATES:
            record["status"] = "等待"
        result.append(record)
        if len(result) >= MAX_TASKS:
            break
    return result


def clear() -> None:
    try:
        path().unlink(missing_ok=True)
    except Exception:
        pass
