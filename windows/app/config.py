"""配置读写 + jmcomic option.yml 生成。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from . import runtime

CONFIG_FILE = "config.json"

DEFAULTS: dict[str, Any] = {
    # 存储
    "storage_dir": "crawled_data",
    # 网络
    "client_impl": "api",          # api | html
    "auto_fallback": True,          # 失败时自动切换另一种客户端实现
    "threads_image": 30,
    "threads_photo": 8,
    "retry_times": 5,
    "proxy": "system",              # system | none | 127.0.0.1:7890
    "cookies_avs": "",
    "domains": "",
    # 输出
    "keep_images": False,
    "keep_zip": True,
    "keep_unpacked": False,
    "auto_open_pdf": False,
    "skip_crawled": False,
    "auto_resume": True,          # 启动时自动继续上次未完成的任务
    "pdf_quality": 92,
    "pdf_max_width": 0,             # 0 = 保持原始尺寸
    "filename_template": "JM{id} {title}",
    "image_suffix": ".jpg",
    # 会话
    "last_input": "",
    "window_geometry": "",
}


def _config_path() -> Path:
    return runtime.config_dir() / CONFIG_FILE


def _clamp(value, low, high, fallback):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, v))


def sanitize(cfg: dict) -> dict:
    out = dict(DEFAULTS)
    if isinstance(cfg, dict):
        out.update({k: v for k, v in cfg.items() if k in DEFAULTS})

    out["client_impl"] = out["client_impl"] if out["client_impl"] in ("api", "html") else "api"
    out["auto_fallback"] = bool(out["auto_fallback"])
    out["keep_images"] = bool(out["keep_images"])
    out["keep_zip"] = bool(out["keep_zip"])
    out["keep_unpacked"] = bool(out["keep_unpacked"])
    out["auto_open_pdf"] = bool(out["auto_open_pdf"])
    out["skip_crawled"] = bool(out["skip_crawled"])
    out["auto_resume"] = bool(out["auto_resume"])

    out["threads_image"] = _clamp(out["threads_image"], 1, 50, 30)
    out["threads_photo"] = _clamp(out["threads_photo"], 1, 32, 8)
    out["retry_times"] = _clamp(out["retry_times"], 0, 20, 5)
    out["pdf_quality"] = _clamp(out["pdf_quality"], 50, 100, 92)
    out["pdf_max_width"] = _clamp(out["pdf_max_width"], 0, 6000, 0)

    suffix = str(out.get("image_suffix") or "").strip()
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix
    out["image_suffix"] = suffix if suffix in ("", ".jpg", ".png", ".webp") else ".jpg"

    template = str(out.get("filename_template") or "").strip()
    if not template:
        template = DEFAULTS["filename_template"]
    out["filename_template"] = template

    storage = str(out.get("storage_dir") or "").strip() or "crawled_data"
    out["storage_dir"] = storage

    proxy = str(out.get("proxy") or "").strip()
    out["proxy"] = proxy or "system"
    out["cookies_avs"] = str(out.get("cookies_avs") or "").strip()
    out["domains"] = str(out.get("domains") or "").strip()
    return out


def load() -> dict:
    path = _config_path()
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            runtime.log_line(f"配置文件读取失败，使用默认配置：{e}", "warn")
            data = {}
    return sanitize(data)


def save(cfg: dict) -> dict:
    cfg = sanitize(cfg)
    path = _config_path()
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as e:
        runtime.log_line(f"配置保存失败：{e}", "error")
    return cfg


def storage_root(cfg: dict) -> Path:
    raw = str(cfg.get("storage_dir") or "crawled_data")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = runtime.home() / p
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def storage_layout(cfg: dict) -> dict[str, Path]:
    root = storage_root(cfg)
    layout = {
        "root": root,
        "images": root / "images",
        "zip": root / "zip",
        "unpacked": root / "unpacked",
        "pdf": root / "pdf",
    }
    for key in ("images", "zip", "unpacked", "pdf"):
        layout[key].mkdir(parents=True, exist_ok=True)
    return layout


def _proxy_value(raw: str):
    val = (raw or "").strip()
    if not val or val.lower() in ("system", "auto"):
        return "system"
    if val.lower() in ("none", "null", "off", "no", "直连", "不使用"):
        return None
    return val


def _domain_list(raw: str) -> list[str]:
    items = []
    for chunk in str(raw or "").replace("，", ",").replace("\n", ",").split(","):
        item = chunk.strip()
        if not item:
            continue
        item = item.replace("https://", "").replace("http://", "").strip("/")
        if item and item not in items:
            items.append(item)
    return items


def build_option(cfg: dict, impl: str | None = None) -> Path:
    """按当前配置生成 jmcomic 的 option 配置文件，返回路径。"""
    cfg = sanitize(cfg)
    impl = impl or cfg["client_impl"]
    layout = storage_layout(cfg)

    client: dict[str, Any] = {
        "impl": impl,
        "retry_times": cfg["retry_times"],
        "postman": {
            "meta_data": {
                "proxies": _proxy_value(cfg["proxy"]),
            }
        },
    }
    if cfg["cookies_avs"]:
        client["postman"]["meta_data"]["cookies"] = {"AVS": cfg["cookies_avs"]}

    domains = _domain_list(cfg["domains"])
    if domains:
        client["domain"] = {impl: domains}

    image_cfg: dict[str, Any] = {"decode": True}
    if cfg["image_suffix"]:
        image_cfg["suffix"] = cfg["image_suffix"]

    data = {
        "log": True,
        "client": client,
        "dir_rule": {
            "base_dir": str(layout["images"]),
            "rule": "Bd / JM{Aid} / Pindex",
        },
        "download": {
            "cache": True,
            "image": image_cfg,
            "threading": {
                "image": cfg["threads_image"],
                "photo": cfg["threads_photo"],
            },
        },
    }

    path = runtime.config_dir() / f"option_{impl}.yml"
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    path.write_text(text, encoding="utf-8")
    return path
