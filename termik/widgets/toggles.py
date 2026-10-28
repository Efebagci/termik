"""Onay kutusu ve radyo grubu."""

from __future__ import annotations

from typing import Callable

import pygame

from ..events import Click, Message, MouseMove
from ..reactive import reactive
from ..text import Style
from ..widget import Widget, action


class Checkbox(Widget):
    """[✓] seçenek. Tıklayınca ya da odaktayken Space/Enter ile değişir; Checkbox.Changed iletir."""

    default_width = "auto"
    default_height = "auto"
    can_focus = True
    cursor = "hand"
    value = reactive(False)

    class Changed(Message):
        def __init__(self, checkbox: Checkbox, value: bool) -> None:
            super().__init__()
            self.checkbox, self.value = checkbox, value

    def __init__(self, label: str, value: bool = False, *, on_change: Callable | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.on_change = on_change
        self.value = value

    def _markup(self, p) -> str:
        return f"{p.check(self.value)} " + (self.label if self.value else f"[dim]{self.label}[/]")

    def measure(self, p, width: int) -> tuple[int, int]:
        return p.text.width(self._markup(p)) + p.ch, p.row

    def render(self, p) -> None:
        c = self.content
        if self.hovered or self.has_focus:
            p.hover((c.x, c.y, p.text.width(self._markup(p)) + p.ch, p.row))
        p.write(c.x + p.ch // 2, c.y, self._markup(p), Style(bold=self.has_focus))

    def toggle(self) -> None:
        self.value = not self.value

    def watch_value(self, value: bool) -> None:
        self.post_message(Checkbox.Changed(self, value))
        if self.on_change is not None:
            self._call(self.on_change, value)

    def on_click(self, event: Click) -> None:
        event.stop()
        self.toggle()

    @action("Değiştir", key="space,enter", show=False, palette=False)
    def press(self) -> None:
        self.toggle()


class RadioSet(Widget):
    """(•) Tam  ( ) Artımlı — tek seçimli grup. ←/→ ile değişir; RadioSet.Changed iletir.

    label= verilirse solunda label_width karakter genişliğinde etiket olur.
    """

    default_width = "auto"
    default_height = "auto"
    can_focus = True
    cursor = "hand"
    index = reactive(0)

    class Changed(Message):
        def __init__(self, radio_set: RadioSet, index: int, value: str) -> None:
            super().__init__()
            self.radio_set, self.index, self.value = radio_set, index, value

    def __init__(self, *options: str, index: int = 0, label: str | None = None,
                 label_width: float = 12, on_change: Callable | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.options = list(options)
        self.label = label
        self.label_width = label_width
        self.on_change = on_change
        self.index = index
        self._rects: list[pygame.Rect] = []
        self._hover_i: int | None = None

    @property
    def value(self) -> str:
        return self.options[self.index] if self.options else ""

    def _markup(self, p, i: int) -> str:
        name = self.options[i]
        return f"{p.radio(i == self.index)} " + (name if i == self.index else f"[dim]{name}[/]")

    def _option_rects(self, p, x: int, y: int) -> list[pygame.Rect]:
        rects = []
        x += round(self.label_width * p.ch) if self.label else 0
        for i in range(len(self.options)):
            w = p.text.width(self._markup(p, i)) + p.ch
            rects.append(pygame.Rect(x, y, w, p.row))
            x += w + p.ch * 2
        return rects

    def measure(self, p, width: int) -> tuple[int, int]:
        rects = self._option_rects(p, 0, 0)
        return (rects[-1].right if rects else 0), p.row

    def render(self, p) -> None:
        c = self.content
        if self.label:
            p.write(c.x, c.y, self.label, color=p.theme.dim)
        self._rects = self._option_rects(p, c.x, c.y)
        for i, rect in enumerate(self._rects):
            current = i == self.index
            if i == self._hover_i or (self.has_focus and current):
                p.hover(rect)
            p.write(rect.x + p.ch // 2, c.y, self._markup(p, i), Style(bold=self.has_focus and current))

    def _option_at(self, x: int, y: int) -> int | None:
        return next((i for i, r in enumerate(self._rects) if r.collidepoint(x, y)), None)

    def watch_index(self, index: int) -> None:
        self.post_message(RadioSet.Changed(self, index, self.value))
        if self.on_change is not None:
            self._call(self.on_change, self.value)

    def on_click(self, event: Click) -> None:
        i = self._option_at(event.x, event.y)
        if i is not None:
            event.stop()
            self.index = i

    def on_mouse_move(self, event: MouseMove) -> None:
        i = self._option_at(event.x, event.y)
        if i != self._hover_i:
            self._hover_i = i
            self.refresh()

    def on_mouse_leave(self) -> None:
        self._hover_i = None
        self.refresh()

    @action("Önceki seçenek", key="left,up", show=False, palette=False)
    def select_previous(self) -> None:
        if self.options:
            self.index = (self.index - 1) % len(self.options)

    @action("Sonraki seçenek", key="right,down", show=False, palette=False)
    def select_next(self) -> None:
        if self.options:
            self.index = (self.index + 1) % len(self.options)
