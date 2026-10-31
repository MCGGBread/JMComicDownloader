"""爬取流水线：下载图片 → 打包 ZIP → 解包 → 合成 PDF。"""
from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
import zipfile
from pathlib import Path

import jmcomic

from . import config as config_mod
from . import fsutil, runtime
from .history import History
from .pdf import build_pdf


class Cancelled(Exception):
    pass


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


class HookDownloader(jmcomic.JmDownloader):
    """带进度回调的下载器。"""

    def __init__(self, option, emit, jm_id, cancel_event):
        super().__init__(option)
        self._emit = emit
        self._jm_id = jm_id
        self._cancel = cancel_event
        self._lock = threading.Lock()
        self.done_images = 0
        self.total_images = 0
        self._last_emit = 0.0
        self.album = None

    def before_album(self, album):
        super().before_album(album)
        self.album = album
        total = 0
        try:
            total = int(getattr(album, "page_count", 0) or 0)
        except Exception:
            total = 0
        if not total:
            try:
                total = sum(len(photo) for photo in album)
            except Exception:
                total = 0
        self.total_images = total
        self._emit({
            "type": "task",
            "jm_id": self._jm_id,
            "status": "下载中",
            "title": getattr(album, "title", "") or "",
            "progress": 0.0,
            "detail": f"共 {total} 页" if total else "",
        })

    def after_image(self, image, img_save_path):
        super().after_image(image, img_save_path)
        with self._lock:
            self.done_images += 1
            done = self.done_images
            total = self.total_images
            now = time.time()
            if now - self._last_emit < 0.15 and (total == 0 or done < total):
                return
            self._last_emit = now
        ratio = (done / total) if total else 0.0
        self._emit({
            "type": "task",
            "jm_id": self._jm_id,
            "status": "下载中",
            "progress": min(0.99, ratio) * 0.75,
            "detail": f"{done}/{total} 页" if total else f"{done} 页",
        })


