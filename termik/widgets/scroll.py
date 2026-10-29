"""Kaydırılabilir kapsayıcı."""

from __future__ import annotations

import pygame

from ..draw import Painter
from ..events import Key, MouseDown, MouseMove, MouseScroll, MouseUp
from ..widget import Widget, action


class ScrollView(Widget):
    """Kaydırılabilir kapsayıcı: çocuklar doğal boylarında alt alta dizilir, sığmayan kısım
    tekerlek, PgUp/PgDn ya da kaydırma çubuğunu sürükleyerek görülür.

    İçeride odak gezerken odaktaki bileşen kendiliğinden görünür alana kaydırılır. İçinde
    odaklanabilir bileşen yoksa ScrollView'in kendisi odak alır ve ↑/↓, Home/End ile de kayar.
    İçerik kısaysa büyümek isteyen (fr) çocuklar boş yeri paylaşır.
    """

    default_height = "1fr"

    def __init__(self, *children: Widget, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self.scroll_y = 0
        self._virtual = 0           # içeriğin toplam boyu, piksel
        self._bar = 0               # kaydırma çubuğuna ayrılan genişlik
        self._drag: int | None = None  # sürüklerken tutulan noktanın çubuk parçasındaki yeri

    @property
    def can_focus(self) -> bool:  # type: ignore[override]
        return not any(w.can_focus for w in self.walk() if w is not self)

    @property
    def max_scroll(self) -> int:
        return max(0, self._virtual - self.content.h)

    def scroll_to(self, y: float) -> None:
        y = max(0, min(round(y), self.max_scroll))
        if y != self.scroll_y:
            self.scroll_y = y
            self.refresh(layout=True)

    def scroll_by(self, dy: float) -> None:
        self.scroll_to(self.scroll_y + dy)

    # ── yerleşim ──────────────────────────────────────────

    def _heights(self, p, kids: list[Widget], width: int) -> list[int]:
        return [self._child_height(c, p, self._child_width(c, p, width), 0) for c in kids]

    def arrange(self, p: Painter) -> None:
        kids = [c for c in self.children if c.display]
        box = self.content
        gap = self._gap_px(p)
        gaps = gap * max(0, len(kids) - 1)
        heights = self._heights(p, kids, box.w)
        self._bar = p.ch if sum(heights) + gaps > box.h else 0
        width = box.w - self._bar
        if self._bar:  # çubuğa yer açınca satır kaydıran içerik uzayabilir
            heights = self._heights(p, kids, width)
        total = sum(heights) + gaps
        grow = [i for i, c in enumerate(kids) if c._spec("h").kind == "fr"]
        if total < box.h and grow:  # kısa içerik: büyümek isteyenler boş yeri paylaşır
            share, extra = divmod(box.h - total, len(grow))
            for n, i in enumerate(grow):
                heights[i] += share + (1 if n < extra else 0)
            total = box.h
        self._virtual = total
        self.scroll_y = max(0, min(self.scroll_y, self.max_scroll))
        y = box.y - self.scroll_y
        for c, h in zip(kids, heights):
            c._layout(p, pygame.Rect(box.x, y, self._child_width(c, p, width), h))
            y += h + gap

    def child_clip(self) -> pygame.Rect:
        c = self.content
        return pygame.Rect(c.x, c.y, c.w - self._bar, c.h)

    def _reveal(self, widget: Widget) -> None:
        c = self.content
        top = widget.region.y - (c.y - self.scroll_y)  # içeriğin başına göre konumu
        if top < self.scroll_y:
            self.scroll_to(top)
        elif top + widget.region.h > self.scroll_y + c.h:
            self.scroll_to(top + widget.region.h - c.h)

    # ── çizim ─────────────────────────────────────────────

    def _thumb(self) -> tuple[int, int]:
        """Kaydırma çubuğundaki parçanın (üst, boy); Painter.scrollbar ile aynı hesap."""
        c = self.content
        size = max(self.app.painter.row // 2, round(c.h * c.h / max(1, self._virtual)))
        return c.y + round((c.h - size) * self.scroll_y / max(1, self.max_scroll)), size

    def render(self, p: Painter) -> None:
        c = self.content
        p.scrollbar(c.right - 2, c.y, c.h, self._virtual, c.h, self.scroll_y, active=self.focus_within)

    # ── fare ──────────────────────────────────────────────

    def on_mouse_scroll(self, event: MouseScroll) -> None:
        if self.max_scroll:
            event.stop()
            self.scroll_by(-event.dy * 3 * self.app.painter.row)

    def on_mouse_down(self, event: MouseDown) -> None:
        c = self.content
        self._drag = None
        if self._bar and event.x >= c.right - self._bar and event.button == 1:
            event.stop()
            top, size = self._thumb()
            if top <= event.y < top + size:
                self._drag = event.y - top
            else:  # çubukta boş yere tık: oraya atla
                self._drag = size // 2
                self._drag_to(event.y)

    def on_mouse_move(self, event: MouseMove) -> None:
        if event.button and self._drag is not None:
            self._drag_to(event.y)

    def on_mouse_up(self, event: MouseUp) -> None:
        self._drag = None

    def _drag_to(self, y: int) -> None:
        c = self.content
        _, size = self._thumb()
        span = c.h - size
        self.scroll_to((y - self._drag - c.y) / span * self.max_scroll if span > 0 else 0)

    # ── klavye ────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        if not self.has_focus:  # içerideki bileşenler oklarla kendi işini yapsın
            return
        step = {"up": -1, "down": 1}.get(event.key)
        if step is not None:
            self.scroll_by(step * self.app.painter.row)
            event.stop()
        elif event.key in ("home", "end"):
            self.scroll_to(0 if event.key == "home" else self.max_scroll)
            event.stop()

    @action("Sayfa yukarı", key="pageup", show=False, palette=False)
    def page_up(self) -> None:
        self.scroll_by(-(self.content.h - self.app.painter.row))

    @action("Sayfa aşağı", key="pagedown", show=False, palette=False)
    def page_down(self) -> None:
        self.scroll_by(self.content.h - self.app.painter.row)
