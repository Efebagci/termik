"""Tablo."""

from __future__ import annotations

import re
from itertools import count
from typing import Any

from ..draw import Painter
from ..events import Click, Message, MouseMove, MouseScroll
from ..fuzzy import fold
from ..layout import AUTO, Size, SizeSpec, distribute, parse_size
from ..text import Style, plain_text
from ..theme import mix
from ..widget import Widget, action


class _Column:
    __slots__ = ("label", "width", "align")

    def __init__(self, label: str, width: Size, align: str) -> None:
        self.label, self.width, self.align = label, width, align


def _natural_key(cell: str) -> list:
    """Doğal sıralama: "9" < "10", harfler Türkçe gevşek ve büyük/küçük harf duyarsız."""
    parts = re.split(r"(\d+(?:[.,]\d+)?)", fold(plain_text(cell)))
    return [(0, float(part.replace(",", "."))) if i % 2 else (1, part) for i, part in enumerate(parts) if part]


class Table(Widget):
    """Başlıklı, sütunlu tablo.

    ↑/↓ (PgUp/PgDn, Home/End) satır seçer; Enter ya da çift tık Table.RowSelected iletir.
    Başlığa tıklamak o sütuna göre sıralar, tekrar tıklamak tersine çevirir. Hücreler markup
    olabilir; genişliği verilmeyen sütunlar içeriklerine göre boyutlanır.

        table = Table(("Tarih", 12), ("Mod", "1fr"), ("Boyut", 9, "right"))
        table.add_row("27.10 22:14", "artımlı", "412 MB")
    """

    default_height = "1fr"
    can_focus = True
    GAP = 2  # sütunlar arası boşluk, karakter

    class RowHighlighted(Message):
        def __init__(self, table: Table, index: int, key: Any) -> None:
            super().__init__()
            self.table, self.index, self.key = table, index, key

    class RowSelected(Message):
        def __init__(self, table: Table, index: int, key: Any) -> None:
            super().__init__()
            self.table, self.index, self.key = table, index, key

    def __init__(self, *columns, zebra: bool = False, sortable: bool = True, show_cursor: bool = True,
                 placeholder: str = "kayıt yok", **kwargs) -> None:
        super().__init__(**kwargs)
        self.columns: list[_Column] = []
        self.rows: list[tuple[list[str], Any]] = []
        self.zebra, self.sortable, self.show_cursor, self.placeholder = zebra, sortable, show_cursor, placeholder
        self.cursor_row = 0
        self.sorted_by: tuple[int, bool] | None = None  # (sütun, ters mi)
        self._keys = count()
        self._natural: list[int] | None = None
        self._edges: list[tuple[int, int]] = []  # son çizimde her sütunun (x, genişlik)
        self._top = 0
        self._visible = 1
        self._hover: int | None = None
        for column in columns:
            self.add_column(*(column if isinstance(column, tuple) else (column,)))

    # ── veri ──────────────────────────────────────────────

    def add_column(self, label: str, width: SizeSpec = None, align: str = "left") -> None:
        """width: karakter, "1fr", "20%" ya da None (içeriğine göre); align: left · right · center."""
        self.columns.append(_Column(label, parse_size(width) if width is not None else AUTO, align))
        self._natural = None
        self.refresh()

    def add_row(self, *cells, key: Any = None, index: int | None = None) -> Any:
        """Satır ekle (index verilirse o sıraya); satırın anahtarını döndürür."""
        key = next(self._keys) if key is None else key
        row = ([str(c) for c in cells], key)
        if index is None:
            self.rows.append(row)
        else:
            self.rows.insert(index, row)
        if self.sorted_by is not None:
            self.sort(*self.sorted_by)
        self._natural = None
        self.refresh()
        return key

    def remove_row(self, key: Any) -> None:
        self.rows = [row for row in self.rows if row[1] != key]
        self.cursor_row = min(self.cursor_row, max(0, len(self.rows) - 1))
        self._natural = None
        self.refresh()

    def clear(self) -> None:
        self.rows.clear()
        self.cursor_row = self._top = 0
        self._natural = None
        self.refresh()

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def cursor_key(self) -> Any:
        return self.rows[self.cursor_row][1] if self.rows else None

    def get_row(self, key: Any) -> list[str]:
        return next(cells for cells, k in self.rows if k == key)

    def sort(self, column: int, reverse: bool = False) -> None:
        """Satırları sütuna göre sırala; imleç aynı satırın üstünde kalır."""
        current = self.cursor_key
        self.rows.sort(key=lambda row: _natural_key(row[0][column] if column < len(row[0]) else ""), reverse=reverse)
        self.sorted_by = (column, reverse)
        if current is not None:
            self.cursor_row = next(i for i, (_, k) in enumerate(self.rows) if k == current)
        self.refresh()

    def move_cursor(self, row: int) -> None:
        if not self.rows:
            return
        row = max(0, min(len(self.rows) - 1, row))
        if row != self.cursor_row:
            self.cursor_row = row
            self.post_message(Table.RowHighlighted(self, row, self.rows[row][1]))
        if row < self._top:
            self._top = row
        elif row >= self._top + self._visible:
            self._top = row - self._visible + 1
        self.refresh()

    # ── çizim ─────────────────────────────────────────────

    def _header_h(self, p) -> int:
        return p.row + 4  # başlık + altındaki çizgi

    def _widths(self, p, width: int) -> list[int]:
        if self._natural is None:
            arrow = p.ch * 2 if self.sortable else 0  # sıralama oku için yer
            self._natural = [
                max([p.text.width(col.label, Style(bold=True)) + arrow]
                    + [p.text.width(cells[k]) for cells, _ in self.rows if k < len(cells)])
                for k, col in enumerate(self.columns)
            ]
        gap = p.ch * self.GAP * max(0, len(self.columns) - 1)
        return distribute([col.width for col in self.columns], self._natural, max(0, width - gap), p.ch)

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        return sum(self._widths(p, width)), self._header_h(p) + max(1, len(self.rows)) * p.row

    def _cell(self, p, markup, x: int, w: int, align: str, y: int) -> None:
        spans = p.text.elide(markup, w)
        if align == "right":
            p.write(x + w, y, spans, right=True)
        elif align == "center":
            p.write(x + (w - p.text.width(spans)) // 2, y, spans)
        else:
            p.write(x, y, spans)

    def render(self, p: Painter) -> None:
        th = p.theme
        c = self.content
        total = len(self.rows)
        y0 = c.y + self._header_h(p)
        self._visible = max(1, (c.bottom - y0) // p.row)
        self.cursor_row = max(0, min(self.cursor_row, total - 1))
        self._top = max(0, min(self._top, total - self._visible))
        bar = p.ch if total > self._visible else 0
        inner = p.ch // 2  # seçim şeridinin içinde yazıya nefes
        x = c.x + inner
        self._edges = []
        for w in self._widths(p, c.w - bar - inner * 2):
            self._edges.append((x, w))
            x += w + p.ch * self.GAP

        for k, (col, (x, w)) in enumerate(zip(self.columns, self._edges)):
            spans = [(col.label, Style(bold=True, fg=th.dim))]
            if self.sorted_by is not None and self.sorted_by[0] == k:
                spans.append((" ▼" if self.sorted_by[1] else " ▲", Style(fg=th.accent)))
            self._cell(p, spans, x, w, col.align, c.y)
        p.surface.fill(th.border, (c.x, c.y + p.row + 1, c.w - bar, 1))

        if not self.rows:
            p.write(c.x + inner, y0, self.placeholder, color=th.faint)
            return
        focused = self.has_focus
        for row in range(min(self._visible, total - self._top)):
            i = self._top + row
            cells, _ = self.rows[i]
            y = y0 + row * p.row
            rect = (c.x, y, c.w - bar, p.row)
            fg = None
            if i == self.cursor_row and self.show_cursor:
                fg = p.selection(rect, focused=focused)
            elif i == self._hover:
                p.hover(rect)
            elif self.zebra and i % 2:
                p.round_rect(rect, mix(p.panel_bg, th.raised, 0.35), radius=0)
            for col, (x, w), cell in zip(self.columns, self._edges, cells):
                self._cell(p, [(plain_text(cell), Style(bold=True, fg=fg))] if fg else cell, x, w, col.align, y)
        p.scrollbar(c.right - 2, y0, self._visible * p.row, total, self._visible, self._top, active=focused)

    # ── fare ──────────────────────────────────────────────

    def _row_at(self, y: int) -> int | None:
        p = self.app.painter
        y0 = self.content.y + self._header_h(p)
        if y < y0:
            return None
        row = (y - y0) // p.row
        i = self._top + row
        return i if row < self._visible and i < len(self.rows) else None

    def _column_at(self, x: int) -> int | None:
        gap = self.app.painter.ch * self.GAP
        return next((k for k, (cx, w) in enumerate(self._edges) if cx - gap // 2 <= x < cx + w + gap // 2), None)

    def on_click(self, event: Click) -> None:
        if self.sortable and event.y < self.content.y + self._header_h(self.app.painter):
            k = self._column_at(event.x)
            if k is not None:
                event.stop()
                self.sort(k, reverse=self.sorted_by == (k, False))
            return
        i = self._row_at(event.y)
        if i is None:
            return
        event.stop()
        self.move_cursor(i)
        if event.count == 2:
            self.post_message(Table.RowSelected(self, i, self.rows[i][1]))

    def on_mouse_move(self, event: MouseMove) -> None:
        i = self._row_at(event.y)
        if i != self._hover:
            self._hover = i
            self.refresh()

    def on_mouse_leave(self) -> None:
        self._hover = None
        self.refresh()

    def on_mouse_scroll(self, event: MouseScroll) -> None:
        event.stop()
        self._top = max(0, min(self._top - event.dy * 3, len(self.rows) - self._visible))
        self.refresh()

    # ── klavye ────────────────────────────────────────────

    @action("Yukarı", key="up", show=False, palette=False)
    def cursor_up(self) -> None:
        self.move_cursor(self.cursor_row - 1)

    @action("Aşağı", key="down", show=False, palette=False)
    def cursor_down(self) -> None:
        self.move_cursor(self.cursor_row + 1)

    @action("Sayfa yukarı", key="pageup", show=False, palette=False)
    def page_up(self) -> None:
        self.move_cursor(self.cursor_row - max(1, self._visible - 1))

    @action("Sayfa aşağı", key="pagedown", show=False, palette=False)
    def page_down(self) -> None:
        self.move_cursor(self.cursor_row + max(1, self._visible - 1))

    @action("Başa", key="home", show=False, palette=False)
    def cursor_home(self) -> None:
        self.move_cursor(0)

    @action("Sona", key="end", show=False, palette=False)
    def cursor_end(self) -> None:
        self.move_cursor(len(self.rows) - 1)

    @action("Satırı seç", key="enter", show=False, palette=False)
    def select_row(self) -> None:
        if self.rows:
            self.post_message(Table.RowSelected(self, self.cursor_row, self.cursor_key))