class Pipeline:
    def __init__(self, cfg: dict, emit, history: History | None = None):
        self.cfg = config_mod.sanitize(cfg)
        self.emit = emit
        self.cancel_event = threading.Event()
        self.control = jmcomic.DownloadControl()
        self.layout = config_mod.storage_layout(self.cfg)
        self.history = history or History()
        self._options: dict[str, object] = {}
        self.last_pdf: str = ""

    # ------------------------------------------------------------------ #
    def cancel(self) -> None:
        self.cancel_event.set()
        try:
            self.control.cancel("用户取消")
        except Exception:
            pass

    def _cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def _get_option(self, impl: str):
        if impl not in self._options:
            option_file = config_mod.build_option(self.cfg, impl)
            self._options[impl] = jmcomic.create_option_by_file(str(option_file))
        return self._options[impl]

    def run_one(self, jm_id: str) -> dict:
        """处理单个番号（供界面动态队列使用）。失败抛异常，取消抛 Cancelled。"""
        if self._cancelled():
            raise Cancelled()
        return self._process(str(jm_id))

    # ------------------------------------------------------------------ #
    def run(self, ids: list[str]) -> dict:
        ids = [str(i) for i in ids]
        total = len(ids)
        ok = fail = skip = 0
        started = time.time()
        self.emit({"type": "overall", "done": 0, "total": total})
        runtime.log_line(f"开始任务：共 {total} 个番号｜实现 {self.cfg['client_impl']}｜存储 {self.layout['root']}")

        for index, jm_id in enumerate(ids, start=1):
            if self._cancelled():
                break
            self.emit({"type": "task", "jm_id": jm_id, "status": "准备", "progress": 0.0})

            if self.cfg["skip_crawled"] and self.history.has(jm_id):
                skip += 1
                self.emit({"type": "task", "jm_id": jm_id, "status": "跳过", "progress": 1.0,
                           "detail": "历史已存在"})
                runtime.log_line(f"JM{jm_id} 已爬取过，跳过")
                self.emit({"type": "overall", "done": index, "total": total})
                continue

            try:
                record = self._process(jm_id)
                ok += 1
                self.emit({
                    "type": "task",
                    "jm_id": jm_id,
                    "status": "完成",
                    "title": record.get("title", ""),
                    "progress": 1.0,
                    "detail": f"{record.get('pages', 0)} 页",
                    "pdf": record.get("pdf", ""),
                })
                runtime.log_line(
                    f"JM{jm_id} 完成：{record.get('pages', 0)} 页 → {record.get('pdf', '')}"
                )
            except Cancelled:
                self.emit({"type": "task", "jm_id": jm_id, "status": "已取消", "detail": "用户停止"})
                break
            except Exception as e:
                fail += 1
                message = str(e) or type(e).__name__
                self.emit({"type": "task", "jm_id": jm_id, "status": "失败",
                           "detail": message[:120]})
                runtime.log_line(f"JM{jm_id} 失败：{message}")
                runtime.log_line(traceback.format_exc(limit=6), "error")
            finally:
                self.emit({"type": "overall", "done": index, "total": total})

        summary = {
            "total": total,
            "ok": ok,
            "fail": fail,
            "skip": skip,
            "cancelled": self._cancelled(),
            "seconds": round(time.time() - started, 1),
            "last_pdf": self.last_pdf,
        }
        runtime.log_line(
            f"任务结束：成功 {ok}｜失败 {fail}｜跳过 {skip}｜耗时 {summary['seconds']}s"
        )
        return summary

    # ------------------------------------------------------------------ #
    def _process(self, jm_id: str) -> dict:
        impls = [self.cfg["client_impl"]]
        if self.cfg["auto_fallback"]:
            impls.append("html" if impls[0] == "api" else "api")

        last_error: Exception | None = None
        for pos, impl in enumerate(impls):
            if self._cancelled():
                raise Cancelled()
            try:
                return self._process_once(jm_id, impl)
            except Cancelled:
                raise
            except Exception as e:
                last_error = e
                if pos + 1 < len(impls):
                    runtime.log_line(
                        f"JM{jm_id} 使用 {impl} 失败（{type(e).__name__}: {e}），尝试切换实现…",
                        "warn",
                    )
        assert last_error is not None
        raise last_error

    def _process_once(self, jm_id: str, impl: str) -> dict:
        started = time.time()
        option = self._get_option(impl)

        def factory(opt):
            return HookDownloader(opt, self.emit, jm_id, self.cancel_event)

        try:
            result = jmcomic.download_album(
                jm_id, option, downloader=factory, check_exception=False, control=self.control
            )
        except Exception as e:
            if "cancel" in type(e).__name__.lower() or self._cancelled():
                raise Cancelled(str(e))
            raise

        album = result.album
        downloader = result.downloader
        if album is None:
            raise RuntimeError("未能获取本子信息")

        title = str(getattr(album, "title", "") or f"JM{jm_id}")
        author = str(getattr(album, "author", "") or "")
        try:
            photos = len(album)
        except Exception:
            photos = 0

        album_dir = getattr(album, "save_path", None)
        if not album_dir:
            album_dir = option.dir_rule.decide_album_root_dir(album)
        album_dir = Path(album_dir)

        if getattr(downloader, "has_download_failures", False):
            runtime.log_line(f"JM{jm_id} 存在部分图片下载失败，将用已成功的图片合成", "warn")

        images = fsutil.collect_images(album_dir)
        if not images:
            raise RuntimeError("没有下载到任何图片（可能被墙、需要登录或番号不存在）")

        name = self._filename(jm_id, title, author, photos, len(images))

        # 1) 打包 ZIP
        self.emit({"type": "task", "jm_id": jm_id, "status": "打包 ZIP", "progress": 0.78,
                   "title": title})
        zip_path = self.layout["zip"] / f"{name}.zip"
        try:
            self._make_zip(album_dir, zip_path, {
                "jm_id": jm_id, "title": title, "author": author,
                "photos": photos, "pages": len(images), "impl": impl,
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception as e:
            runtime.log_line(f"ZIP 打包失败（继续直接合成 PDF）：{e}", "warn")
            zip_path = None

        # 2) 解包
        unpacked_dir = None
        source_images = images
        if zip_path is not None:
            self.emit({"type": "task", "jm_id": jm_id, "status": "解包", "progress": 0.84,
                       "title": title})
            try:
                unpacked_dir = self._unpack(zip_path, name)
                source_images = fsutil.collect_images(unpacked_dir) or images
            except Exception as e:
                runtime.log_line(f"解包失败（改用原图目录）：{e}", "warn")
                unpacked_dir = None

        # 3) 合成 PDF
        self.emit({"type": "task", "jm_id": jm_id, "status": "生成 PDF", "progress": 0.88,
                   "title": title})
        pdf_path = self.layout["pdf"] / f"{name}.pdf"

        def on_pdf_progress(done, total):
            self.emit({
                "type": "task",
                "jm_id": jm_id,
                "status": "生成 PDF",
                "progress": 0.88 + 0.11 * (done / total if total else 1),
                "title": title,
                "detail": f"{done}/{total} 页",
            })

        def on_skip(path, error):
            runtime.log_line(f"跳过损坏图片 {Path(path).name}：{error}", "warn")

        pdf_path, pages = build_pdf(
            source_images,
            pdf_path,
            quality=int(self.cfg["pdf_quality"]),
            max_width=int(self.cfg["pdf_max_width"]),
            title=f"JM{jm_id} {title}".strip(),
            on_progress=on_pdf_progress,
            on_skip=on_skip,
        )

        record = {
            "jm_id": jm_id,
            "title": title,
            "author": author,
            "photos": photos,
            "pages": pages,
            "impl": impl,
            "pdf": self.history.rel(pdf_path),
            "zip": self.history.rel(zip_path) if zip_path else "",
            "images_dir": self.history.rel(album_dir) if self.cfg["keep_images"] else "",
            "size": pdf_path.stat().st_size if pdf_path.exists() else 0,
            "duration": round(time.time() - started, 1),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.history.upsert(record)
        self.last_pdf = str(pdf_path)

        self._cleanup(album_dir, unpacked_dir, zip_path)
        return record

    # ------------------------------------------------------------------ #
    def _filename(self, jm_id, title, author, photos, pages) -> str:
        mapping = {
            "id": jm_id,
            "title": title,
            "author": author,
            "photos": photos,
            "pages": pages,
        }
        template = self.cfg["filename_template"]
        try:
            raw = template.format_map(_SafeDict(mapping))
        except Exception:
            raw = f"JM{jm_id} {title}"
        name = fsutil.safe_filename(raw)
        if not name or name.lower() in ("jm", "untitled"):
            name = f"JM{jm_id}"
        return name

    def _make_zip(self, album_dir: Path, zip_path: Path, info: dict) -> None:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        if zip_path.exists():
            zip_path.unlink()
        tmp = zip_path.with_name(zip_path.name + ".part")
        files = sorted(
            (p for p in album_dir.rglob("*") if p.is_file()),
            key=lambda p: fsutil.natural_key(str(p.relative_to(album_dir)).replace("\\", "/")),
        )
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for file in files:
                zf.write(file, file.relative_to(album_dir).as_posix())
            zf.writestr("_info.json", json.dumps(info, ensure_ascii=False, indent=2))
        tmp.replace(zip_path)

    def _unpack(self, zip_path: Path, name: str) -> Path:
        target = self.layout["unpacked"] / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                dest = (target / member.filename).resolve()
                if not fsutil.is_within(dest, target):
                    continue
                zf.extract(member, target)
        return target

    def _cleanup(self, album_dir: Path, unpacked_dir: Path | None, zip_path: Path | None) -> None:
        if not self.cfg["keep_images"] and fsutil.is_within(album_dir, self.layout["images"]):
            shutil.rmtree(album_dir, ignore_errors=True)
        if unpacked_dir and not self.cfg["keep_unpacked"] and fsutil.is_within(
            unpacked_dir, self.layout["unpacked"]
        ):
            shutil.rmtree(unpacked_dir, ignore_errors=True)
        if zip_path and not self.cfg["keep_zip"] and zip_path.exists():
            try:
                zip_path.unlink()
            except Exception:
                pass
