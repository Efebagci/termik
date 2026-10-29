"""Açılır seçim kutusu."""

from __future__ import annotations

from typing import Callable, Iterable

import pygame

from ..draw import Painter
from ..events import Click, Message
from ..popup import Popup
from ..reactive import reactive
from ..text import Style
from ..widget import Widget, action
from .options import OptionList


class Select(Widget):
    """Açılır seçim kutusu: ⏎, space ya da tık altında süzülebilir bir liste açar; ←/→ listeyi açmadan
    önceki ya da sonraki seçeneğe geçer. Select.Changed iletir.

        Select(["Tam", "Artımlı", "Diferansiyel"], index=1)

    Görünüşü temadaki select belirtecinden gelir: bracket [ Artımlı ▾ ], arrows ◂ Artımlı ▸, underline
    altı çizili. Genişliği en uzun seçeneğe göre sabittir; değer değişince yerleşim oynamaz.
    """

    default_width = "auto"
    bind_value = "value"
    default_height = "auto"
    can_focus = True
    cursor = "hand"
    index = reactive(0)

    class Changed(Message):
        def __init__(self, select: Select, index: int) -> None:
            super().__init__()
            self.select, self.index = select, index

        @property
        def value(self) -> str:
            return self.select.options[self.index]

    def __init__(self, options: list[str], *, index: int = 0, on_change: Callable | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.options = list(options)
        self.on_change = on_change
        self.index = max(0, min(index, len(self.options) - 1))

    @property
    def value(self) -> str | None:
        return self.options[self.index] if self.options else None

    @value.setter
    def value(self, value: str) -> None:
        if value in self.options:
            self.index = self.options.index(value)

    def watch_index(self, index: int) -> None:
        self.post_message(Select.Changed(self, index))
        self._sync_bind()
        if self.on_change is not None:
            self._call(self.on_change, self.value)

    # ── yerleşim ve çizim ────────────────────────────────

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        longest = max((p.text.width([(o, Style(bold=True))]) for o in self.options), default=p.ch * 4)
        extra = {"arrows": 4, "underline": 3}.get(p.theme.select, 6)  # ◂ … ▸ · … ▾ · [ … ▾ ]
        return longest + p.ch * extra, p.row

    def render(self, p: Painter) -> None:
        th = p.theme
        c = self.content
        style = th.select
        focused = self.has_focus
        y = c.y
        if style == "arrows":
            arrow = th.accent if focused else th.faint
            p.write(c.x, y, "◂", color=arrow)
            p.write(c.right, y, "▸", color=arrow, right=True)
            label = p.text.elide([(self.value or "", Style(bold=focused))], c.w - p.ch * 4)
            p.write(c.x + p.ch * 2, y, label, color=th.text)
        elif style == "underline":
            label = p.text.elide([(self.value or "", Style(bold=focused))], c.w - p.ch * 3)
            p.write(c.x, y, label, color=th.text if focused or self.hovered else th.dim)
            p.write(c.right, y, "▾", color=th.accent if focused else th.faint, right=True)
            base = y + (p.row + p.text.height) // 2
            p.surface.fill(th.accent if focused else th.border, (c.x, base, c.w, 2 if focused else 1))
        else:  # bracket: butonlarla aynı dil; odakta ters renkli
            rect = pygame.Rect(c.x, y, c.w, p.row)
            if focused:
                p.surface.fill(th.accent, rect)
            elif self.hovered:
                p.hover(rect)
            edge, text, arrow = ((th.bg, th.bg, th.bg) if focused else
                                 (th.faint, th.faint, th.faint) if self.disabled else (th.faint, th.text, th.dim))
            p.write(c.x, y, "[ ", color=edge)
            p.write(c.right, y, " ]", color=edge, right=True)
            p.write(c.right - p.text.width(" ]"), y, "▾", color=arrow, right=True)
            label = p.text.elide([(self.value or "", Style(bold=focused))], c.w - p.ch * 6)
            p.write(c.x + p.text.width("[ "), y, label, color=text)

    # ── eylemler ─────────────────────────────────────────

    @action("Listeyi aç", key="enter,space", show=False, palette=False)
    def open(self) -> None:
        if self.options and not self.disabled:
            self.window.push_screen(_SelectPopup(self), callback=self._picked)

    def _picked(self, index: int | None) -> None:
        if index is not None:
            self.index = index

    @action("Önceki seçenek", key="left", show=False, palette=False)
    def previous(self) -> None:
        if self.options:
            self.index = (self.index - 1) % len(self.options)

    @action("Sonraki seçenek", key="right", show=False, palette=False)
    def next(self) -> None:
        if self.options:
            self.index = (self.index + 1) % len(self.options)

    def on_click(self, event: Click) -> None:
        event.stop()
        self.open()


class _SelectPopup(Popup):
    """Seçim kutusunun altında açılan süzülebilir liste; seçilen sırayı döndürür."""

    def __init__(self, select: Select) -> None:
        super().__init__(select.region, min_width=select.region.w)
        self.list = OptionList(select.options, index=select.index, rows=min(8, len(select.options)))

    def compose_body(self) -> Iterable[Widget]:
        yield self.list

    def on_mount(self) -> None:
        self.list.focus()

    def on_option_list_selected(self, event: OptionList.Selected) -> None:
        event.stop()
        self.dismiss(event.index)
