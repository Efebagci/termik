"""Tuş adları: pygame olaylarını "ctrl+s", "shift+tab", "enter" gibi dizgelere çevirir,
kısayol satırı için kısa gösterimler üretir.

Türkçe klavyede AltGr, Windows'ta Ctrl+Alt olarak gelir. İkisi birlikte basılıysa tuş
"altgr+q" diye adlandırılır; böylece AltGr+Q (@) ne "q" ne de "ctrl+alt+q" kısayolunu tetikler.
"""

from __future__ import annotations

import pygame

_NAMES = {
    pygame.K_RETURN: "enter", pygame.K_KP_ENTER: "enter", pygame.K_ESCAPE: "escape",
    pygame.K_TAB: "tab", pygame.K_BACKSPACE: "backspace", pygame.K_DELETE: "delete",
    pygame.K_INSERT: "insert", pygame.K_SPACE: "space",
    pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_LEFT: "left", pygame.K_RIGHT: "right",
    pygame.K_HOME: "home", pygame.K_END: "end", pygame.K_PAGEUP: "pageup", pygame.K_PAGEDOWN: "pagedown",
    **{getattr(pygame, f"K_F{i}"): f"f{i}" for i in range(1, 13)},
}
_ALIASES = {
    "esc": "escape", "return": "enter", "del": "delete", "ins": "insert",
    "pgup": "pageup", "pgdn": "pagedown", "control": "ctrl", "cmd": "meta", "win": "meta",
}
_MODS = ("altgr", "ctrl", "alt", "meta", "shift")
_DISPLAY = {
    "enter": "⏎", "escape": "esc", "up": "↑", "down": "↓", "left": "←", "right": "→",
    "backspace": "⌫", "delete": "del", "pageup": "pgup", "pagedown": "pgdn",
}


def normalize(key: str) -> str:
    """'Ctrl+Shift+Z' → 'ctrl+shift+z', 'Esc' → 'escape'. Değiştiricilerin sırası sabitlenir."""
    parts = [_ALIASES.get(p, p) for p in key.strip().lower().split("+") if p]
    if not parts:
        return ""
    *mods, base = parts
    return "+".join([m for m in _MODS if m in mods] + [base])


def from_event(event) -> str:
    """pygame KEYDOWN olayının tuş adı."""
    mod = event.mod
    ctrl, alt = bool(mod & pygame.KMOD_CTRL), bool(mod & pygame.KMOD_ALT)
    base = _NAMES.get(event.key)
    special = base is not None
    if base is None:
        base = pygame.key.name(event.key).lower()
    if ctrl and alt:  # AltGr
        mods = ["altgr"]
    else:
        mods = [name for name, on in (("ctrl", ctrl), ("alt", alt)) if on]
    if mod & pygame.KMOD_META:
        mods.append("meta")
    # harflerde shift karakterin kendisinde görünür; yalnızca özel tuşlarda ya da ctrl/alt ile yazılır
    if mod & pygame.KMOD_SHIFT and (special or mods):
        mods.append("shift")
    return "+".join(mods + [base])


def display(key: str) -> str:
    """Kısayol satırı için kısa gösterim: 'enter' → '⏎', 'ctrl+escape' → 'ctrl+esc'."""
    *mods, base = normalize(key).split("+")
    return "+".join(mods + [_DISPLAY.get(base, base)])
