"""Kaydırıcı."""

from __future__ import annotations

from typing import Callable

from ..events import Message, MouseDown, MouseMove, MouseScroll
from ..reactive import reactive
from ..text import Style
from ..widget import Widget, action

_BOLD = Style(bold=True)


class Slider(Widget):
    """Kaydırıcı: ←/→ (↓/↑) bir adım, PgUp/PgDn aralığın onda biri, Home/End uçlar; fareyle tıklanıp
    sürüklenir, tekerlekle değişir. Değer step'e oturtulur. Slider.Changed iletir.

        Slider(60, min=0, max=100, step=5)

    Görünüşü temadaki slider belirtecinden gelir: bar ilerleme çubuğu gibi çizilir (bar belirtecini
    izler), line ince iz ve yuvarlak tutamak, value yalnızca ◂ 60 ▸. Değer sağda sabit genişlikte
    yazar (show_value=False gizler); format= biçimi değiştirir ("{:.1f} sn").
    """

    default_height = "auto"
    can_focus = True
    cursor = "hand"
    value = reactive(0)

    class Changed(Message):
        def __init__(self, slider: Slider, value: float) -> None:
            super().__init__()
            self.slider, self.value = slider, value

    def __init__(self, value: float = 0, *, min: float = 0, max: float = 100, step: float = 1,
                 show_value: bool = True, format: str | None = None, on_change: Callable | None = None,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        if not max > min:
            raise ValueError("Slider: max, min'den büyük olmalı")
        self.minimum, self.maximum, self.step = min, max, step
        self.show_value = show_value
        self._whole = all(float(v).is_integer() for v in (min, max, step or 1))
        self.format = format or ("{:.0f}" if self._whole else "{:g}")
        self.on_change = on_change
        self.value = self._snap(value)
        self._track = (0, 1)  # son çizimde izin x'i ve genişliği (fare için)

    def _snap(self, value: float) -> float:
        lo, hi = self.minimum, self.maximum
        value = lo if value < lo else hi if value > hi else value
        if self.step:
            value = lo + round((value - lo) / self.step) * self.step
            value = lo if value < lo else hi if value > hi else value
        return int(round(value)) if self._whole else round(value, 10)

    @property
    def fraction(self) -> float:
        return (self.value - self.minimum) / (self.maximum - self.minimum)

    def set(self, value: float) -> None:
        self.value = self._snap(value)

    def watch_value(self, value: float) -> None:
        self.post_message(Slider.Changed(self, value))
        if self.on_change is not None:
            self._call(self.on_change, value)

    # ── yerleşim ve çizim ────────────────────────────────

    def _value_width(self, p) -> int:
        return max(p.text.width(self.format.format(v), _BOLD) for v in (self.minimum, self.maximum))

    def measure(self, p, width: int) -> tuple[int, int]:
        return p.ch * 24, p.row

    def render(self, p) -> None:
        th = p.theme
        c = self.content
        focused = self.has_focus
        off = self.disabled  # devre dışı: her şey soluk
        fill = th.faint if off else th.accent
        shown = [(self.format.format(self.value), _BOLD)]
        vw = self._value_width(p)
        if th.slider == "value":
            arrow = th.accent if focused else th.faint
            p.write(c.x, c.y, "◂", color=arrow)
            p.write(c.x + p.ch * 2 + vw, c.y, shown, color=th.faint if off else th.text, right=True)
            p.write(c.x + p.ch * 3 + vw, c.y, "▸", color=arrow)
            self._track = (c.x, p.ch * 4 + vw)
            return
        room = max(p.ch * 4, c.w - (vw + p.ch * 2 if self.show_value else 0))
        if th.slider == "line":
            mid = c.y + p.row // 2
            h = max(2, round(p.row / 7))
            knob = max(3, p.text.height // 3)
            p.round_rect((c.x, mid - h // 2, room, h), th.raised, radius=h // 2)
            tx = c.x + knob + round((room - knob * 2) * self.fraction)
            if tx > c.x:
                p.round_rect((c.x, mid - h // 2, tx - c.x, h), fill, radius=h // 2)
            knob_color = th.faint if off else th.accent if focused else th.text
            p.round_rect((tx - knob, mid - knob, knob * 2, knob * 2), knob_color, radius=knob)
        else:  # bar: ilerleme çubuğu ve dolgunun ucunda parlak tutamak
            room = room // p.ch * p.ch
            p.bar(c.x, c.y, room, self.fraction, colors=(fill, fill) if off else None)
            tx = min(c.x + room - 2, c.x + round(room * self.fraction))
            top = c.y + (p.row - p.text.height) // 2
            thumb = th.faint if off else th.text if focused else th.dim
            p.surface.fill(thumb, (tx - 1, top - 1, 3, p.text.height + 2))
        self._track = (c.x, room)
        if self.show_value:
            p.write(c.right, c.y, shown, color=th.faint if off else th.text if focused else th.dim, right=True)

    # ── klavye ve fare ───────────────────────────────────

    @action("Azalt", key="left,down", show=False, palette=False)
    def decrease(self) -> None:
        self.set(self.value - (self.step or 1))

    @action("Artır", key="right,up", show=False, palette=False)
    def increase(self) -> None:
        self.set(self.value + (self.step or 1))

    @action("Çok azalt", key="pagedown", show=False, palette=False)
    def decrease_page(self) -> None:
        self.set(self.value - (self.maximum - self.minimum) / 10)

    @action("Çok artır", key="pageup", show=False, palette=False)
    def increase_page(self) -> None:
        self.set(self.value + (self.maximum - self.minimum) / 10)

    @action("En aza", key="home", show=False, palette=False)
    def to_minimum(self) -> None:
        self.set(self.minimum)

    @action("En çoğa", key="end", show=False, palette=False)
    def to_maximum(self) -> None:
        self.set(self.maximum)

    def _set_at(self, x: int) -> None:
        x0, w = self._track
        self.set(self.minimum + (x - x0) / max(1, w) * (self.maximum - self.minimum))

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button != 1 or self.disabled:
            return
        event.stop()
        if self.app.theme.slider == "value":  # sol yarı azaltır, sağ yarı artırır
            x0, w = self._track
            self.set(self.value + (self.step or 1) * (1 if event.x >= x0 + w // 2 else -1))
        else:
            self._set_at(event.x)

    def on_mouse_move(self, event: MouseMove) -> None:
        if event.button and not self.disabled and self.app.theme.slider != "value":
            self._set_at(event.x)

    def on_mouse_scroll(self, event: MouseScroll) -> None:
        if not self.disabled:
            event.stop()
            self.set(self.value + (self.step or 1) * (1 if event.dy > 0 else -1))
