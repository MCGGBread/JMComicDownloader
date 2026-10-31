"""深色主题：颜色、字体、ttk 样式。"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

C = {
    "bg": "#0e1014",
    "panel": "#141821",
    "card": "#1a1f29",
    "card2": "#222835",
    "input": "#12161e",
    "border": "#2a3140",
    "border2": "#3b4457",
    "text": "#e9ecf3",
    "muted": "#8d95a8",
    "dim": "#5d6577",
    "accent": "#ff4d6d",
    "accent_dark": "#e03a5a",
    "accent_soft": "#331a23",
    "ok": "#4ade80",
    "warn": "#fbbf24",
    "err": "#f87171",
    "info": "#60a5fa",
    "sel": "#2b3344",
}

FAMILY = "Microsoft YaHei UI"
MONO = "Consolas"

FS = {
    "h1": 17,
    "h2": 12,
    "body": 10,
    "small": 9,
    "tiny": 8,
}


def ui_font(size=10, bold=False):
    return (FAMILY, size, "bold") if bold else (FAMILY, size)


def mono_font(size=9, bold=False):
    return (MONO, size, "bold") if bold else (MONO, size)


def apply_theme(root: tk.Misc) -> ttk.Style:
    root.configure(bg=C["bg"])

    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(name).configure(family=FAMILY, size=FS["body"])
        except Exception:
            pass
    try:
        tkfont.nametofont("TkFixedFont").configure(family=MONO, size=9)
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(
        ".",
        background=C["bg"],
        foreground=C["text"],
        fieldbackground=C["input"],
        bordercolor=C["border"],
        lightcolor=C["card"],
        darkcolor=C["card"],
        troughcolor=C["panel"],
        focuscolor=C["accent"],
        selectbackground=C["sel"],
        selectforeground=C["text"],
        font=ui_font(FS["body"]),
    )

    # Treeview
    style.configure(
        "Treeview",
        background=C["card"],
        fieldbackground=C["card"],
        foreground=C["text"],
        borderwidth=0,
        relief="flat",
        rowheight=30,
        font=ui_font(FS["body"]),
    )
    style.configure(
        "Treeview.Heading",
        background=C["panel"],
        foreground=C["muted"],
        relief="flat",
        borderwidth=0,
        padding=(8, 7),
        font=ui_font(FS["small"], bold=True),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", C["card2"])],
        foreground=[("active", C["text"])],
    )
    style.map(
        "Treeview",
        background=[("selected", C["sel"])],
        foreground=[("selected", C["text"])],
    )
    try:
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    except Exception:
        pass

    # 滚动条
    for orient in ("Vertical", "Horizontal"):
        style.configure(
            f"{orient}.TScrollbar",
            background=C["card2"],
            troughcolor=C["panel"],
            bordercolor=C["panel"],
            arrowcolor=C["muted"],
            relief="flat",
            borderwidth=0,
            width=10,
        )
        style.map(
            f"{orient}.TScrollbar",
            background=[("active", C["border2"]), ("pressed", C["border2"])],
        )

    # 进度条
    style.configure(
        "Accent.Horizontal.TProgressbar",
        background=C["accent"],
        troughcolor=C["card2"],
        bordercolor=C["card2"],
        lightcolor=C["accent"],
        darkcolor=C["accent"],
        thickness=6,
        borderwidth=0,
    )

    # 下拉框
    style.configure(
        "TCombobox",
        fieldbackground=C["card2"],
        background=C["card2"],
        foreground=C["text"],
        arrowcolor=C["muted"],
        bordercolor=C["border"],
        lightcolor=C["card2"],
        darkcolor=C["card2"],
        padding=(8, 6),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", C["card2"]), ("disabled", C["card"])],
        foreground=[("readonly", C["text"]), ("disabled", C["dim"])],
        selectbackground=[("readonly", C["card2"])],
        selectforeground=[("readonly", C["text"])],
        bordercolor=[("focus", C["accent"])],
    )
    style.configure(
        "TCheckbutton",
        background=C["card"],
        foreground=C["text"],
        indicatorbackground=C["input"],
        indicatorforeground=C["accent"],
        bordercolor=C["border2"],
        focuscolor=C["card"],
        padding=(0, 4),
        font=ui_font(FS["body"]),
    )
    style.map(
        "TCheckbutton",
        background=[("active", C["card"])],
        foreground=[("active", C["text"])],
        indicatorbackground=[("selected", C["accent"]), ("active", C["input"])],
        indicatorforeground=[("selected", C["text"])],
    )

    # 数字输入框
    style.configure(
        "Dark.TSpinbox",
        fieldbackground=C["input"],
        background=C["input"],
        foreground=C["text"],
        arrowcolor=C["muted"],
        bordercolor=C["border"],
        lightcolor=C["input"],
        darkcolor=C["input"],
        insertcolor=C["text"],
        padding=(6, 4),
    )
    style.map(
        "Dark.TSpinbox",
        fieldbackground=[("readonly", C["input"])],
        foreground=[("disabled", C["dim"])],
        arrowcolor=[("active", C["text"]), ("disabled", C["dim"])],
        bordercolor=[("focus", C["accent"])],
    )

    root.option_add("*TCombobox*Listbox.background", C["card2"])
    root.option_add("*TCombobox*Listbox.foreground", C["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.font", ui_font(FS["body"]))
    root.option_add("*Font", ui_font(FS["body"]))

    return style
