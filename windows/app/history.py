"""爬取历史（用户爬过的 JM 番号）。"""
from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

from . import runtime


class History:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else runtime.config_dir() / "crawled_history.json"
        self._data: dict[str, dict] = {}
        self.load()

    # ------------------------------------------------------------------ #
    def load(self) -> None:
        self._data = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            albums = raw.get("albums", raw) if isinstance(raw, dict) else {}
            if isinstance(albums, dict):
                self._data = {str(k): v for k, v in albums.items() if isinstance(v, dict)}
        except Exception as e:
            runtime.log_line(f"历史记录读取失败：{e}", "warn")

    def save(self) -> None:
        payload = {"version": 1, "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "albums": self._data}
        tmp = self.path.with_suffix(".json.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception as e:
            runtime.log_line(f"历史记录保存失败：{e}", "error")

    # ------------------------------------------------------------------ #
    def all(self) -> list[dict]:
        return sorted(self._data.values(), key=lambda r: str(r.get("time", "")), reverse=True)

    def get(self, jm_id) -> dict | None:
        return self._data.get(str(jm_id))

    def has(self, jm_id) -> bool:
        return str(jm_id) in self._data

    def upsert(self, record: dict) -> None:
        jm_id = str(record.get("jm_id", ""))
        if not jm_id:
            return
        old = self._data.get(jm_id, {})
        merged = {**old, **record}
        merged["crawl_count"] = int(old.get("crawl_count", 0)) + 1
        merged.setdefault("first_time", record.get("time"))
        self._data[jm_id] = merged
        self.save()

    def remove(self, jm_id) -> None:
        if str(jm_id) in self._data:
            self._data.pop(str(jm_id), None)
            self.save()

    def clear(self) -> None:
        self._data.clear()
        self.save()

    def export_csv(self, target) -> int:
        rows = self.all()
        with open(target, "w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["番号", "标题", "作者", "页数", "章节数", "完成时间", "PDF 路径"])
            for r in rows:
                writer.writerow([
                    r.get("jm_id", ""),
                    r.get("title", ""),
                    r.get("author", ""),
                    r.get("pages", ""),
                    r.get("photos", ""),
                    r.get("time", ""),
                    self.resolve(r.get("pdf", "")),
                ])
        return len(rows)

    # ------------------------------------------------------------------ #
    def rel(self, path) -> str:
        """尽量存相对路径，整个文件夹搬走也不失效。"""
        if not path:
            return ""
        try:
            p = Path(path).resolve()
            return str(p.relative_to(runtime.home()))
        except Exception:
            return str(path)

    def resolve(self, path) -> str:
        if not path:
            return ""
        p = Path(str(path))
        if p.is_absolute():
            return str(p)
        return str((runtime.home() / p).resolve())
