"""Sekmeli kapsayıcı."""

from __future__ import annotations

from typing import Callable

import pygame

from ..events import Click, Key, Message, MouseMove
from ..reactive import reactive
from ..text import Style
from ..widget import Widget, action

_BOLD = Style(bold=True)


class Tab(Widget):
    """Tabs içindeki bir sekme: başlık (markup) ve alt alta dizilen içerik."""

    def __init__(self, title: str, *children: Widget, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self.title = title


class Tabs(Widget):
    """Sekmeli kapsayıcı: çocukları Tab'lerdir, yalnızca etkin olanı görünür.

        with ui.Tabs():
            with ui.Tab("Genel"):
                yield ui.Input(label="Ad")
            with ui.Tab("Gelişmiş"):
                yield ui.Checkbox("Ayrıntılı günlük")

    Başlık satırı odaktayken ←/→, içerideki her yerden ctrl+tab / ctrl+shift+tab (ya da ctrl+pgdn /
    ctrl+pgup) sekme değiştirir; başlığa tıklamak da. Odak gizli bir sekmedeki bileşene geçerse o
    sekme açılır. Görünüşü temadaki tabs belirtecinden gelir: inverse, folder, underline, bracket.
    Tabs.Changed iletir.
    """

    can_focus = True
    active = reactive(0, layout=True)

    class Changed(Message):
        def __init__(self, tabs: Tabs, index: int) -> None:
            super().__init__()
            self.tabs, self.index = tabs, index

        @property
        def title(self) -> str:
            return self.tabs.tabs[self.index].title

    def __init__(self, *children: Widget, active: int = 0, on_change: Callable | None = None, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self.active = active
        self.on_change = on_change
        self._rects: list[pygame.Rect] = []
        self._hover: int | None = None

    @property
    def tabs(self) -> list[Tab]:
        return [c for c in self.children if isinstance(c, Tab)]

    def select(self, index: int) -> None:
        if self.tabs:
            self.active = index % len(self.tabs)

    def on_mount(self) -> None:
        self._show()

    def _show(self) -> None:
        for i, tab in enumerate(self.tabs):
            tab.display = i == self.active

    def watch_active(self, index: int) -> None:
        self._show()
        focused = self.app.focused
        if focused is not None and any(not tab.display and (focused is tab or tab in focused.ancestors())
                                       for tab in self.tabs):
            self.focus()  # odak gizlenen sekmede kaldı: başlığa gelsin
        self.post_message(Tabs.Changed(self, index))
        if self.on_change is not None:
            self._call(self.on_change, index)

    def _reveal(self, widget: Widget) -> None:
        for i, tab in enumerate(self.tabs):
            if tab is widget or tab in widget.ancestors():
                if i != self.active:
                    self.active = i
                return

    # ── yerleşim ve çizim ────────────────────────────────

    def _header(self, p) -> int:
        """Başlık şeridinin yüksekliği: klasör kipinde üstte yarım satır çerçeve payı, altta ayraç."""
        return (p.row // 2 if p.theme.tabs == "folder" else 0) + p.row + p.row // 3

    def chrome(self, p) -> tuple[int, int, int, int]:
        t, r, b, l = super().chrome(p)
        return t + self._header(p), r, b, l

    def render(self, p) -> None:
        th = p.theme
        style = th.tabs
        r = self.region
        within = self.focus_within
        top = r.y + (p.row // 2 if style == "folder" else 0)
        line_y = top + p.row + 1
        x = r.x
        gaps: list[tuple[int, int]] = []
        self._rects = []
        for i, tab in enumerate(self.tabs):
            active, hot = i == self.active, i == self._hover
            idle = th.text if hot else th.dim
            if style == "bracket":  # [ Genel ]: butonlar gibi; etkin olan ters renkli
                lead = p.text.width([("[ ", Style())])
                w = lead * 2 + p.text.width(tab.title, _BOLD)
                if active:
                    p.surface.fill(th.accent if within else th.border, (x, top, w, p.row))
                    fg = th.bg if within else th.text
                    p.write(x, top, [("[ ", Style())], color=fg)
                    p.write(x + lead, top, tab.title, _BOLD, fg)
                    p.write(x + w, top, [(" ]", Style())], color=fg, right=True)
                else:
                    p.write(x + lead, top, tab.title, color=idle)
            else:
                w = p.text.width(tab.title, _BOLD) + p.ch * 2
                if not active:
                    p.write(x + p.ch, top, tab.title, color=idle)
                elif style == "inverse":  # ters renkli etiket, ayraca yapışık
                    p.surface.fill(th.accent if within else th.border, (x, top, w, line_y - top + 1))
                    p.write(x + p.ch, top, tab.title, _BOLD, th.bg if within else th.text)
                elif style == "underline":
                    p.write(x + p.ch, top, tab.title, _BOLD, th.accent if within else th.text)
                    p.surface.fill(th.accent if within else th.dim, (x, line_y - 1, w, 3))
                else:  # folder: etkin sekme çerçeveyle içeriğe bağlanır
                    color = th.accent if within else th.border
                    box_top = r.y + p.row // 4
                    p.surface.fill(color, (x, box_top, w, 1))
                    p.surface.fill(color, (x, box_top, 1, line_y - box_top + 1))
                    p.surface.fill(color, (x + w - 1, box_top, 1, line_y - box_top + 1))
                    gaps.append((x + 1, x + w - 1))
                    p.write(x + p.ch, top, tab.title, _BOLD, th.accent if within else th.text)
            self._rects.append(pygame.Rect(x, top, w, p.row))
            x += w + p.ch
        line = th.accent if within and style == "folder" else th.border
        p._hline(r.x, r.right, line_y, 1, line, gaps)

    # ── klavye ve fare ───────────────────────────────────

    def on_key(self, event: Key) -> None:
        if self.has_focus and event.key in ("left", "right"):
            event.stop()
            self.select(self.active + (1 if event.key == "right" else -1))

    @action("Sonraki sekme", key="ctrl+tab,ctrl+pagedown", show=False, palette=False)
    def next_tab(self) -> None:
        self.select(self.active + 1)

    @action("Önceki sekme", key="ctrl+shift+tab,ctrl+pageup", show=False, palette=False)
    def previous_tab(self) -> None:
        self.select(self.active - 1)

    def _title_at(self, pos) -> int | None:
        return next((i for i, rect in enumerate(self._rects) if rect.collidepoint(pos)), None)

    def on_click(self, event: Click) -> None:
        i = self._title_at(event.pos)
        if i is not None:
            event.stop()
            self.select(i)

    def on_mouse_move(self, event: MouseMove) -> None:
        i = self._title_at(event.pos)
        if i != self._hover:
            self._hover = i
            self.refresh()

    def on_mouse_leave(self) -> None:
        self._hover = None
        self.refresh()
