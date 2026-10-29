"""İşletim sistemiyle ilgili küçük işler: ekran ölçeği, pencere simgesi, modal pencere kilidi,
farenin masaüstündeki konumu.

Windows'a özgü kısımlar ctypes ile yapılır; başka sistemlerde ya da bir şey ters giderse sessizce
pygame'in genel yoluna düşülür.
"""

from __future__ import annotations

import struct
import sys
from typing import Callable

import pygame

_WIN = sys.platform == "win32"
_user32 = None
_icons: dict[int, tuple[int, int]] = {}  # pencere (HWND) → (küçük, büyük) simge; değişince eskiler silinir


def _lib():
    """Kendi user32 kopyamız: argtypes ayarları başka kütüphanelerinkine karışmasın."""
    global _user32
    if _user32 is None:
        import ctypes
        from ctypes import wintypes as w

        u = ctypes.WinDLL("user32", use_last_error=True)
        u.EnableWindow.argtypes = (w.HWND, w.BOOL)
        u.SendMessageW.argtypes = (w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        u.SendMessageW.restype = w.LPARAM
        u.CreateIconFromResourceEx.argtypes = (ctypes.c_char_p, w.DWORD, w.BOOL, w.DWORD, ctypes.c_int,
                                               ctypes.c_int, w.UINT)
        u.CreateIconFromResourceEx.restype = w.HICON
        u.DestroyIcon.argtypes = (w.HICON,)
        u.GetSystemMetrics.argtypes = (ctypes.c_int,)
        set_long = getattr(u, "SetWindowLongPtrW", None) or u.SetWindowLongW
        set_long.argtypes = (w.HWND, ctypes.c_int, ctypes.c_void_p)
        set_long.restype = ctypes.c_void_p
        _user32 = u
    return _user32


def hwnd(window: pygame.Window | None) -> int:
    """Pencerenin Windows tanıtıcısı (HWND); Windows değilse ya da bilinmiyorsa 0."""
    if not _WIN or window is None:
        return 0
    try:
        return int(window.handle or 0)
    except (pygame.error, AttributeError, TypeError, ValueError):
        return 0


def dpi_scale() -> float:
    """Windows ekran ölçeği (%125 → 1.25); pygame.init()'ten sonra çağrılmalı."""
    if not _WIN:
        return 1.0
    try:
        import ctypes
        return ctypes.windll.user32.GetDpiForSystem() / 96
    except (AttributeError, OSError):
        return 1.0


def set_enabled(window: pygame.Window, enabled: bool) -> None:
    """Pencereyi girdiye aç ya da kapat. Windows'ta kapalı pencereye tıklamak, sahip olduğu modal
    pencereyi öne getirir; öbür sistemlerde bu işi uygulama kendisi yapar."""
    handle = hwnd(window)
    if handle:
        try:
            _lib().EnableWindow(handle, bool(enabled))
        except OSError:
            pass


def set_owner(window: pygame.Window, owner: pygame.Window) -> None:
    """window'u owner'ın üstünde tut: Windows'ta sahiplik (birlikte küçülür, görev çubuğunda ayrı
    düğmesi olmaz). Modal pencereler için."""
    handle, owner_handle = hwnd(window), hwnd(owner)
    if handle and owner_handle:
        try:
            set_long = getattr(_lib(), "SetWindowLongPtrW", None) or _lib().SetWindowLongW
            set_long(handle, -8, owner_handle)  # GWLP_HWNDPARENT
        except OSError:
            pass


def set_icon(window: pygame.Window, make: Callable[[int], pygame.Surface]) -> None:
    """Pencere simgesini kur; make(boyut) o boyutta çizilmiş bir simge verir.

    Windows başlık çubuğu ve görev çubuğu için farklı boyut ister; tek bir resmi küçültmek kenarları
    tırtıklı yapar. Bu yüzden orada iki boyut ayrı ayrı çizilir. Öbür sistemlerde tek resim yeter.
    """
    handle = hwnd(window)
    if handle:
        try:
            u = _lib()
            small = _hicon(make(u.GetSystemMetrics(49) or 16))  # SM_CXSMICON
            big = _hicon(make(u.GetSystemMetrics(11) or 32))    # SM_CXICON
            if small and big:
                u.SendMessageW(handle, 0x80, 0, small)  # WM_SETICON, ICON_SMALL
                u.SendMessageW(handle, 0x80, 1, big)    # ICON_BIG
                for old in _icons.pop(handle, ()):
                    u.DestroyIcon(old)
                _icons[handle] = (small, big)
                return
        except (OSError, ValueError, pygame.error):
            pass
    window.set_icon(make(64))


def forget(window: pygame.Window) -> None:
    """Pencere kapanırken ona ait simgeleri sil."""
    handle = hwnd(window)
    if handle and handle in _icons:
        for icon in _icons.pop(handle):
            _lib().DestroyIcon(icon)


def _hicon(surface: pygame.Surface) -> int:
    """32 bit (saydamlıklı) Windows simgesi: SDL'in de kullandığı bellekte simge kaynağı yolu."""
    w, h = surface.get_size()
    xor = pygame.image.tobytes(pygame.transform.flip(surface, False, True), "BGRA")  # satırlar alttan üste
    mask = bytes((w + 31) // 32 * 4 * h)  # saydamlık alfa kanalında; VE maskesi boş
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor) + len(mask), 0, 0, 0, 0)
    data = header + xor + mask
    return _lib().CreateIconFromResourceEx(data, len(data), True, 0x00030000, w, h, 0) or 0


def mouse_in(window: pygame.Window) -> tuple[int, int] | None:
    """Farenin pencere içindeki konumu, pencere fare olayı almıyor olsa da (dosya bırakılırken)."""
    try:
        mx, my = pygame.mouse.get_pos(desktop=True)
        wx, wy = window.position
    except (pygame.error, TypeError, AttributeError):
        return None
    return mx - wx, my - wy
