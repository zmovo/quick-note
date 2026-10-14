"""以每日笔记为中心的总览；趋势按需展开。"""
import tkinter as tk
from tkinter import ttk
from datetime import date

from storage import load_days

BG, INK, MUTED = "#f7f8fa", "#20242c", "#818894"
FONT = "Microsoft YaHei UI"


def label(parent, text, size=11, color=INK, bold=False, bg=BG):
    return tk.Label(parent, text=text, bg=bg, fg=color,
                    font=(FONT, size, "bold" if bold else "normal"), anchor="w")


def button(parent, text, command):
    return tk.Button(parent, text=text, command=command, bg="white", fg="#505866",
                     activebackground="#edf0f5", relief="flat", bd=0, padx=12, pady=6,
                     cursor="hand2", font=(FONT, 10))


class RecordColumn:
    def __init__(self, parent, title, color, column):
        self.frame = tk.Frame(parent, bg=BG)
        self.frame.grid(row=0, column=column, sticky="nsew", padx=(0, 10) if column == 0 else (10, 0))
        head = tk.Frame(self.frame, bg=BG)
        head.pack(fill="x", pady=(0, 4))
        label(head, title, 15, color, True).pack(side="left")
        self.count = label(head, "0", 11, MUTED)
        self.count.pack(side="left", padx=10)
        body = tk.Frame(self.frame, bg=BG)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0, width=1)
        scrollbar = ttk.Scrollbar(body, command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.cards = tk.Frame(self.canvas, bg=BG)
        self.item = self.canvas.create_window(0, 0, window=self.cards, anchor="nw")
        self.canvas.bind("<Configure>", self.resize)
        self.cards.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<MouseWheel>", self.scroll)
        self.areas = []

    def scroll(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    def resize(self, event):
        self.canvas.itemconfigure(self.item, width=event.width)
        self.canvas.after_idle(self.fit_text)

    def fit_text(self):
        for area in self.areas:
            if area.winfo_exists() and area.winfo_width() > 100:
                lines = area.count("1.0", "end-1c", "displaylines")
                height = max(1, lines[0] if lines else 1)
                if int(area.cget("height")) != height:
                    area.configure(height=height)

    def display(self, entries):
        for child in self.cards.winfo_children():
            child.destroy()
        self.areas = []
        self.count.configure(text=str(len(entries)))
        if not entries:
            label(self.cards, "这一天还没有记录", 11, MUTED).pack(anchor="w", pady=24)
        for stamp, content in entries:
            card = tk.Frame(self.cards, bg="white", highlightbackground="#e6e9ee", highlightthickness=1)
            card.pack(fill="x", pady=(0, 12), padx=(0, 4))
            top = tk.Frame(card, bg="white", padx=16, pady=8)
            top.pack(fill="x")
            label(top, stamp[11:], 10, MUTED, bg="white").pack(side="left")
            copy = button(top, "复制", lambda value=content: self.copy(value))
            copy.configure(padx=4, pady=0)
            copy.pack(side="right")
            area = tk.Text(card, wrap="word", font=(FONT, 12), bg="white", fg=INK,
                           bd=0, relief="flat", highlightthickness=0,
                           highlightbackground="white", highlightcolor="white",
                           padx=16, pady=4, spacing3=6, width=1, height=1,
                           selectbackground="#dce8fb", cursor="xterm")
            area.insert("1.0", content)
            area.configure(state="disabled")
            area.pack(fill="x", pady=(0, 12))
            self.areas.append(area)
            area.bind("<Configure>", lambda _, widget=area: widget.after_idle(self.fit_text))
            for widget in (card, top, area):
                widget.bind("<MouseWheel>", self.scroll)
        self.canvas.yview_moveto(0)
        self.canvas.after(80, self.fit_text)

    def copy(self, content):
        self.frame.clipboard_clear()
        self.frame.clipboard_append(content)


class Dashboard:
    def __init__(self, root):
        self.window = tk.Toplevel(root)
        self.window.title("碎片记录 · 每日总览")
        width = min(1120, self.window.winfo_screenwidth() - 60)
        height = min(740, self.window.winfo_screenheight() - 100)
        self.window.geometry(f"{width}x{height}+{(self.window.winfo_screenwidth()-width)//2}+35")
        self.window.minsize(820, 500)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.window.withdraw)
        self.window.bind("<Escape>", lambda _: self.window.withdraw())
        self.days, self.selected_day = {}, None
        self.trend_visible = False

        sidebar = tk.Frame(self.window, bg="white", width=190, padx=18, pady=24)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        label(sidebar, "碎片记录", 17, bold=True, bg="white").pack(anchor="w")
        label(sidebar, "日期", 10, MUTED, bg="white").pack(anchor="w", pady=(28, 8))
        self.date_list = tk.Listbox(sidebar, bg="white", fg="#555d69", font=(FONT, 12),
                                    bd=0, highlightthickness=0, selectbackground="#edf2fc",
                                    selectforeground="#285fba", activestyle="none", exportselection=False)
        self.date_list.pack(fill="both", expand=True)
        self.date_list.bind("<<ListboxSelect>>", self.select_date)
        self.help_icon = tk.Canvas(sidebar, width=34, height=34, bg="white", highlightthickness=0,
                                   cursor="hand2")
        self.help_icon.pack(anchor="w", pady=(14, 0))
        self.help_icon.create_oval(3, 3, 31, 31, outline="#aeb6c2", width=1.5)
        self.help_icon.create_text(17, 17, text="?", fill="#596577", font=(FONT, 13, "bold"))
        self.help_icon.bind("<Button-1>", lambda _: self.show_shortcuts())

        main = tk.Frame(self.window, bg=BG, padx=28, pady=22)
        main.pack(side="left", fill="both", expand=True)
        header = tk.Frame(main, bg=BG)
        header.pack(fill="x")
        self.day_title = label(header, "每日笔记", 22, bold=True)
        self.day_title.pack(side="left")
        self.icon_button(header, "refresh", self.refresh, "刷新记录").pack(side="right", padx=(8, 0))
        self.icon_button(header, "trend", self.toggle_trend, "查看学习趋势").pack(side="right")

        self.chart_box = tk.Frame(main, bg="white", padx=12, pady=8)
        label(self.chart_box, "每日记录条数", 10, MUTED, bg="white").pack(anchor="w")
        self.chart = tk.Canvas(self.chart_box, bg="white", height=140, highlightthickness=0)
        self.chart.pack(fill="x")
        scrollbar = ttk.Scrollbar(self.chart_box, orient="horizontal", command=self.chart.xview)
        scrollbar.pack(fill="x")
        self.chart.configure(xscrollcommand=scrollbar.set)
        self.chart.bind("<Configure>", lambda _: self.draw_chart())
        self.columns = tk.Frame(main, bg=BG)
        self.columns.pack(fill="both", expand=True)
        self.columns.grid_columnconfigure((0, 1), weight=1, uniform="notes")
        self.columns.grid_rowconfigure(0, weight=1)
        self.panels = {
            "今日学习": RecordColumn(self.columns, "需要复习", "#315e9b", 0),
            "待补齐": RecordColumn(self.columns, "待补全", "#97713a", 1),
        }
        self.refresh()

    def icon_button(self, parent, kind, command, tooltip):
        icon = tk.Canvas(parent, width=38, height=38, bg="white", highlightthickness=0,
                         cursor="hand2")
        color = "#596577"
        if kind == "trend":
            icon.create_line(9, 28, 9, 10, fill=color, width=1.5)
            icon.create_line(9, 28, 30, 28, fill=color, width=1.5)
            icon.create_line(12, 23, 18, 18, 23, 21, 29, 11, fill="#315e9b", width=2,
                             smooth=True)
            for x, y in ((12, 23), (18, 18), (23, 21), (29, 11)):
                icon.create_oval(x-1.5, y-1.5, x+1.5, y+1.5, fill="#315e9b", outline="")
        else:
            icon.create_text(19, 18, text="↻", fill=color, font=("Segoe UI Symbol", 23))
        icon.bind("<Button-1>", lambda _: command())
        icon.bind("<Enter>", lambda _: icon.configure(bg="#edf0f5"))
        icon.bind("<Leave>", lambda _: icon.configure(bg="white"))
        icon.bind("<Enter>", lambda event: self.show_tip(event, tooltip), add="+")
        icon.bind("<Leave>", lambda _: self.hide_tip(), add="+")
        return icon

    def show_tip(self, event, text):
        self.hide_tip()
        self.tip = tk.Toplevel(self.window)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        tk.Label(self.tip, text=text, bg="#303846", fg="white", padx=8, pady=4,
                 font=(FONT, 9)).pack()
        self.tip.geometry(f"+{event.x_root+10}+{event.y_root-28}")

    def hide_tip(self):
        if getattr(self, "tip", None) and self.tip.winfo_exists():
            self.tip.destroy()

    def show_shortcuts(self):
        if getattr(self, "shortcut_window", None) and self.shortcut_window.winfo_exists():
            self.shortcut_window.deiconify()
            self.shortcut_window.lift()
            return
        popup = self.shortcut_window = tk.Toplevel(self.window)
        popup.title("快捷键")
        popup.transient(self.window)
        popup.resizable(False, False)
        panel = tk.Frame(popup, bg="white", padx=20, pady=16)
        panel.pack(fill="both", expand=True)
        for key, action in (("Alt+1", "记录需要复习的内容"), ("Alt+2", "记录待补全的内容"),
                            ("Alt+3", "打开总览"), ("Esc", "关闭总览")):
            row = tk.Frame(panel, bg="white")
            row.pack(fill="x", pady=4)
            label(row, key, 10, "#315e9b", True, "white").pack(side="left", padx=(0, 16))
            label(row, action, 10, bg="white").pack(side="left")
        popup.bind("<Escape>", lambda _: popup.destroy())
        popup.geometry(f"+{self.help_icon.winfo_rootx()+40}+{self.help_icon.winfo_rooty()-100}")

    def show(self):
        if self.trend_visible:
            self.toggle_trend()
        self.refresh()
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def toggle_trend(self):
        self.trend_visible = not self.trend_visible
        if self.trend_visible:
            self.chart_box.pack(fill="x", before=self.columns, pady=(0, 20))
            self.draw_chart()
        else:
            self.chart_box.pack_forget()

    def refresh(self):
        try:
            self.days = load_days()
        except (OSError, UnicodeError) as exc:
            self.day_title.configure(text="读取失败")
            return
        self.date_list.delete(0, "end")
        for day in self.days:
            self.date_list.insert("end", f"  {day[5:].replace('-', ' / ')}" + ("  今天" if day == date.today().isoformat() else f"  {day[:4]}"))
        if self.selected_day not in self.days:
            self.selected_day = next(iter(self.days), None)
        if self.selected_day:
            index = list(self.days).index(self.selected_day)
            self.date_list.selection_set(index)
            self.date_list.see(index)
        self.display_day()
        if self.trend_visible:
            self.draw_chart()

    def select_date(self, _=None):
        selection = self.date_list.curselection()
        if selection:
            self.selected_day = list(self.days)[selection[0]]
            self.display_day()

    def display_day(self):
        day = self.selected_day
        self.day_title.configure(text=day.replace("-", " / ") if day else "每日笔记")
        groups = self.days.get(day, {"今日学习": [], "待补齐": []})
        for category, panel in self.panels.items():
            panel.display(groups[category])

    def draw_chart(self):
        canvas = self.chart
        canvas.delete("all")
        days = sorted(self.days)
        width = max(canvas.winfo_width(), len(days) * 70 + 60)
        canvas.configure(scrollregion=(0, 0, width, 140))
        canvas.create_text(12, 12, text="需要复习", fill="#315e9b", anchor="w")
        canvas.create_text(95, 12, text="待补全", fill="#97713a", anchor="w")
        if not days:
            canvas.create_text(180, 70, text="有记录后显示趋势", fill=MUTED)
            return
        maximum = max(1, *(len(v) for groups in self.days.values() for v in groups.values()))
        canvas.create_line(35, 115, width - 20, 115, fill="#e6e9ee")
        for category, color in (("今日学习", "#315e9b"), ("待补齐", "#97713a")):
            points = []
            for index, day in enumerate(days):
                x = 50 + index * max(70, (width - 100) // max(1, len(days) - 1))
                count = len(self.days[day][category])
                y = 115 - count / maximum * 75
                points.extend((x, y))
                canvas.create_oval(x-4, y-4, x+4, y+4, fill=color, outline="white")
                if count:
                    canvas.create_text(x, y-12, text=str(count), fill=color)
                if category == "今日学习":
                    canvas.create_text(x, 130, text=day[5:], fill=MUTED)
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=2)
        canvas.xview_moveto(1)
