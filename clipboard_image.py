"""只读 Windows 剪贴板图片；不清空剪贴板，不模拟按键。"""
import ctypes
import struct
from ctypes import wintypes


def dib_to_bmp(data):
    """给 CF_DIB / CF_DIBV5 补充 BMP 文件头，保留原像素。"""
    if len(data) < 40:
        raise ValueError("剪贴板位图不完整")
    size, width, height, planes, bits, compression = struct.unpack_from('<IiiHHI', data)
    if size not in (40, 108, 124) or size > len(data) or width <= 0 or not height or planes != 1:
        raise ValueError("不支持的剪贴板位图")
    if bits not in (1, 4, 8, 16, 24, 32) or compression not in (0, 3, 6):
        raise ValueError("不支持的位图编码")
    colors = struct.unpack_from('<I', data, 32)[0] or ((1 << bits) if bits <= 8 else 0)
    masks = (16 if compression == 6 else 12) if size == 40 and compression in (3, 6) else 0
    offset = size + masks + colors * 4
    if size == 124:
        profile, length = struct.unpack_from('<II', data, 112)
        if profile and profile <= offset:
            offset = max(offset, profile + length)
    pixels = ((width * bits + 31) // 32) * 4 * abs(height)
    if offset + pixels > len(data):
        raise ValueError("剪贴板位图像素不完整")
    return struct.pack('<2sIHHI', b'BM', len(data) + 14, 0, 0, offset + 14) + data


def read_image():
    """返回 (扩展名, 数据) 或 None；剪贴板占用时抛出 BlockingIOError。"""
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.RegisterClipboardFormatW.argtypes = (wintypes.LPCWSTR,)
    user.RegisterClipboardFormatW.restype = wintypes.UINT
    user.GetClipboardData.argtypes = (wintypes.UINT,)
    user.GetClipboardData.restype = wintypes.HANDLE
    kernel.GlobalSize.argtypes = (wintypes.HGLOBAL,)
    kernel.GlobalSize.restype = ctypes.c_size_t
    kernel.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    if not user.OpenClipboard(None):
        raise BlockingIOError("剪贴板暂时被占用")
    try:
        for format_id, extension in ((user.RegisterClipboardFormatW('PNG'), '.png'), (17, '.bmp'), (8, '.bmp')):
            handle = user.GetClipboardData(format_id)
            if not handle:
                continue
            size = kernel.GlobalSize(handle)
            if not size or size > 64 * 1024 * 1024:
                raise ValueError("图片为空或超过 64 MB")
            pointer = kernel.GlobalLock(handle)
            if not pointer:
                raise BlockingIOError("剪贴板图片暂时不可读")
            try:
                data = ctypes.string_at(pointer, size)
            finally:
                kernel.GlobalUnlock(handle)
            if extension == '.png':
                if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                    continue
            else:
                data = dib_to_bmp(data)
            return extension, data
        return None
    finally:
        user.CloseClipboard()
