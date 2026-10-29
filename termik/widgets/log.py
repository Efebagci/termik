"""Kayıt akışı."""

from __future__ import annotations

import time

from ..draw import Painter
from ..events import MouseScroll
from ..widget import Widget, action


class Log(Widget):
    """Satır satır büyüyen kayıt; yeni satır gelince en alta kayar.

    Tekerlek, ↑/↓, PgUp/PgDn, Home/End ile gezilir. Yukarı kaydırılmışken yeni satırlar görünümü
    oynatmaz; en alta inince canlı takip sürer. info/ok/warn/error simgeli satır yazar;
    timestamps=True ise başlarına saat eklenir.
    """

    default_height = "1fr"
    can_focus = True

    def __init__(self, *, max_lines: int = 1000, timestamps: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.lines: list[str] = []
        self.max_lines = max_lines
        self.timestamps = timestamps
        self._back = 0     # en alttan kaç satır yukarıda (0: canlı takip)
        self._visible = 1

    def write(self, markup: str) -> None:
        new = markup.split("\n")
        if self._back:
            self._back += len(new)
        self.lines.extend(new)
        if len(self.lines) > self.max_lines:
            del self.lines[: len(self.lines) - self.max_lines]
        self._clamp()
        self.refresh()

    def _stamped(self, icon: str, message: str) -> None:
        stamp = f"[faint]{time.strftime('%H:%M:%S')}[/]  " if self.timestamps else ""
        self.write(f"{stamp}{icon} {message}")

    def info(self, message: str) -> None:
        self._stamped("[blue]•[/]", message)

    def ok(self, message: str) -> None:
        self._stamped("[green]✓[/]", message)

    def warn(self, message: str) -> None:
        self._stamped("[yellow]⚠[/]", message)

    def error(self, message: str) -> None:
        self._stamped("[red]✗[/]", message)

    def clear(self) -> None:
        self.lines.clear()
        self._back = 0
        self.refresh()

    def scroll(self, lines: int) -> None:
        """Pozitif: yukarı (eski satırlara), negatif: aşağı."""
        self._back += lines
        self._clamp()
        self.refresh()

    def _clamp(self) -> None:
        self._back = max(0, min(self._back, len(self.lines) - self._visible))

    def render(self, p: Painter) -> None:
        c = self.content
        self._visible = max(1, c.h // p.row)
        self._clamp()
        total = len(self.lines)
        end = total - self._back
        start = max(0, end - self._visible)
        bar = p.ch if total > self._visible else 0
        for i, line in enumerate(self.lines[start:end]):
            p.write(c.x, c.y + i * p.row, p.text.elide(line, c.w - bar))
        p.scrollbar(c.right - 2, c.y, self._visible * p.row, total, self._visible, start, active=self.has_focus)

    def on_mouse_scroll(self, event: MouseScroll) -> None:
        event.stop()
        self.scroll(event.dy * 3)

    @action("Yukarı", key="up", show=False, palette=False)
    def line_up(self) -> None:
        self.scroll(1)

    @action("Aşağı", key="down", show=False, palette=False)
    def line_down(self) -> None:
        self.scroll(-1)

    @action("Sayfa yukarı", key="pageup", show=False, palette=False)
    def page_up(self) -> None:
        self.scroll(self._visible - 1)

    @action("Sayfa aşağı", key="pagedown", show=False, palette=False)
    def page_down(self) -> None:
        self.scroll(1 - self._visible)

    @action("Başa", key="home", show=False, palette=False)
    def scroll_home(self) -> None:
        self.scroll(len(self.lines))

    @action("Sona", key="end", show=False, palette=False)
    def scroll_end(self) -> None:
        self._back = 0
        self.refresh()
