"""主窗口。"""
from __future__ import annotations

import queue
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import config as config_mod
from .. import parser, queue_state, runtime
from ..fsutil import human_size
from ..history import History
from ..pipeline import Cancelled, Pipeline
from .theme import C, FAMILY, FS, apply_theme, ui_font
from .widgets import (CheckBox, InputText, ProgressBar, ScrollFrame, button, card,
                      chip, hline, label)

NAV_ITEMS = [
    ("crawl", "⬇", "爬取"),
    ("history", "☰", "记录"),
    ("settings", "⚙", "设置"),
]

STATUS_TAG = {
    "完成": "ok",
    "失败": "err",
    "跳过": "dim",
    "已取消": "warn",
    "准备": "wait",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = config_mod.load()
        if not (runtime.config_dir() / config_mod.CONFIG_FILE).exists():
            config_mod.save(self.cfg)
        self.history = History()
        self.queue: queue.Queue = queue.Queue()
        self.running = False
        self.pipeline: Pipeline | None = None
        self.task_items: dict[str, str] = {}
        self._tasks: dict[str, dict] = {}      # 任务明细（持久化用）
        self._order: list[str] = []            # 任务顺序
        self._restored: list[str] = []         # 上次未完成、待继续的番号
        self._closing = False
        self.pending_ids: queue.Queue = queue.Queue()   # 待处理任务队列
        self._pending_set: set[str] = set()             # 队列内番号（去重用）
        self._running_id: str | None = None
        self._total_added = 0
        self._finished = 0
        self._stopping = False
        self._stop_requested = False
        self._worker_thread: threading.Thread | None = None
        self.parsed_ids: list[str] = []
        self.records: list[dict] = []
        self._parse_job = None
        self._current_page = "crawl"

        apply_theme(self)
        self.title(f"{runtime.APP_NAME} · 番号 → PDF")
        self.minsize(1040, 700)
        self._restore_geometry()

        runtime.set_ui_sink(lambda level, msg: self.queue.put(
            {"type": "log", "level": level, "msg": msg}
        ))

        self._build()
        self._refresh_history()
        self._restore_queue()
        self._update_header_path()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._drain)
        runtime.log_line(f"界面已启动 v{runtime.VERSION}｜home={runtime.home()}")
        self._append_log("info", f"{runtime.APP_NAME} v{runtime.VERSION} 已就绪")
        self._append_log("dim", f"数据目录：{runtime.home()}")

    # ================================================================== #
    # 布局
    # ================================================================== #
    def _restore_geometry(self):
        geo = str(self.cfg.get("window_geometry") or "")
        if geo and "x" in geo:
            try:
                self.geometry(geo)
                return
            except Exception:
                pass
        width, height = 1200, 810
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(width, int(screen_w * 0.92))
        height = min(height, int(screen_h * 0.88))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._build_header()

        self.nav = tk.Frame(self, bg=C["panel"], width=200)
        self.nav.grid(row=1, column=0, sticky="ns")
        self.nav.pack_propagate(False)
        self._build_nav()

        self.content = tk.Frame(self, bg=C["bg"])
        self.content.grid(row=1, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self.pages["crawl"] = self._build_crawl_page(self.content)
        self.pages["history"] = self._build_history_page(self.content)
        self.pages["settings"] = self._build_settings_page(self.content)
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self._build_statusbar()
        self._show("crawl")

    # ------------------------------------------------------------------ #
    def _build_header(self):
        header = tk.Frame(self, bg=C["panel"], height=66)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_propagate(False)

        left = tk.Frame(header, bg=C["panel"])
        left.pack(side="left", padx=(18, 0), pady=13)
        logo = tk.Label(
            left, text="JM", bg=C["accent"], fg="#ffffff",
            font=(FAMILY, 13, "bold"), width=3, height=1,
        )
        logo.pack(side="left")
        titles = tk.Frame(left, bg=C["panel"])
        titles.pack(side="left", padx=(12, 0))
        label(titles, "JMComic 客户端", size=13, bold=True, bg=C["panel"]).pack(anchor="w")
        label(
            titles, "番号批量下载 · 自动解包 · 合成 PDF", size=9, fg=C["muted"], bg=C["panel"]
        ).pack(anchor="w")

        right = tk.Frame(header, bg=C["panel"])
        right.pack(side="right", padx=18)
        self.header_path = label(right, "", size=9, fg=C["muted"], bg=C["panel"])
        self.header_path.pack(side="left", padx=(0, 10))
        button(right, "打开数据目录", self._open_data_dir, kind="subtle", pady=5).pack(side="left")

        tk.Frame(self, bg=C["border"], height=1).grid(row=0, column=0, columnspan=2, sticky="sew")

    def _build_nav(self):
        tk.Frame(self.nav, bg=C["panel"], height=14).pack(fill="x")
        self.nav_items = {}
        for key, icon, text in NAV_ITEMS:
            item = tk.Frame(self.nav, bg=C["panel"], cursor="hand2")
            item.pack(fill="x", pady=1)
            bar = tk.Frame(item, bg=C["panel"], width=3)
            bar.pack(side="left", fill="y")
            lbl = tk.Label(
                item, text=f"  {icon}   {text}", bg=C["panel"], fg=C["muted"],
                font=ui_font(11), anchor="w", padx=12, pady=11, cursor="hand2",
            )
            lbl.pack(side="left", fill="both", expand=True)
            for widget in (item, lbl):
                widget.bind("<Button-1>", lambda _e, k=key: self._show(k))
                widget.bind("<Enter>", lambda _e, l=lbl, k=key: self._nav_hover(l, k, True))
                widget.bind("<Leave>", lambda _e, l=lbl, k=key: self._nav_hover(l, k, False))
            self.nav_items[key] = (item, bar, lbl)

        bottom = tk.Frame(self.nav, bg=C["panel"])
        bottom.pack(side="bottom", fill="x", pady=14)
        hline(bottom).pack(fill="x", pady=(0, 10))
        label(bottom, f"v{runtime.VERSION}", size=8, fg=C["dim"], bg=C["panel"]).pack(padx=16, anchor="w")
        label(bottom, "数据全部保存在本地", size=8, fg=C["dim"], bg=C["panel"]).pack(padx=16, anchor="w")

    def _nav_hover(self, lbl, key, entering):
        if self._current_page == key:
            return
        lbl.configure(fg=C["text"] if entering else C["muted"])

    def _show(self, key):
        self._current_page = key
        for name, (item, bar, lbl) in self.nav_items.items():
            active = name == key
            item.configure(bg=C["card2"] if active else C["panel"])
            lbl.configure(
                bg=C["card2"] if active else C["panel"],
                fg=C["text"] if active else C["muted"],
                font=ui_font(11, bold=active),
            )
            bar.configure(bg=C["accent"] if active else C["panel"])
        self.pages[key].tkraise()
        if key == "history":
            self._refresh_history()
        if key == "settings":
            self._load_settings_to_ui()

    # ================================================================== #
    # 爬取页
    # ================================================================== #
    def _build_crawl_page(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        wrap = tk.Frame(page, bg=C["bg"])
        wrap.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 8))
        wrap.grid_columnconfigure(0, weight=1)

        # ---- 输入卡片
        box = card(wrap)
        box.grid(row=0, column=0, sticky="ew")
        box.grid_columnconfigure(0, weight=1)

        head = tk.Frame(box, bg=C["card"])
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        label(head, "① 输入番号", size=12, bold=True).pack(side="left")
        label(
            head,
            "支持 jm54747 / h540931 / 142176(备注) / 批量数字 / 链接，可混合粘贴",
            size=9, fg=C["muted"],
        ).pack(side="right")

        self.input = InputText(
            box,
            height=4,
            placeholder="在这里粘贴番号，例如：\n"
                        "jm54747电梯（极品）  142176(母子大车)\n"
                        "h540931(瞬)-h499835(幼瞬)\n"
                        "47228，118983，152470，197393",
        )
        self.input.grid(row=1, column=0, sticky="ew", padx=16)
        self.input.text.bind("<KeyRelease>", self._schedule_parse)

        toolbar = tk.Frame(box, bg=C["card"])
        toolbar.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 14))
        label(
            toolbar, "运行中可继续追加 · 重复自动去重", size=9, fg=C["dim"]
        ).pack(side="left")
        self.btn_start = button(toolbar, "开始爬取", self._submit, kind="primary", padx=22)
        self.btn_start.pack(side="right")
        self.btn_stop = button(toolbar, "停止", self._stop, kind="danger", padx=16)
        self.btn_stop.pack(side="right", padx=(0, 8))
        self.btn_stop.configure(state="disabled")
        button(toolbar, "解析预览", self._parse_preview, kind="ghost").pack(
            side="right", padx=(0, 8)
        )
        button(toolbar, "清空", self._clear_input, kind="subtle").pack(side="right", padx=(0, 8))

        # ---- 识别结果
        chips_row = tk.Frame(page, bg=C["bg"], height=26)
        chips_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 8))
        chips_row.pack_propagate(False)
        self.chip_count = label(chips_row, "", size=9, bold=True, fg=C["accent"], bg=C["bg"])
        self.chip_count.pack(side="left", padx=(0, 10))
        self.chips_frame = tk.Frame(chips_row, bg=C["bg"])
        self.chips_frame.pack(side="left", fill="x", expand=True)
        label(self.chips_frame, "尚未识别到番号", size=9, fg=C["dim"], bg=C["bg"]).pack(side="left")

        # ---- 任务队列
        task_box = card(page)
        task_box.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=18, pady=(0, 10))
        task_box.grid_rowconfigure(1, weight=1)
        task_box.grid_columnconfigure(0, weight=1)

        task_head = tk.Frame(task_box, bg=C["card"])
        task_head.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        label(task_head, "② 任务队列", size=12, bold=True).pack(side="left")
        button(task_head, "清空列表", self._clear_task_list, kind="subtle",
               pady=2, padx=9, size=9).pack(side="right")
        self.overall_label = label(task_head, "0 / 0", size=9, fg=C["muted"])
        self.overall_label.pack(side="right", padx=(10, 10))
        self.progress = ProgressBar(task_head, width=200, height=6, bg=C["card"])
        self.progress.pack(side="right", padx=(0, 4))

        tree_wrap = tk.Frame(task_box, bg=C["card"])
        tree_wrap.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)

        columns = ("id", "title", "status", "progress", "detail")
        self.task_tree = ttk.Treeview(
            tree_wrap, columns=columns, show="headings", selectmode="browse"
        )
        for col, text, width, anchor in (
            ("id", "番号", 92, "w"),
            ("title", "标题", 330, "w"),
            ("status", "状态", 96, "w"),
            ("progress", "进度", 66, "center"),
            ("detail", "备注", 210, "w"),
        ):
            self.task_tree.heading(col, text=text, anchor=anchor)
            self.task_tree.column(col, width=width, anchor=anchor, stretch=(col == "title"))
        self.task_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.task_tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.task_tree.configure(yscrollcommand=vsb.set)
        for tag, color in (
            ("ok", C["ok"]), ("err", C["err"]), ("warn", C["warn"]),
            ("run", C["accent"]), ("wait", C["muted"]), ("dim", C["dim"]),
        ):
            self.task_tree.tag_configure(tag, foreground=color)
        self.task_tree.insert(
            "", "end", iid="_hint",
            values=("", "粘贴番号后点「开始爬取」；运行中可继续粘贴，点「追加任务」加入队列", "", "", ""),
            tags=("dim",),
        )

        # ---- 日志
        log_box = card(page)
        log_box.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 14))
        log_box.grid_columnconfigure(0, weight=1)

        log_head = tk.Frame(log_box, bg=C["card"])
        log_head.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 4))
        label(log_head, "运行日志", size=10, bold=True).pack(side="left")
        button(log_head, "打开日志文件", self._open_log, kind="subtle", pady=3, padx=10).pack(side="right")
        button(log_head, "清空", self._clear_log, kind="subtle", pady=3, padx=10).pack(
            side="right", padx=(0, 6)
        )

        log_wrap = tk.Frame(log_box, bg=C["card"])
        log_wrap.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        log_wrap.grid_columnconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_wrap, height=5, bg=C["input"], fg=C["muted"], relief="flat", bd=0,
            highlightthickness=1, highlightbackground=C["border"], highlightcolor=C["border"],
            font=(FAMILY, 9), padx=10, pady=6, wrap="none", state="disabled",
        )
        self.log_text.grid(row=0, column=0, sticky="ew")
        log_vsb = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log_text.yview)
        log_vsb.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_vsb.set)
        self.log_text.tag_configure("info", foreground=C["muted"])
        self.log_text.tag_configure("ok", foreground=C["ok"])
        self.log_text.tag_configure("err", foreground=C["err"])
        self.log_text.tag_configure("warn", foreground=C["warn"])
        self.log_text.tag_configure("dim", foreground=C["dim"])

        return page

    # ================================================================== #
    # 记录页
    # ================================================================== #
    def _build_history_page(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        head = tk.Frame(page, bg=C["bg"])
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        label(head, "爬取记录", size=13, bold=True).pack(side="left")
        self.history_count = label(head, "", size=9, fg=C["muted"])
        self.history_count.pack(side="left", padx=(10, 0))

        right = tk.Frame(head, bg=C["bg"])
        right.pack(side="right")
        button(right, "清空记录", self._clear_history, kind="subtle", pady=4).pack(side="right")
        button(right, "导出 CSV", self._export_history, kind="subtle", pady=4).pack(
            side="right", padx=(0, 6)
        )
        self.search_entry = tk.Entry(
            right, bg=C["input"], fg=C["text"], insertbackground=C["accent"],
            relief="flat", bd=0, highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"], font=ui_font(10), width=22,
        )
        self.search_entry.pack(side="right", padx=(0, 8), ipady=5)
        self.search_entry.bind("<KeyRelease>", lambda _e: self._render_records())
        label(right, "搜索", size=9, fg=C["dim"]).pack(side="right", padx=(0, 6))

        box = card(page)
        box.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 10))
        box.grid_rowconfigure(0, weight=1)
        box.grid_columnconfigure(0, weight=1)

        wrap = tk.Frame(box, bg=C["card"])
        wrap.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        columns = ("id", "title", "pages", "time", "file")
        self.hist_tree = ttk.Treeview(wrap, columns=columns, show="headings", selectmode="browse")
        for col, text, width, anchor in (
            ("id", "番号", 96, "w"),
            ("title", "标题", 380, "w"),
            ("pages", "页数", 70, "center"),
            ("time", "完成时间", 150, "center"),
            ("file", "PDF", 260, "w"),
        ):
            self.hist_tree.heading(col, text=text, anchor=anchor)
            self.hist_tree.column(col, width=width, anchor=anchor, stretch=(col == "title"))
        self.hist_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.hist_tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.hist_tree.configure(yscrollcommand=vsb.set)
        self.hist_tree.bind("<Double-1>", lambda _e: self._open_selected_pdf())

        actions = tk.Frame(page, bg=C["bg"])
        actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 14))
        button(actions, "打开 PDF", self._open_selected_pdf, kind="primary", pady=5).pack(side="left")
        button(actions, "打开所在文件夹", self._open_selected_folder, kind="ghost", pady=5).pack(
            side="left", padx=(8, 0)
        )
        button(actions, "重新爬取", self._recrawl_selected, kind="ghost", pady=5).pack(
            side="left", padx=(8, 0)
        )
        button(actions, "删除记录", self._delete_selected, kind="subtle", pady=5).pack(
            side="left", padx=(8, 0)
        )
        return page

    # ================================================================== #
    # 设置页
    # ================================================================== #
    def _build_settings_page(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, weight=1)

        scroll = ScrollFrame(page, bg=C["bg"])
        self.settings_scroll = scroll
        scroll.grid(row=0, column=0, sticky="nsew", padx=18, pady=(16, 10))
        body = scroll.inner
        body.grid_columnconfigure(0, weight=1)

        self.vars: dict[str, tk.Variable] = {
            "storage_dir": tk.StringVar(),
            "client_impl": tk.StringVar(),
            "threads_image": tk.IntVar(),
            "threads_photo": tk.IntVar(),
            "retry_times": tk.IntVar(),
            "proxy": tk.StringVar(),
            "cookies_avs": tk.StringVar(),
            "pdf_quality": tk.IntVar(),
            "pdf_max_width": tk.IntVar(),
            "filename_template": tk.StringVar(),
            "keep_images": tk.BooleanVar(),
            "keep_zip": tk.BooleanVar(),
            "keep_unpacked": tk.BooleanVar(),
            "auto_open_pdf": tk.BooleanVar(),
            "skip_crawled": tk.BooleanVar(),
            "auto_fallback": tk.BooleanVar(),
            "auto_resume": tk.BooleanVar(),
        }

        # ---- 存储
        sec = self._section(body, "存储位置", "下载的图片、ZIP、PDF 都保存在这里；相对路径基于程序所在目录。")
        row = tk.Frame(sec, bg=C["card"])
        row.pack(fill="x", pady=(0, 4))
        label(row, "存储根目录", size=9, fg=C["muted"], width=10, anchor="w").pack(side="left")
        entry = self._entry(row, self.vars["storage_dir"])
        entry.pack(side="left", fill="x", expand=True, padx=(6, 8))
        button(row, "浏览…", self._browse_storage, kind="ghost", pady=4, padx=12).pack(side="left")
        button(row, "打开", self._open_storage, kind="subtle", pady=4, padx=12).pack(
            side="left", padx=(6, 0)
        )
        self.storage_hint = label(sec, "", size=8, fg=C["dim"])
        self.storage_hint.pack(anchor="w", pady=(2, 0))

        # ---- 下载
        sec = self._section(body, "下载设置", "并发过高容易触发限流，建议图片 20~30、章节 4~8。")
        row = tk.Frame(sec, bg=C["card"])
        row.pack(fill="x", pady=(0, 8))
        label(row, "客户端实现", size=9, fg=C["muted"], width=10, anchor="w").pack(side="left")
        combo = ttk.Combobox(
            row, textvariable=self.vars["client_impl"], state="readonly", width=10,
            values=("api", "html"),
        )
        combo.pack(side="left", padx=(6, 12))
        label(row, "api 兼容性好 / html 效率高", size=8, fg=C["dim"]).pack(side="left")

        row = tk.Frame(sec, bg=C["card"])
        row.pack(fill="x", pady=(0, 8))
        self._spin_row(row, "图片并发", "threads_image", 1, 50, 0)
        self._spin_row(row, "章节并发", "threads_photo", 1, 32, 18)
        self._spin_row(row, "重试次数", "retry_times", 0, 20, 18)

        row = tk.Frame(sec, bg=C["card"])
        row.pack(fill="x", pady=(0, 8))
        label(row, "网络代理", size=9, fg=C["muted"], width=10, anchor="w").pack(side="left")
        self._entry(row, self.vars["proxy"], width=30).pack(side="left", padx=(6, 10), ipady=4)
        label(row, "system=跟随系统 · none=直连 · 也可填 127.0.0.1:7890", size=8, fg=C["dim"]).pack(side="left")

        row = tk.Frame(sec, bg=C["card"])
        row.pack(fill="x", pady=(0, 8))
        label(row, "Cookie AVS", size=9, fg=C["muted"], width=10, anchor="w").pack(side="left")
        self._entry(row, self.vars["cookies_avs"], width=42).pack(side="left", padx=(6, 10), ipady=4)
        label(row, "敏感题材需要登录时填写（浏览器里名为 AVS 的 Cookie）", size=8, fg=C["dim"]).pack(side="left")

        row = tk.Frame(sec, bg=C["card"])
        row.pack(fill="x", pady=(0, 4))
        label(row, "自定义域名", size=9, fg=C["muted"], width=10, anchor="w").pack(side="left", anchor="n", pady=6)
        self.domains_text = tk.Text(
            row, height=2, bg=C["input"], fg=C["text"], insertbackground=C["accent"],
            relief="flat", bd=0, highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"], font=ui_font(9), padx=8, pady=6, wrap="word",
        )
        self.domains_text.pack(side="left", fill="x", expand=True, padx=(6, 0))
        label(sec, "留空使用内置域名；多个用逗号或换行分隔，仅在网络异常时按需修改。",
              size=8, fg=C["dim"]).pack(anchor="w", pady=(2, 0))

        # ---- 输出
        sec = self._section(body, "输出设置", "默认流程：下载原图 → 打包 ZIP → 解包 → 合成 PDF。")
        row = tk.Frame(sec, bg=C["card"])
        row.pack(fill="x", pady=(0, 8))
        self._spin_row(row, "PDF 质量", "pdf_quality", 50, 100, 0)
        self._spin_row(row, "PDF 最大宽度", "pdf_max_width", 0, 6000, 18)
        label(row, "0 = 保持原始尺寸", size=8, fg=C["dim"]).pack(side="left", padx=(8, 0))

        row = tk.Frame(sec, bg=C["card"])
        row.pack(fill="x", pady=(0, 8))
        label(row, "文件命名", size=9, fg=C["muted"], width=10, anchor="w").pack(side="left")
        self._entry(row, self.vars["filename_template"]).pack(
            side="left", fill="x", expand=True, padx=(6, 0), ipady=4
        )
        label(sec, "可用占位符：{id} 番号 · {title} 标题 · {author} 作者 · {pages} 页数",
              size=8, fg=C["dim"]).pack(anchor="w", pady=(2, 6))

        checks = tk.Frame(sec, bg=C["card"])
        checks.pack(fill="x")
        items = (
            ("保留下载的原图", "keep_images"),
            ("保留 ZIP 压缩包", "keep_zip"),
            ("保留解包目录", "keep_unpacked"),
            ("完成后自动打开 PDF", "auto_open_pdf"),
            ("跳过已爬取过的番号", "skip_crawled"),
            ("下载失败时自动切换实现", "auto_fallback"),
            ("启动时自动继续未完成任务", "auto_resume"),
        )
        for index, (text, key) in enumerate(items):
            CheckBox(checks, text, self.vars[key]).grid(
                row=index // 3, column=index % 3, sticky="w", padx=(0, 20), pady=5
            )
        for col in range(3):
            checks.grid_columnconfigure(col, weight=1, uniform="check")

        # ---- 保存
        actions = tk.Frame(body, bg=C["bg"])
        actions.pack(fill="x", pady=(16, 24))
        button(actions, "保存设置", self._save_settings, kind="primary", padx=24, pady=7).pack(side="left")
        button(actions, "恢复默认", self._reset_settings, kind="subtle", pady=7).pack(
            side="left", padx=(10, 0)
        )
        label(actions, "修改后对下一个任务生效，无需重启", size=9, fg=C["dim"]).pack(
            side="left", padx=(14, 0)
        )

        return page

    def _section(self, parent, title, desc):
        box = card(parent)
        box.pack(fill="x", pady=(0, 14))
        inner = tk.Frame(box, bg=C["card"])
        inner.pack(fill="x", padx=18, pady=16)
        label(inner, title, size=11, bold=True).pack(anchor="w")
        label(inner, desc, size=8, fg=C["dim"]).pack(anchor="w", pady=(2, 12))
        return inner

    def _entry(self, parent, var, width=None):
        entry = tk.Entry(
            parent, textvariable=var, bg=C["input"], fg=C["text"],
            insertbackground=C["accent"], relief="flat", bd=0,
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"], font=ui_font(10),
        )
        if width:
            entry.configure(width=width)
        return entry

    def _spin_row(self, parent, text, key, low, high, padx_left):
        holder = tk.Frame(parent, bg=C["card"])
        holder.pack(side="left", padx=(padx_left, 0))
        label(holder, text, size=9, fg=C["muted"]).pack(side="left", padx=(0, 6))
        spin = ttk.Spinbox(
            holder, from_=low, to=high, textvariable=self.vars[key], width=6,
            style="Dark.TSpinbox", font=ui_font(10),
        )
        spin.pack(side="left")
        return spin

    # ------------------------------------------------------------------ #
    def _build_statusbar(self):
        bar = tk.Frame(self, bg=C["panel"], height=30)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        tk.Frame(bar, bg=C["border"], height=1).pack(fill="x", side="top")
        self.status_var = tk.StringVar(value="就绪")
        label(bar, "", size=9, fg=C["muted"], bg=C["panel"], textvariable=self.status_var).pack(
            side="left", padx=18, pady=6
        )
        self.status_path = label(bar, "", size=8, fg=C["dim"], bg=C["panel"])
        self.status_path.pack(side="right", padx=18)

    # ================================================================== #
    # 事件队列
    # ================================================================== #
    def _drain(self):
        if self._closing:
            return
        processed = 0
        while processed < 300:
            try:
                event = self.queue.get_nowait()
            except queue.Empty:
                break
            processed += 1
            try:
                self._handle_event(event)
            except Exception:
                runtime.log_line(traceback.format_exc(limit=4), "error")
        try:
            self.after(70, self._drain)
        except tk.TclError:
            pass

    def _handle_event(self, event):
        kind = event.get("type")
        if kind == "log":
            self._append_log(event.get("level", "info"), event.get("msg", ""))
        elif kind == "task":
            self._update_task(event)
        elif kind == "overall":
            total = event.get("total") or 0
            done = event.get("done") or 0
            self.overall_label.configure(text=f"{done} / {total}")
            self.progress.set((done / total * 100) if total else 0)
        elif kind == "item_start":
            jm_id = str(event.get("jm_id") or "")
            self._pending_set.discard(jm_id)
            self._running_id = jm_id
            self._update_status()
        elif kind == "item_done":
            jm_id = str(event.get("jm_id") or "")
            self._pending_set.discard(jm_id)
            self._running_id = None
            self._finished += 1
            self._update_overall()
            self._update_status()
        elif kind == "finished":
            self._on_finished(event.get("summary") or {})

    def _append_log(self, level, text):
        if not text:
            return
        tag = {"error": "err", "warn": "warn", "ok": "ok", "dim": "dim", "raw": "info"}.get(
            level, "info"
        )
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text.rstrip() + "\n", tag)
        total_lines = int(self.log_text.index("end-1c").split(".")[0])
        if total_lines > 1500:
            self.log_text.delete("1.0", f"{total_lines - 1500}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ================================================================== #
    # 爬取动作
    # ================================================================== #
    def _schedule_parse(self, _event=None):
        if self._parse_job:
            try:
                self.after_cancel(self._parse_job)
            except Exception:
                pass
        self._parse_job = self.after(400, self._auto_parse)

    def _auto_parse(self):
        self._parse_job = None
        self.parsed_ids = parser.parse_ids(self.input.get())
        self._render_chips(self.parsed_ids)

    def _parse_preview(self):
        self._auto_parse()
        if not self.parsed_ids:
            self._append_log("warn", "没有从输入中识别到番号")
            messagebox.showinfo(
                "未识别到番号",
                "没有找到有效番号。\n\n可以这样输入：\njm54747电梯（极品）\n47228，118983，152470",
                parent=self,
            )
            return
        preview = "，".join(self.parsed_ids[:20])
        more = f" …共 {len(self.parsed_ids)} 个" if len(self.parsed_ids) > 20 else ""
        self._append_log("ok", f"识别到 {len(self.parsed_ids)} 个番号：{preview}{more}")

    def _render_chips(self, ids):
        for widget in self.chips_frame.winfo_children():
            widget.destroy()
        if not ids:
            self.chip_count.configure(text="")
            label(self.chips_frame, "尚未识别到番号", size=9, fg=C["dim"], bg=C["bg"]).pack(side="left")
            return
        self.chip_count.configure(text=f"识别到 {len(ids)} 个番号")
        for jm_id in ids[:10]:
            chip(self.chips_frame, f"JM{jm_id}").pack(side="left", padx=(0, 6))
        if len(ids) > 10:
            label(self.chips_frame, f"+{len(ids) - 10}", size=9, fg=C["dim"], bg=C["bg"]).pack(side="left")

    def _clear_input(self):
        self.input.set("")
        self.parsed_ids = []
        self._render_chips([])

    # ------------------------------------------------------------------ #
    # 任务队列（支持运行中追加）
    # ------------------------------------------------------------------ #
    def _submit(self):
        """把输入框里的番号加入队列；运行中提交即为追加，不打断当前任务。"""
        if self._stopping:
            self._append_log("warn", "正在停止当前任务，请稍候再添加")
            return

        raw = self.input.get()
        ids = parser.parse_ids(raw)
        starting = not self.running
        resumed = 0

        if starting:
            if self._restored:
                # 上次没跑完的任务先放回队列，不清空列表
                resumed = self._queue_restored()
            else:
                self._reset_task_view()

        if not ids and not resumed:
            messagebox.showwarning(
                "请输入番号", "没有识别到有效番号，请检查输入内容。", parent=self
            )
            return

        added = self._enqueue(ids)
        if not added and not resumed:
            self._append_log("warn", "这些番号已经在队列里或正在下载，已忽略")
            return

        if added:
            self.cfg["last_input"] = raw
            config_mod.save(self.cfg)
            self.input.set("")
            self.parsed_ids = []
            self._render_chips([])
            self._append_log(
                "info",
                f"{'加入' if starting else '追加'} {len(added)} 个任务"
                f"（队列共 {self._total_added} 项）",
            )

        if starting:
            self._start_worker()
        else:
            self._update_status()

    def _clear_task_list(self):
        if self.running:
            messagebox.showinfo("提示", "正在爬取中，请先点「停止」再清空列表", parent=self)
            return
        if not self._order:
            return
        if not messagebox.askyesno(
            "清空列表",
            "清空当前任务列表？\n（不会删除已下载的文件和爬取历史）",
            parent=self,
        ):
            return
        self._reset_task_view()
        self._append_log("warn", "任务列表已清空")

    def _reset_task_view(self):
        """开新一批任务时清空列表、计数和持久化状态。"""
        self.task_tree.delete(*self.task_tree.get_children())
        self.task_items.clear()
        self._pending_set.clear()
        while True:
            try:
                self.pending_ids.get_nowait()
            except queue.Empty:
                break
        self._tasks.clear()
        self._order.clear()
        self._restored.clear()
        queue_state.clear()
        self._running_id = None
        self._total_added = 0
        self._finished = 0
        self._update_overall()

    # 这些状态下重复提交直接忽略；「失败 / 已取消」允许重新入队重试
    _SKIP_DUP_STATES = {
        "等待", "准备", "下载中", "打包 ZIP", "解包", "生成 PDF", "完成", "跳过",
    }

    def _enqueue(self, ids):
        """插入任务行并入队，返回真正新增的番号。"""
        added = []
        for jm_id in ids:
            if jm_id in self._pending_set or jm_id == self._running_id:
                continue

            item = self.task_items.get(jm_id)
            if item and self.task_tree.exists(item):
                if self.task_tree.set(item, "status") in self._SKIP_DUP_STATES:
                    continue

            self.pending_ids.put(jm_id)
            self._pending_set.add(jm_id)
            self._total_added += 1

            record = self._tasks.get(jm_id)
            if record:
                record.update({"status": "等待", "detail": ""})
            else:
                self._tasks[jm_id] = {"jm_id": jm_id, "title": "", "status": "等待", "detail": ""}
                self._order.append(jm_id)

            if item and self.task_tree.exists(item):
                self.task_tree.item(
                    item, values=(f"JM{jm_id}", "", "等待", "0%", ""), tags=("wait",)
                )
            else:
                item = self.task_tree.insert(
                    "", "end", iid=f"jm_{jm_id}",
                    values=(f"JM{jm_id}", "", "等待", "0%", ""), tags=("wait",),
                )
                self.task_items[jm_id] = item
            added.append(jm_id)

        if added:
            self.task_tree.see(self.task_items[added[-1]])
        self._update_overall()
        self._persist_queue()
        return added

    # ------------------------------------------------------------------ #
    # 队列持久化（关闭后可继续）
    # ------------------------------------------------------------------ #
    def _persist_queue(self, force=False, running_as_waiting=False):
        if self._closing and not force:
            return
        records = []
        for jm_id in self._order:
            task = self._tasks.get(jm_id)
            if not task:
                continue
            record = dict(task)
            if running_as_waiting and record.get("status") in queue_state.ACTIVE_STATES:
                record["status"] = "等待"
            records.append(record)

        # 只要列表里还有任务就保存：下次启动仍能看到上次的队列和结果
        if records:
            queue_state.save(records)
        else:
            queue_state.clear()

    def _restore_queue(self):
        tasks = queue_state.load()
        if not tasks:
            return

        self.task_tree.delete(*self.task_tree.get_children())
        self.task_items.clear()
        self._tasks.clear()
        self._order.clear()
        self._restored.clear()

        for task in tasks:
            jm_id = str(task.get("jm_id") or "")
            if not jm_id or jm_id in self._tasks:
                continue
            status = str(task.get("status") or "等待")
            if status in queue_state.ACTIVE_STATES:
                status = "等待"
                self._restored.append(jm_id)

            record = {
                "jm_id": jm_id,
                "title": task.get("title") or "",
                "status": status,
                "detail": task.get("detail") or "",
            }
            self._tasks[jm_id] = record
            self._order.append(jm_id)
            self.task_items[jm_id] = self.task_tree.insert(
                "", "end", iid=f"jm_{jm_id}",
                values=(
                    f"JM{jm_id}", record["title"], status,
                    "0%" if status == "等待" else "100%", record["detail"],
                ),
                tags=(STATUS_TAG.get(status, "wait"),),
            )

        self._total_added = len(self._order)
        self._finished = sum(
            1 for r in self._tasks.values() if r["status"] in queue_state.TERMINAL_STATES
        )
        self._update_overall()

        pending = len(self._restored)
        runtime.log_line(
            f"恢复上次队列：共 {self._total_added} 条，其中待继续 {pending} 个"
        )
        if not pending:
            self._append_log(
                "dim",
                f"已恢复上次的任务列表（{self._total_added} 条，均已完成）",
            )
            return

        self._append_log(
            "warn",
            f"已恢复上次未完成的任务：{pending} 个（共 {self._total_added} 条记录）",
        )
        if self.cfg.get("auto_resume"):
            self._append_log("info", "1 秒后自动继续，可在设置里关闭")
            self.after(1000, self._resume_restored)
        else:
            self._append_log("info", "点「开始爬取」即可继续")

    def _queue_restored(self) -> int:
        count = 0
        for jm_id in list(self._restored):
            if jm_id in self._pending_set:
                continue
            self.pending_ids.put(jm_id)
            self._pending_set.add(jm_id)
            record = self._tasks.get(jm_id)
            if record is not None:
                record["status"] = "等待"
                record["detail"] = ""
            item = self.task_items.get(jm_id)
            if item and self.task_tree.exists(item):
                self.task_tree.item(
                    item,
                    values=(f"JM{jm_id}", record.get("title", "") if record else "",
                            "等待", "0%", ""),
                    tags=("wait",),
                )
            count += 1
        self._restored.clear()
        return count

    def _resume_restored(self):
        if self.running or not self._restored:
            return
        count = self._queue_restored()
        if count:
            self._append_log("info", f"继续上次未完成的 {count} 个任务")
            self._start_worker()

    def _start_worker(self):
        self._stop_requested = False
        self.pipeline = Pipeline(self.cfg, self.queue.put, self.history)
        self._set_running(True)
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def _worker_loop(self):
        """常驻消费队列：取一个、处理一个，队列空了再退出。"""
        ok = fail = skip = 0
        started = time.time()
        last_pdf = ""
        cancelled = False

        while not self._stop_requested:
            try:
                jm_id = self.pending_ids.get(timeout=1.2)
            except queue.Empty:
                break  # 队列空，收工；期间新加的任务会被下一轮取到

            if self._stop_requested:
                self.queue.put({"type": "task", "jm_id": jm_id, "status": "已取消",
                                "detail": "未开始"})
                self.queue.put({"type": "item_done", "jm_id": jm_id})
                break

            self.queue.put({"type": "item_start", "jm_id": jm_id})
            self.queue.put({"type": "task", "jm_id": jm_id, "status": "准备", "progress": 0.0})

            if self.pipeline.cfg["skip_crawled"] and self.pipeline.history.has(jm_id):
                skip += 1
                self.queue.put({"type": "task", "jm_id": jm_id, "status": "跳过",
                                "progress": 1.0, "detail": "历史已存在"})
                runtime.log_line(f"JM{jm_id} 已爬取过，跳过")
                self.queue.put({"type": "item_done", "jm_id": jm_id})
                continue

            item_cancelled = False
            try:
                record = self.pipeline.run_one(jm_id)
                ok += 1
                last_pdf = record.get("pdf") or last_pdf
                self.queue.put({
                    "type": "task", "jm_id": jm_id, "status": "完成",
                    "title": record.get("title", ""), "progress": 1.0,
                    "detail": f"{record.get('pages', 0)} 页",
                })
                runtime.log_line(
                    f"JM{jm_id} 完成：{record.get('pages', 0)} 页 → {record.get('pdf', '')}"
                )
            except Cancelled:
                item_cancelled = True
                self.queue.put({"type": "task", "jm_id": jm_id, "status": "已取消",
                                "detail": "用户停止"})
            except Exception as e:
                fail += 1
                message = str(e) or type(e).__name__
                self.queue.put({"type": "task", "jm_id": jm_id, "status": "失败",
                                "detail": message[:120]})
                runtime.log_line(f"JM{jm_id} 失败：{message}")
                runtime.log_line(traceback.format_exc(limit=6), "error")
            finally:
                self.queue.put({"type": "item_done", "jm_id": jm_id})

            if item_cancelled:
                cancelled = True
                break

        summary = {
            "ok": ok,
            "fail": fail,
            "skip": skip,
            "cancelled": cancelled or self._stop_requested,
            "seconds": round(time.time() - started, 1),
            "last_pdf": last_pdf,
        }
        runtime.log_line(
            f"任务结束：成功 {ok}｜失败 {fail}｜跳过 {skip}｜耗时 {summary['seconds']}s"
        )
        self.queue.put({"type": "finished", "summary": summary})

    def _stop(self):
        if not self.running or not self.pipeline:
            return
        self._stopping = True
        self._stop_requested = True
        self._append_log("warn", "正在停止，等待当前任务收尾…")
        self.btn_stop.configure(state="disabled")
        self.btn_start.configure(state="disabled")

        # 清掉还没开始的任务
        while True:
            try:
                jm_id = self.pending_ids.get_nowait()
            except queue.Empty:
                break
            self._pending_set.discard(jm_id)
            item = self.task_items.get(jm_id)
            if item and self.task_tree.exists(item):
                self.task_tree.item(
                    item, values=(f"JM{jm_id}", "", "已取消", "0%", "未开始"), tags=("warn",)
                )
            record = self._tasks.get(jm_id)
            if record is not None:
                record["status"] = "已取消"
                record["detail"] = "未开始"
            self._finished += 1
        self._update_overall()
        self._persist_queue()
        self.pipeline.cancel()

    def _set_running(self, running):
        self.running = running
        self.btn_start.configure(state="normal", text="追加任务" if running else "开始爬取")
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.status_var.set("正在爬取…" if running else "就绪")

    def _update_overall(self):
        total = self._total_added
        done = min(self._finished, total)
        self.overall_label.configure(text=f"{done} / {total}")
        self.progress.set((done / total * 100) if total else 0)

    def _update_status(self):
        if not self.running:
            return
        self.status_var.set(
            f"正在爬取 · 完成 {self._finished}/{self._total_added}"
            f" · 待处理 {self.pending_ids.qsize()}"
        )

    def _update_task(self, event):
        jm_id = str(event.get("jm_id") or "")
        item = self.task_items.get(jm_id)
        if not item:
            return
        title = event.get("title")
        status = event.get("status")
        progress = event.get("progress")
        detail = event.get("detail")
        if title:
            self.task_tree.set(item, "title", title)
        if detail is not None:
            self.task_tree.set(item, "detail", detail)
        if progress is not None:
            self.task_tree.set(item, "progress", f"{int(progress * 100)}%")
        record = self._tasks.get(jm_id)
        if record is not None:
            if title:
                record["title"] = title
            if detail is not None:
                record["detail"] = detail
            if status:
                record["status"] = status

        if status:
            self.task_tree.set(item, "status", status)
            tag = STATUS_TAG.get(status)
            if tag is None:
                tag = "run" if status in ("下载中", "打包 ZIP", "解包", "生成 PDF") else "wait"
            self.task_tree.item(item, tags=(tag,))
            if tag == "run":
                self.task_tree.see(item)
            self._persist_queue()

    def _on_finished(self, summary):
        self._stopping = False
        self._set_running(False)
        self._finished = max(self._finished, self._total_added)
        self._update_overall()

        ok = summary.get("ok", 0)
        fail = summary.get("fail", 0)
        skip = summary.get("skip", 0)
        seconds = summary.get("seconds", 0)
        if summary.get("cancelled"):
            self.status_var.set(f"已停止 · 完成 {ok} · 失败 {fail}")
            self._append_log("warn", "任务已取消")
        else:
            self.status_var.set(f"完成 {ok} · 失败 {fail} · 跳过 {skip} · 耗时 {seconds}s")
            self._append_log(
                "ok" if fail == 0 else "warn",
                f"任务结束：成功 {ok}，失败 {fail}，跳过 {skip}，耗时 {seconds}s",
            )
        self._refresh_history()

        last_pdf = summary.get("last_pdf") or ""
        if self.cfg.get("auto_open_pdf") and last_pdf and Path(last_pdf).exists():
            runtime.open_path(last_pdf)

        self._persist_queue()

        # 收尾瞬间又进来的任务，自动续跑
        if not self.pending_ids.empty():
            self._append_log("info", "队列里还有任务，继续执行")
            self._start_worker()

    # ================================================================== #
    # 记录动作
    # ================================================================== #
    def _refresh_history(self):
        self.history.load()
        self.records = self.history.all()
        self._render_records()

    def _render_records(self):
        if not hasattr(self, "hist_tree"):
            return
        keyword = ""
        if hasattr(self, "search_entry"):
            keyword = self.search_entry.get().strip().lower()
        self.hist_tree.delete(*self.hist_tree.get_children())
        if not self.records:
            self.hist_tree.insert(
                "", "end", iid="_empty",
                values=("", "还没有爬取记录，去「爬取」页输入番号开始吧", "", "", ""),
                tags=("dim",),
            )
            self.hist_tree.tag_configure("dim", foreground=C["dim"])
            self.history_count.configure(text="共 0 个")
            return
        shown = 0
        for record in self.records:
            jm_id = str(record.get("jm_id", ""))
            title = str(record.get("title", ""))
            if keyword and keyword not in jm_id.lower() and keyword not in title.lower():
                continue
            pdf_name = Path(self.history.resolve(record.get("pdf", ""))).name
            self.hist_tree.insert(
                "", "end", iid=jm_id,
                values=(f"JM{jm_id}", title, record.get("pages", ""),
                        record.get("time", ""), pdf_name),
            )
            shown += 1
        total = len(self.records)
        self.history_count.configure(
            text=f"{shown} / {total} 个" if keyword else f"共 {total} 个"
        )

    def _selected_record(self):
        selection = self.hist_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一条记录", parent=self)
            return None
        jm_id = selection[0]
        record = self.history.get(jm_id)
        if not record:
            messagebox.showwarning("提示", "记录已不存在，请刷新", parent=self)
        return record

    def _open_selected_pdf(self):
        record = self._selected_record()
        if not record:
            return
        pdf = self.history.resolve(record.get("pdf", ""))
        if not pdf or not Path(pdf).exists():
            messagebox.showwarning(
                "PDF 不存在",
                f"找不到 PDF 文件：\n{pdf}\n\n可能已被移动或删除，可以重新爬取。",
                parent=self,
            )
            return
        runtime.open_path(pdf)

    def _open_selected_folder(self):
        record = self._selected_record()
        if not record:
            return
        pdf = self.history.resolve(record.get("pdf", ""))
        folder = Path(pdf).parent if pdf else config_mod.storage_layout(self.cfg)["pdf"]
        if folder.exists():
            runtime.open_path(folder)
        else:
            messagebox.showwarning("提示", f"文件夹不存在：\n{folder}", parent=self)

    def _recrawl_selected(self):
        record = self._selected_record()
        if not record:
            return
        self._show("crawl")
        self.input.set(f"JM{record.get('jm_id')}")
        self._auto_parse()
        self.input.focus_input()

    def _delete_selected(self):
        record = self._selected_record()
        if not record:
            return
        if not messagebox.askyesno("删除记录", f"删除 JM{record.get('jm_id')} 的爬取记录？\n（不会删除已下载的文件）", parent=self):
            return
        self.history.remove(record.get("jm_id"))
        self._refresh_history()

    def _clear_history(self):
        if not self.records:
            return
        if not messagebox.askyesno("清空记录", "确定清空全部爬取记录？\n（不会删除已下载的文件）", parent=self):
            return
        self.history.clear()
        self._refresh_history()

    def _export_history(self):
        if not self.records:
            messagebox.showinfo("提示", "还没有可导出的记录", parent=self)
            return
        target = filedialog.asksaveasfilename(
            parent=self, title="导出爬取记录", defaultextension=".csv",
            initialfile=f"jm_history_{time.strftime('%Y%m%d')}.csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if not target:
            return
        count = self.history.export_csv(target)
        self._append_log("ok", f"已导出 {count} 条记录到 {target}")

    # ================================================================== #
    # 设置动作
    # ================================================================== #
    def _load_settings_to_ui(self):
        cfg = self.cfg
        for key, var in self.vars.items():
            if key == "cookies_avs":
                continue
            try:
                var.set(cfg.get(key))
            except Exception:
                pass
        self.vars["cookies_avs"].set(cfg.get("cookies_avs", ""))
        if hasattr(self, "domains_text"):
            self.domains_text.delete("1.0", "end")
            self.domains_text.insert("1.0", cfg.get("domains", ""))
        self._update_storage_hint()

    def _update_storage_hint(self):
        if not hasattr(self, "storage_hint"):
            return
        try:
            root = config_mod.storage_root(self.cfg)
            self.storage_hint.configure(text=f"实际路径：{root}")
        except Exception:
            self.storage_hint.configure(text="")

    def _browse_storage(self):
        initial = str(config_mod.storage_root(self.cfg))
        chosen = filedialog.askdirectory(parent=self, title="选择存储目录", initialdir=initial)
        if chosen:
            self.vars["storage_dir"].set(chosen)
            self._update_storage_hint()

    def _open_storage(self):
        runtime.open_path(config_mod.storage_root(self.cfg))

    def _collect_settings(self):
        data = dict(self.cfg)
        for key, var in self.vars.items():
            try:
                data[key] = var.get()
            except Exception:
                pass
        if hasattr(self, "domains_text"):
            data["domains"] = self.domains_text.get("1.0", "end-1c").strip()
        return config_mod.sanitize(data)

    def _save_settings(self):
        self.cfg = config_mod.save(self._collect_settings())
        self._load_settings_to_ui()
        self._update_header_path()
        self._append_log("ok", "设置已保存")
        self.status_var.set("设置已保存")

    def _reset_settings(self):
        if not messagebox.askyesno("恢复默认", "将所有设置恢复为默认值？", parent=self):
            return
        self.cfg = config_mod.save(dict(config_mod.DEFAULTS))
        self._load_settings_to_ui()
        self._update_header_path()
        self._append_log("warn", "已恢复默认设置")

    # ================================================================== #
    # 杂项
    # ================================================================== #
    def _update_header_path(self):
        try:
            root = config_mod.storage_root(self.cfg)
            text = str(root)
            if len(text) > 52:
                text = "…" + text[-50:]
            self.header_path.configure(text=f"存储：{text}")
            self.status_path.configure(text=str(root))
            self._update_storage_hint()
        except Exception:
            pass

    def _open_data_dir(self):
        runtime.open_path(runtime.home())

    def _open_log(self):
        runtime.open_path(runtime.log_path())

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _on_close(self):
        if self.running:
            if not messagebox.askyesno(
                "退出",
                "正在爬取中，确定要退出吗？\n\n未完成的任务会保存，下次打开可以继续。",
                parent=self,
            ):
                return
        self._closing = True
        self._persist_queue(force=True, running_as_waiting=True)
        if self.running and self.pipeline:
            self.pipeline.cancel()
        try:
            self.cfg["last_input"] = self.input.get()
            self.cfg["window_geometry"] = self.geometry()
            config_mod.save(self.cfg)
        except Exception:
            pass
        self.destroy()
