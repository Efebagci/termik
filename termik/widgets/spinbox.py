"""Sayı alanı."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

import pygame

from ..draw import Painter
from ..events import Blur, Key, Message, MouseDown, MouseMove, MouseScroll, TextInput
from ..reactive import reactive
from ..text import Style
from ..theme import mix
from ..widget import Widget, action

_BOLD = Style(bold=True)


def _places(x: float) -> int:
    """Ondalık basamak sayısı: 0.25 → 2, 3 → 0."""
    try:
        return max(0, -Decimal(str(x)).normalize().as_tuple().exponent)
    except (InvalidOperation, TypeError):
        return 0


class Spinbox(Widget):
    """Sayı alanı: ↑/↓ (ya da tekerlek, − ve + düğmeleri) bir adım, PgUp/PgDn on adım, Home/End
    sınırlar. Rakam yazınca değer baştan yazılır; ⏎ ya da odaktan çıkmak onaylar, Esc vazgeçer.
    Ondalık ayırıcı nokta ya da virgül olabilir. Değer min ve max arasında tutulur. Spinbox.Changed
    iletir.

        Spinbox(12, min=1, max=99)
        Spinbox(0.5, min=0, max=1, step=0.05, format="{:.0%}")

    Görünüşü temadaki spin belirtecinden gelir: bracket [ − 12 + ] · arrows ◂ 12 ▸ · stacked sağda ▴▾.
    """

    default_width = "auto"
    default_height = "auto"
    can_focus = True
    accepts_text = True
    cursor = "hand"
    bind_value = "value"
    value = reactive(0)

    class Changed(Message):
        def __init__(self, spinbox: Spinbox, value: float) -> None:
            super().__init__()
            self.spinbox, self.value = spinbox, value

    def __init__(self, value: float = 0, *, min: float | None = None, max: float | None = None, step: float = 1,
                 format: str | None = None, on_change: Callable | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        if min is not None and max is not None and not max > min:
            raise ValueError("Spinbox: max, min'den büyük olmalı")
        if not step > 0:
            raise ValueError("Spinbox: step sıfırdan büyük olmalı")
        self.minimum, self.maximum, self.step = min, max, step
        self._places = sorted(_places(v) for v in (value, min, max, step) if v is not None)[-1]  # min/max gölgeli
        self.format = format or f"{{:.{self._places}f}}"
        self.on_change = on_change
        self._buffer: str | None = None  # yazılırken düzenlenen metin
        self._minus = self._plus = pygame.Rect(0, 0, 0, 0)  # son çizimde düğmelerin yeri (fare için)
        self._mouse: tuple[int, int] | None = None
        self.value = self._clamp(value)

    # ── değer ────────────────────────────────────────────

    def _clamp(self, value: float) -> float:
        if self.minimum is not None and value < self.minimum:
            value = self.minimum
        if self.maximum is not None and value > self.maximum:
            value = self.maximum
        value = round(value, self._places)
        return int(value) if self._places == 0 else value

    def set(self, value: float) -> None:
        self.value = self._clamp(value)

    def watch_value(self, value: float) -> None:
        self.post_message(Spinbox.Changed(self, value))
        self._sync_bind()
        if self.on_change is not None:
            self._call(self.on_change, value)

    def text_value(self) -> str:
        return self.format.format(self.value)

    @property
    def editing(self) -> bool:
        return self._buffer is not None

    def commit(self) -> None:
        """Yazılanı değere çevir; geçersizse eski değer kalır."""
        buffer, self._buffer = self._buffer, None
        if buffer:
            try:
                self.set(float(buffer.replace(",", ".")))
            except ValueError:
                pass
        self.refresh()

    def cancel(self) -> None:
        self._buffer = None
        self.refresh()

    def _step(self, n: float) -> None:
        if self.disabled:
            return
        if self.editing:
            self.commit()
        self.set(self.value + n * self.step)

    # ── tuşlar ve fare ───────────────────────────────────

    @action("Artır", key="up", show=False, palette=False)
    def increment(self) -> None:
        self._step(1)

    @action("Azalt", key="down", show=False, palette=False)
    def decrement(self) -> None:
        self._step(-1)

    @action("On adım artır", key="pageup", show=False, palette=False)
    def increment_page(self) -> None:
        self._step(10)

    @action("On adım azalt", key="pagedown", show=False, palette=False)
    def decrement_page(self) -> None:
        self._step(-10)

    @action("En küçük", key="home", show=False, palette=False)
    def to_min(self) -> None:
        if self.minimum is not None and not self.disabled:
            self._buffer = None
            self.set(self.minimum)

    @action("En büyük", key="end", show=False, palette=False)
    def to_max(self) -> None:
        if self.maximum is not None and not self.disabled:
            self._buffer = None
            self.set(self.maximum)

    def on_key(self, event: Key) -> None:
        if event.key == "enter" and self.editing:
            event.stop()
            self.commit()
        elif event.key == "escape" and self.editing:
            event.stop()
            self.cancel()
        elif event.key == "backspace" and not self.disabled:
            event.stop()
            self._buffer = (self.text_value() if self._buffer is None else self._buffer)[:-1]
            self.refresh()
        elif event.key == "delete" and not self.disabled:
            event.stop()
            self._buffer = ""
            self.refresh()

    def on_text_input(self, event: TextInput) -> None:
        if self.disabled:
            return
        for ch in event.text:
            buffer = self._buffer or ""
            if self._buffer is None and (ch.isdigit() or ch in "-.,"):
                buffer = ""  # yazmaya başlamak değeri baştan yazar
            if ch.isdigit():
                buffer += ch
            elif ch in ".," and self._places and "." not in buffer:
                buffer += "."
            elif ch == "-" and not buffer and (self.minimum is None or self.minimum < 0):
                buffer = "-"
            else:
                continue
            self._buffer = buffer
        self.refresh()

    def on_blur(self, event: Blur) -> None:
        if self.editing:
            self.commit()

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button != 1:
            return
        if self._minus.collidepoint(event.pos):
            self._step(-1)
        elif self._plus.collidepoint(event.pos):
            self._step(1)

    def on_mouse_scroll(self, event: MouseScroll) -> None:
        if event.dy and not self.disabled:
            event.stop()
            self._step(1 if event.dy > 0 else -1)

    # ── yerleşim ve çizim ────────────────────────────────

    def _field(self, p) -> int:
        """Değer alanının genişliği: sınırların, değerin ve 4 rakamın en genişi (+ imleç)."""
        samples = [self.format.format(v) for v in (self.minimum, self.maximum, self.value) if v is not None]
        return max(max((p.text.width(s, _BOLD) for s in samples), default=0) + p.ch, p.ch * 5)

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        field = self._field(p)
        extra = {"arrows": 4, "stacked": 4}.get(p.theme.spin, 8)  # ◂ … ▸ · … ▴▾ · [ − … + ]
        return field + p.ch * extra, p.row

    def _label(self) -> str:
        return self._buffer if self._buffer is not None else self.text_value()

    def _write_value(self, p, right: int, y: int, color, caret_color) -> None:
        """Değeri sağa yaslı yaz; düzenlenirken sonunda blok imleç."""
        text = self._label()
        if self.editing:
            p.surface.fill(caret_color, (right - p.ch, y + (p.row - p.text.height) // 2, p.ch, p.text.height))
            right -= p.ch
        p.write(right, y, [(text, _BOLD if self.has_focus else Style())], color=color, right=True)

    def render(self, p: Painter) -> None:
        th = p.theme
        c = self.content
        y = c.y
        focused, style = self.has_focus, th.spin
        dim = th.faint if self.disabled else th.dim
        hover = None
        if self.hovered and self._mouse is not None:
            mouse = self._mouse
            hover = "-" if self._minus.collidepoint(mouse) else "+" if self._plus.collidepoint(mouse) else None
        if style == "arrows":
            arrow = th.accent if focused else th.faint
            self._minus = pygame.Rect(c.x, y, p.ch * 2, p.row)
            self._plus = pygame.Rect(c.right - p.ch * 2, y, p.ch * 2, p.row)
            p.write(c.x, y, "◂", color=th.accent if hover == "-" else arrow)
            p.write(c.right, y, "▸", color=th.accent if hover == "+" else arrow, right=True)
            self._write_value(p, c.right - p.ch * 2, y, th.faint if self.disabled else th.text, th.accent)
        elif style == "stacked":  # alan + sağda üst üste iki ok
            cell = p.ch * 2
            field = pygame.Rect(c.x, y, c.w - cell, p.row)
            p.surface.fill(mix(th.bg, th.raised, 0.55), field)
            p.surface.fill(th.accent if focused else th.border, (field.x, field.bottom - (2 if focused else 1),
                                                                 field.w, 2 if focused else 1))
            self._write_value(p, field.right - p.ch // 2, y, th.faint if self.disabled else th.text, th.accent)
            arrows = pygame.Rect(field.right, y, cell, p.row)
            p.surface.fill(mix(th.bg, th.raised, 0.8), arrows)
            self._plus = pygame.Rect(arrows.x, arrows.y, arrows.w, arrows.h // 2)
            self._minus = pygame.Rect(arrows.x, self._plus.bottom, arrows.w, arrows.h - self._plus.h)
            cx, size = arrows.centerx, max(3, round(p.ch * 0.45))
            for rect, up, key in ((self._plus, True, "+"), (self._minus, False, "-")):
                color = th.accent if hover == key or focused else dim
                mid = rect.centery + (1 if up else -1)
                tip, base = (mid - size // 2, mid + size // 2) if up else (mid + size // 2, mid - size // 2)
                pygame.draw.polygon(p.surface, color, [(cx - size, base), (cx + size, base), (cx, tip)])
        else:  # bracket: Select ile aynı dil; odakta ters renkli
            rect = pygame.Rect(c.x, y, c.w, p.row)
            if focused:
                p.surface.fill(th.accent, rect)
            edge, text, sign = ((th.bg, th.bg, th.bg) if focused else
                                (th.faint, th.faint, th.faint) if self.disabled else (th.faint, th.text, th.dim))
            p.write(c.x, y, "[ ", color=edge)
            p.write(c.right, y, " ]", color=edge, right=True)
            bw, sw = p.text.width("[ "), p.text.width("− ")
            self._minus = pygame.Rect(c.x + bw - p.ch // 2, y, sw + p.ch // 2, p.row)
            self._plus = pygame.Rect(c.right - bw - sw, y, sw + p.ch // 2, p.row)
            hot = th.bg if focused else th.accent
            p.write(c.x + bw, y, "−", color=hot if hover == "-" else sign)
            p.write(c.right - bw, y, "+", color=hot if hover == "+" else sign, right=True)
            self._write_value(p, c.right - bw - sw - p.ch // 2, y, text, th.bg if focused else th.accent)

    def on_mouse_move(self, event: MouseMove) -> None:
        self._mouse = event.pos
        self.refresh()  # ± üstüne gelince vurgu

    def on_mouse_leave(self) -> None:
        self._mouse = None
        self.refresh()
