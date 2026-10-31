"""运行时基础：便携目录、日志重定向、单例锁。

所有用户数据都放在 exe 同级目录下：
    <exe目录>/
        config/            配置（config.json / option_*.yml / crawled_history.json）
        crawled_data/      下载产物（images / zip / unpacked / pdf）
        logs/              app.log
如果 exe 所在目录不可写（例如放在 Program Files），自动回退到 %APPDATA%\\JMComicClient。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

APP_ID = "JMComicClient"
APP_NAME = "JMComic 客户端"
VERSION = "1.4.1"

_LOCK = threading.Lock()
_LOG_PATH: Path | None = None
_UI_SINK = None
_ORIG_STDOUT = sys.stdout
_ORIG_STDERR = sys.stderr


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """exe 所在目录（源码运行时为项目根目录）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


_HOME: Path | None = None


def home() -> Path:
    """数据根目录。"""
    global _HOME
    if _HOME is not None:
        return _HOME

    env = os.environ.get("JMCLIENT_HOME")
    if env:
        p = Path(env).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        _HOME = p
        return p

    base = app_dir()
    if _writable(base / "config"):
        _HOME = base
    else:
        fallback = Path(os.environ.get("APPDATA") or Path.home()) / APP_ID
        fallback.mkdir(parents=True, exist_ok=True)
        _HOME = fallback
    return _HOME


def config_dir() -> Path:
    p = home() / "config"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_dir() -> Path:
    p = home() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_data_dir() -> Path:
    p = home() / "crawled_data"
    p.mkdir(parents=True, exist_ok=True)
    return p


# --------------------------------------------------------------------------- #
# 日志
# --------------------------------------------------------------------------- #
def set_ui_sink(func) -> None:
    """注册 UI 日志回调（会在任意线程被调用，回调内部需自行保证线程安全）。"""
    global _UI_SINK
    _UI_SINK = func


def log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        _LOG_PATH = log_dir() / "app.log"
    return _LOG_PATH


def _rotate_if_needed(path: Path, limit: int = 3 * 1024 * 1024) -> None:
    try:
        if path.exists() and path.stat().st_size > limit:
            backup = path.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            path.rename(backup)
    except Exception:
        pass


def log_line(text: str, level: str = "info") -> None:
    text = str(text).rstrip("\r\n")
    if not text:
        return
    stamp = time.strftime("%H:%M:%S")
    line = f"[{stamp}] {text}"
    with _LOCK:
        try:
            _rotate_if_needed(log_path())
            with open(log_path(), "a", encoding="utf-8") as fp:
                fp.write(f"{time.strftime('%Y-%m-%d')} {line}\n")
        except Exception:
            pass
    if _UI_SINK is not None:
        try:
            _UI_SINK(level, line)
        except Exception:
            pass


class _StreamProxy:
    """把 stdout/stderr 重定向到日志文件 + UI（打包成 windowed exe 后 stdout 为 None）。"""

    def __init__(self, name: str):
        self.name = name
        self._buf = ""

    def write(self, data):
        if not data:
            return 0
        if not isinstance(data, str):
            data = str(data)
        # 开发模式下同时保留控制台输出
        if not is_frozen() and _ORIG_STDOUT is not None:
            try:
                _ORIG_STDOUT.write(data)
            except Exception:
                pass
        self._buf += data
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip()
            if line:
                log_line(line, "raw")
        return len(data)

    def flush(self):
        if self._buf.strip():
            line, self._buf = self._buf, ""
            log_line(line.strip(), "raw")

    def isatty(self):
        return False

    @property
    def encoding(self):
        return "utf-8"

    def fileno(self):
        raise OSError("stream has no file descriptor")


def bootstrap() -> None:
    """重定向标准流并确保目录存在。必须在 import jmcomic 之前调用。"""
    for d in (config_dir(), log_dir(), default_data_dir()):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    if isinstance(sys.stdout, _StreamProxy) and isinstance(sys.stderr, _StreamProxy):
        return
    if sys.stdout is None or sys.stdout is _ORIG_STDOUT:
        sys.stdout = _StreamProxy("stdout")
    if sys.stderr is None or sys.stderr is _ORIG_STDERR:
        sys.stderr = _StreamProxy("stderr")


def install_jmcomic_logger() -> None:
    """接管 jmcomic 的日志执行器，输出到文件与 UI。"""
    try:
        from jmcomic import JmModuleConfig
    except Exception:
        return

    def _executor(topic, msg, e=None):
        if isinstance(msg, BaseException):
            e, msg = msg, str(msg)
        prefix = f"【{topic}】" if topic else ""
        log_line(f"{prefix}{msg}")
        if e is not None:
            log_line(f"{prefix}{type(e).__name__}: {e}", "error")

    JmModuleConfig.EXECUTOR_LOG = _executor


def open_path(path) -> None:
    """用系统默认程序打开文件/文件夹。"""
    p = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(p)  # noqa: S606
        else:
            import subprocess

            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", p])
    except Exception as e:
        log_line(f"打开失败 {p}: {e}", "error")
