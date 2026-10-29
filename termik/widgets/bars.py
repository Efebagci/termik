"""Uygulama çubukları: başlık, kısayol satırı, durum çubuğu."""

from __future__ import annotations

import time

import pygame

from .. import keys
from ..draw import Painter
from ..events import Click, MouseMove
from ..reactive import reactive
from ..text import Style, escape
from ..widget import Widget


class Header(Widget):
    """Uygulama başlığı: renk geçişli ad, soluk alt başlık, sağda durum ve saat."""

    default_height = "auto"
    title = reactive("termik")
    subtitle = reactive("")
    status = reactive("")

    def __init__(self, title: str = "termik", subtitle: str = "", *, clock: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self.title, self.subtitle, self.clock = title, subtitle, clock

    def on_mount(self) -> None:
        if self.clock:
            self.set_interval(15, self.refresh)

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        return 0, max(p.heading.height + 6, p.row)

    def render(self, p: Painter) -> None:
        th = p.theme
        c = self.content
        base = c.y + (c.h - p.heading.height) // 2 + p.heading.stack.ascent  # ortak taban çizgisi
        x = c.x + p.gradient_text(c.x, base - p.heading.stack.ascent, self.title, th.accent, th.accent2)
        if self.subtitle:
            p.text.draw(p.surface, x + p.ch, 0, self.subtitle, color=th.faint, baseline=base)
        right = "   ".join(part for part in (self.status, f"[faint]{time.strftime('%H:%M')}[/]" if self.clock else "") if part)
        if right:
            p.text.draw(p.surface, c.right - p.text.width(right), 0, right, baseline=base)


class KeyBar(Widget):
    """Şu an geçerli kısayollar: "f5 başlat · esc iptal · ctrl+q çık".

    Odaktaki bileşenden uygulamaya kadar @action ile tanımlanmış eylemleri gösterir; odak değişince
    kendiliğinden güncellenir. Öğelere tıklamak eylemi çalıştırır.
    """

    default_height = "auto"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._items: list[tuple[pygame.Rect, Widget, str]] = []
        self._hover_i: int | None = None

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        return 0, p.row

    def render(self, p: Painter) -> None:
        c = self.content
        sep = "  [faint]·[/]  "
        x = c.x
        self._items = []
        for i, (key, hint, owner, name) in enumerate(self.window.active_bindings()):
            markup = f"{escape(keys.display(key))} [dim]{escape(hint)}[/]"
            lead = p.text.width(sep) if i else 0
            w = p.text.width(markup)
            if x + lead + w > c.right:
                break
            if i:
                x += p.write(x, c.y, sep)
            rect = pygame.Rect(x - p.ch // 2, c.y, w + p.ch, p.row)
            if i == self._hover_i:
                p.hover(rect)
            p.write(x, c.y, markup)
            self._items.append((rect, owner, name))
            x += w

    def _item_at(self, x: int, y: int) -> int | None:
        return next((i for i, (r, _, _) in enumerate(self._items) if r.collidepoint(x, y)), None)

    def on_click(self, event: Click) -> None:
        i = self._item_at(event.x, event.y)
        if i is not None:
            event.stop()
            _, owner, name = self._items[i]
            owner._call(getattr(owner, name))

    def on_mouse_move(self, event: MouseMove) -> None:
        i = self._item_at(event.x, event.y)
        if i != self._hover_i:
            self._hover_i = i
            self.refresh()

    def on_mouse_leave(self) -> None:
        self._hover_i = None
        self.refresh()


class StatusBar(Widget):
    """Alt durum çubuğu: solda renkli mod rozeti ve bağlam, sağda bilgiler.

    mode_color bir tema rengi adıdır: "accent", "green", "yellow", "red"…
    """

    default_height = "auto"
    mode = reactive("", layout=True)
    mode_color = reactive("accent")
    left = reactive("")
    right = reactive("")

    def __init__(self, *, mode: str = "", mode_color: str = "accent", left: str = "", right: str = "",
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.mode, self.mode_color, self.left, self.right = mode, mode_color, left, right

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        return 0, p.row + (6 if p.theme.radius else 2)

    def render(self, p: Painter) -> None:
        th = p.theme
        bar = self.content
        p.round_rect(bar, th.raised)
        x = bar.x
        if self.mode:
            bw = p.small.width(self.mode, Style(bold=True)) + p.ch * 3
            p.pill(pygame.Rect(bar.x, bar.y, bw, bar.h), th.color(self.mode_color) or th.accent, self.mode,
                   th.bg, bold=True, font=p.small)
            x += bw
        rw = p.text.width(self.right) if self.right else 0
        if self.right:
            p.text.draw(p.surface, bar.right - p.ch * 2 - rw, bar.y, self.right, center_in=bar.h)
        if self.left:
            lx = x + p.ch * 2
            p.text.draw(p.surface, lx, bar.y, p.text.elide(self.left, bar.right - p.ch * 4 - rw - lx), center_in=bar.h)
