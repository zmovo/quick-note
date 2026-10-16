"""全局热键保存选中文字，并打开每日记录总览。"""

import ctypes
import queue
import threading
import tkinter as tk
from ctypes import wintypes
from dashboard import Dashboard
from storage import get_topics, save


HOTKEYS = {1: (ord("1"), "今日学习"),
           2: (ord("2"), "待补齐"),
           3: (ord("3"), "打开总览")}  # 共用 Alt
WM_HOTKEY = 0x0312


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", INPUT_UNION)]

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
user32.RegisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT)
user32.GetMessageW.restype = ctypes.c_int
user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.CloseClipboard.restype = wintypes.BOOL
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_long)
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def send_copy_keys(alternate=False):
    """一次提交完整复制快捷键，避免按键之间混入其他输入。"""
    key = 0x2D if alternate else 0x43  # Ctrl+Insert / Ctrl+C
    flags = 1 if alternate else 0  # Insert 是扩展键
    keys = (INPUT * 4)(
        INPUT(1, INPUT_UNION(ki=KEYBDINPUT(0x11, 0, 0, 0, 0))),
        INPUT(1, INPUT_UNION(ki=KEYBDINPUT(key, 0, flags, 0, 0))),
        INPUT(1, INPUT_UNION(ki=KEYBDINPUT(key, 0, flags | 2, 0, 0))),
        INPUT(1, INPUT_UNION(ki=KEYBDINPUT(0x11, 0, 2, 0, 0))),
    )
    return user32.SendInput(4, keys, ctypes.sizeof(INPUT)) == 4


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
                events.put(("save", (message.wParam, user32.GetForegroundWindow())))
    finally:
        for ident in registered:
            user32.UnregisterHotKey(None, ident)


def read_clipboard_text():
    """从系统剪贴板读取 Unicode 文本，剪贴板被占用时交给调用方重试。"""
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def main():
    root = tk.Tk()
    root.withdraw()
    events = queue.Queue()
    threading.Thread(target=hotkey_listener, args=(events,), daemon=True).start()
    toast = None
    hide_job = None
    pending = False
    pending_topic = "未分类"
    source_window = None
    dashboard = Dashboard(root)
    dashboard.show()

    def show_toast(title, detail, success):
        nonlocal toast, hide_job
        if hide_job is not None:
            root.after_cancel(hide_job)
        if toast is not None and toast.winfo_exists():
            toast.destroy()
        toast = tk.Toplevel(root)
        toast.withdraw()
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
        # 提示不能抢走原应用的键盘焦点，否则下一次复制会发给提示窗。
        hwnd = user32.GetAncestor(toast.winfo_id(), 2)
        style = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, style | 0x08000000)
        user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
        hide_job = root.after(5000 if success else 8000, toast.destroy)

    def save_selection(sequence, category_id, attempts=0):
        nonlocal pending
        if user32.GetClipboardSequenceNumber() == sequence:
            if attempts < 40:
                root.after(40, save_selection, sequence, category_id, attempts + 1)
                return
            pending = False
            show_toast("保存失败", "没有复制到文字。请保持文字选中，松开 Alt 后重试。", False)
            return
        try:
            content = read_clipboard_text()
            if content is None:
                if attempts < 40:
                    root.after(50, save_selection, sequence, category_id, attempts + 1)
                    return
                pending = False
                show_toast("保存失败", "系统剪贴板暂时不可读，请稍后重试。", False)
                return
            if not content.strip():
                if attempts < 40:
                    root.after(50, save_selection, sequence, category_id, attempts + 1)
                    return
                pending = False
                show_toast("保存失败", "复制到的内容为空，请保持文字选中后重试。", False)
                return
            category = HOTKEYS[category_id][1]
            with dashboard.lock:
                path = save(category, content, topic=pending_topic)
            pending = False
            dashboard.refresh()
            show_toast(f"✓ 已记入{category}",
                       f"{pending_topic} · {len(content)} 字 · {path.parent.name}/{path.name}", True)
        except Exception as exc:
            pending = False
            show_toast("保存失败", f"{type(exc).__name__}: {exc}", False)

    def send_copy(sequence, category_id, alternate=False):
        nonlocal pending
        if user32.GetForegroundWindow() != source_window:
            pending = False
            show_toast("保存失败", "复制前窗口已切换，请在选中文字的窗口重试。", False)
            return
        if not send_copy_keys(alternate):
            pending = False
            show_toast("保存失败", "系统未能发送复制按键。请检查目标应用权限后重试。", False)
            return
        root.after(180, save_selection, sequence, category_id, 16 if alternate else 0)

    def capture(category_id, attempts=0):
        copy_selection(category_id)

    def copy_selection(category_id, attempts=0):
        nonlocal pending
        # 等 Alt 松开后发送 Ctrl+C，避免混入修饰键。
        if any(user32.GetAsyncKeyState(key) & 0x8000
               for key in (0x12, 0x11, 0x10, HOTKEYS[category_id][0])):
            if attempts < 40:
                root.after(25, copy_selection, category_id, attempts + 1)
            else:
                pending = False
                show_toast("保存失败", "请松开快捷键后重试", False)
            return
        sequence = user32.GetClipboardSequenceNumber()
        root.after(100, send_copy, sequence, category_id)

    def poll():
        nonlocal pending, pending_topic, source_window
        try:
            while True:
                action, value = events.get_nowait()
                if action == "save":
                    value, target = value
                    if value == 3:
                        dashboard.show()
                    elif not pending:
                        pending = True
                        with dashboard.lock:
                            pending_topic = dashboard.topic_filter if dashboard.topic_filter in get_topics() else "未分类"
                        source_window = target
                        capture(value)
                else:
                    show_toast("无法启动热键", value, False)
                    # Keep the dashboard open so the user can still manage records.
                    root.after(5000, poll)
                    return
        except queue.Empty:
            pass
        root.after(30, poll)

    poll()
    root.mainloop()


if __name__ == "__main__":
    main()
