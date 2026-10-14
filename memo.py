"""全局热键保存选中文字，并打开每日记录总览。"""

import ctypes
import queue
import threading
import tkinter as tk
from ctypes import wintypes
from dashboard import Dashboard
from storage import save


HOTKEYS = {1: (ord("1"), "今日学习"),
           2: (ord("2"), "待补齐"),
           3: (ord("3"), "打开总览")}  # 共用 Alt
WM_HOTKEY = 0x0312

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
user32.RegisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT)
user32.GetMessageW.restype = ctypes.c_int
user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.keybd_event.argtypes = (ctypes.c_ubyte, ctypes.c_ubyte, wintypes.DWORD,
                              ctypes.c_void_p)


def hotkey_listener(events):
    # 在线程中接收 Win32 消息，Tk 窗口只由主线程操作。
    registered = []
    message = wintypes.MSG()
    try:
        for ident, (key, category) in HOTKEYS.items():
            if not user32.RegisterHotKey(None, ident, 0x0001 | 0x4000, key):
                events.put(("error", f"{category}热键被占用（错误码 {ctypes.get_last_error()}）"))
                return
            registered.append(ident)
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY and message.wParam in HOTKEYS:
                events.put(("save", message.wParam))
    finally:
        for ident in registered:
            user32.UnregisterHotKey(None, ident)


def main():
    root = tk.Tk()
    root.withdraw()
    events = queue.Queue()
    threading.Thread(target=hotkey_listener, args=(events,), daemon=True).start()
    toast = None
    hide_job = None
    pending = False
    dashboard = Dashboard(root)

    def show_toast(title, detail, success):
        nonlocal toast, hide_job
        if hide_job is not None:
            root.after_cancel(hide_job)
        if toast is not None and toast.winfo_exists():
            toast.destroy()
        toast = tk.Toplevel(root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.attributes("-alpha", 0.97)
        accent = "#4ade80" if success else "#fb7185"
        card = tk.Frame(toast, bg="#20252f", highlightbackground="#3a4250",
                        highlightthickness=1)
        card.pack()
        tk.Frame(card, bg=accent, width=5).pack(side="left", fill="y")
        text = tk.Frame(card, bg="#20252f", padx=18, pady=12)
        text.pack(side="left", fill="both")
        tk.Label(text, text=title, bg="#20252f", fg=accent, anchor="w",
                 font=("Microsoft YaHei UI", 12, "bold"), width=30).pack(anchor="w")
        tk.Label(text, text=detail, bg="#20252f", fg="#d1d5db", anchor="w",
                 font=("Microsoft YaHei UI", 10), wraplength=360).pack(anchor="w", pady=(3, 0))
        toast.update_idletasks()
        x = toast.winfo_screenwidth() - toast.winfo_width() - 28
        y = toast.winfo_screenheight() - toast.winfo_height() - 75
        toast.geometry(f"+{x}+{y}")
        hide_job = root.after(2200 if success else 4000, toast.destroy)

    def save_selection(sequence, category_id, attempts=0):
        nonlocal pending
        if user32.GetClipboardSequenceNumber() == sequence:
            if attempts < 15:
                root.after(30, save_selection, sequence, category_id, attempts + 1)
                return
            pending = False
            show_toast("保存失败", "未复制到选中的文字", False)
            return
        pending = False
        try:
            content = root.clipboard_get()
            if not content.strip():
                show_toast("保存失败", "选中内容没有文字", False)
                return
            category = HOTKEYS[category_id][1]
            path = save(category, content)
            dashboard.refresh()
            show_toast(f"✓ 已记入{category}", f"{len(content)} 字 · {path.parent.name}/{path.name}", True)
        except tk.TclError:
            show_toast("保存失败", "选中内容没有文字", False)
        except OSError as exc:
            show_toast("保存失败", str(exc), False)

    def copy_selection(category_id, attempts=0):
        nonlocal pending
        # 等 Alt 松开后发送 Ctrl+C，避免混入修饰键。
        if user32.GetAsyncKeyState(0x12) & 0x8000:
            if attempts < 40:
                root.after(25, copy_selection, category_id, attempts + 1)
            else:
                pending = False
                show_toast("保存失败", "请松开快捷键后重试", False)
            return
        sequence = user32.GetClipboardSequenceNumber()
        for key, flags in ((0x11, 0), (0x43, 0), (0x43, 2), (0x11, 2)):
            user32.keybd_event(key, 0, flags, None)
        root.after(30, save_selection, sequence, category_id)

    def poll():
        nonlocal pending
        try:
            while True:
                action, value = events.get_nowait()
                if action == "save":
                    if value == 3:
                        dashboard.show()
                    elif not pending:
                        pending = True
                        copy_selection(value)
                else:
                    show_toast("无法启动热键", value, False)
                    root.after(4000, root.destroy)
                    return
        except queue.Empty:
            pass
        root.after(30, poll)

    poll()
    root.mainloop()


if __name__ == "__main__":
    main()
