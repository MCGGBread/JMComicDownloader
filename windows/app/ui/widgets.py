"""通用控件封装（tk.Button 扁平化、带占位符的输入框、可滚动容器等）。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import C, FS, ui_font


def card(parent, **kwargs):
    return tk.Frame(
        parent,
        bg=kwargs.pop("bg", C["card"]),
        highlightthickness=1,
        highlightbackground=C["border"],
        highlightcolor=C["border"],
        bd=0,
        **kwargs,
    )


def label(parent, text="", size=FS["body"], bold=False, fg=None, bg=None, **kwargs):
    return tk.Label(
        parent,
        text=text,
        bg=bg or parent["bg"],
        fg=fg or C["text"],
        font=ui_font(size, bold),
        bd=0,
        **kwargs,
    )


def hline(parent, color=None):
    return tk.Frame(parent, bg=color or C["border"], height=1)


def button(parent, text, command=None, kind="ghost", padx=14, pady=6, size=FS["body"],
           bold=None, width=None, bg=None):
    palette = {
        "primary": (C["accent"], "#ffffff", C["accent_dark"], "#ffffff", C["accent"], 0),
        "ghost": (C["card2"], C["text"], C["border2"], C["text"], C["border"], 1),
        "subtle": (C["card"], C["muted"], C["card2"], C["text"], C["border"], 1),
        "danger": (C["accent_soft"], C["accent"], "#47202b", C["text"], C["accent"], 1),
    }
    normal_bg, fg, hover_bg, hover_fg, border, thickness = palette.get(kind, palette["ghost"])
    if bg:
        normal_bg = bg
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=normal_bg,
        fg=fg,
        activebackground=hover_bg,
        activeforeground=hover_fg,
        relief="flat",
        bd=0,
        highlightthickness=thickness,
        highlightbackground=border,
        highlightcolor=border,
        padx=padx,
        pady=pady,
        cursor="hand2",
        disabledforeground=C["dim"],
        takefocus=0,
        font=ui_font(size, bold if bold is not None else kind == "primary"),
    )
    if width:
        btn.configure(width=width)

    def on_enter(_event):
        if str(btn["state"]) != "disabled":
            btn.configure(bg=hover_bg, fg=hover_fg)

    def on_leave(_event):
        if str(btn["state"]) != "disabled":
            btn.configure(bg=normal_bg, fg=fg)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


def chip(parent, text):
    return tk.Label(
        parent,
        text=text,
        bg=C["accent_soft"],
        fg=C["accent"],
        font=ui_font(FS["small"]),
        padx=8,
        pady=2,
        bd=0,
    )


class InputText(tk.Frame):
    """带占位符的多行输入框。"""

    def __init__(self, parent, height=7, placeholder="", **kwargs):
        super().__init__(parent, bg=kwargs.pop("bg", C["card"]), bd=0)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._placeholder = placeholder
        self._is_placeholder = False

        self.text = tk.Text(
            self,
            height=height,
            bg=C["input"],
            fg=C["text"],
            insertbackground=C["accent"],
            selectbackground=C["sel"],
            selectforeground=C["text"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
            font=ui_font(FS["body"]),
            padx=12,
            pady=10,
            wrap="word",
            undo=True,
            spacing1=1,
            spacing3=3,
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=self.vsb.set)

        self.text.tag_configure("ph", foreground=C["dim"])
        self.text.bind("<FocusIn>", self._on_focus_in)
        self.text.bind("<FocusOut>", self._on_focus_out)
        self._show_placeholder()

    # ------------------------------------------------------------------ #
    def _show_placeholder(self):
        if not self._placeholder:
            return
        if not self.text.get("1.0", "end-1c").strip():
            self.text.delete("1.0", "end")
            self.text.insert("1.0", self._placeholder, "ph")
            self._is_placeholder = True

    def _on_focus_in(self, _event=None):
        if self._is_placeholder:
            self.text.delete("1.0", "end")
            self.text.tag_remove("ph", "1.0", "end")
            self._is_placeholder = False

    def _on_focus_out(self, _event=None):
        if not self.text.get("1.0", "end-1c").strip():
            self._show_placeholder()

    # ------------------------------------------------------------------ #
    def get(self) -> str:
        if self._is_placeholder:
            return ""
        return self.text.get("1.0", "end-1c")

    def set(self, value: str) -> None:
        self.text.delete("1.0", "end")
        self.text.tag_remove("ph", "1.0", "end")
        self._is_placeholder = False
        if value:
            self.text.insert("1.0", value)
        else:
            self._show_placeholder()

    def focus_input(self):
        self.text.focus_set()


class CheckBox(tk.Frame):
    """自绘复选框（ttk 在 clam 主题下的指示器配色不可用）。"""

    def __init__(self, parent, text, variable, bg=None, fg=None, size=FS["body"]):
        bg = bg or parent["bg"]
        super().__init__(parent, bg=bg, cursor="hand2")
        self.var = variable
        self._bg = bg
        self.canvas = tk.Canvas(self, width=17, height=17, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(side="left")
        self.label = tk.Label(
            self, text=text, bg=bg, fg=fg or C["text"], font=ui_font(size), cursor="hand2"
        )
        self.label.pack(side="left", padx=(7, 0))
        self._draw()
        for widget in (self, self.canvas, self.label):
            widget.bind("<Button-1>", self._toggle)
        try:
            self.var.trace_add("write", lambda *_a: self._draw())
        except Exception:
            pass

    def _draw(self):
        self.canvas.delete("all")
        on = bool(self.var.get())
        fill = C["accent"] if on else C["input"]
        outline = C["accent"] if on else C["border2"]
        self.canvas.create_rectangle(1, 1, 16, 16, fill=fill, outline=outline)
        if on:
            self.canvas.create_line(
                4.5, 8.5, 7.5, 11.5, 12.5, 5.5,
                fill="#ffffff", width=2, capstyle="round", joinstyle="round",
            )

    def _toggle(self, _event=None):
        self.var.set(not bool(self.var.get()))


class ProgressBar(tk.Frame):
    """自绘细进度条（ttk 在 clam 主题下配色不可控）。"""

    def __init__(self, parent, width=200, height=6, bg=None, fill=None, track=None):
        bg = bg or C["card"]
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        self._bar_w = width
        self._bar_h = height
        self.canvas = tk.Canvas(
            self, width=width, height=height, bg=bg, highlightthickness=0, bd=0
        )
        self.canvas.pack()
        self.canvas.create_rectangle(
            0, 0, width, height, fill=track or C["card2"], outline=""
        )
        self._bar = self.canvas.create_rectangle(
            0, 0, 0, height, fill=fill or C["accent"], outline=""
        )

    def set(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        value = max(0.0, min(100.0, value))
        self.canvas.coords(self._bar, 0, 0, self._bar_w * value / 100.0, self._bar_h)


class ScrollFrame(tk.Frame):
    """垂直滚动容器（用于设置页）。"""

    def __init__(self, parent, bg=None):
        bg = bg or C["bg"]
        super().__init__(parent, bg=bg, bd=0)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._win, width=event.width)

    def _bind_wheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        if self.canvas.winfo_height() >= self.inner.winfo_reqheight():
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
