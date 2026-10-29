"""Grafik: çizgi, alan ve çubuk."""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable

import pygame

from ..draw import Painter
from ..events import MouseMove
from ..markup import escape
from ..plot import ChartData, Number, Series, nice_ticks
from ..text import Style
from ..theme import Color, mix
from ..widget import Widget

_BOLD = Style(bold=True)


class Chart(Widget):
    """Çizgi, alan ve çubuk grafiği: eksenler, noktalı ızgara, gösterge, fareyle değer.

        cpu = ui.Chart({"cpu": [], "bellek": []}, title="Kullanım %", y_min=0, y_max=100, max_points=60)
        cpu.append("cpu", 42)                                # canlı veri: en yenisi sağda
        ui.Chart({"Ocak": 12, "Şubat": 30}, kind="bar")       # kategoriler
        ui.Chart([3, 1, 4, 1, 5], kind="area", x=["pzt", "sal", "çar", "per", "cum"])

    data: sayı listesi (tek seri), {ad: liste} (birden çok seri) ya da {etiket: sayı} (kategoriler).
    kind: "line", "area" ya da "bar" (birden çok seride yan yana çubuklar). y_min / y_max ekseni
    sabitler; verilmezse veriden bulunur. max_points canlı veride tutulacak son nokta sayısı.
    y_format değerleri biçimler ("{:.0f} %" ya da fonksiyon). Gösterge (legend) birden çok seri ya da
    adlı seriler varken başlık satırının sağında durur.

    Görünüşü temadaki chart belirtecinden gelir: smooth yumuşak kenarlı çizgiler, braille ⣀⡠ noktaları,
    blocks ▁▃▇ blokları. Fare üstündeyken en yakın noktanın bütün serilerdeki değerleri gösterilir.
    """

    default_height = 12

    def __init__(self, data: Any = None, *, kind: str = "line", title: str | None = None,
                 x: Iterable | None = None, y_min: Number | None = None, y_max: Number | None = None,
                 max_points: int | None = None, y_format: str | Callable[[Number], str] | None = None,
                 legend: bool | None = None, grid: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self.data = ChartData(data, kind=kind, title=title, x=x, y_min=y_min, y_max=y_max,
                              max_points=max_points, y_format=y_format)
        self.data.on_change = self.refresh
        self.legend, self.grid = legend, grid
        self._mouse: tuple[int, int] | None = None
        self._plot = pygame.Rect(0, 0, 0, 0)

    # ── veri (ChartData'ya iletilir) ─────────────────────

    @property
    def series(self) -> list[Series]:
        return self.data.series

    @property
    def kind(self) -> str:
        return self.data.kind

    @kind.setter
    def kind(self, value: str) -> None:
        self.data.kind = value
        self.refresh()

    @property
    def title(self) -> str | None:
        return self.data.title

    @title.setter
    def title(self, value: str | None) -> None:
        self.data.title = value
        self.refresh()

    def set_data(self, data: Any) -> None:
        self.data.set_data(data)

    def add_series(self, name: str, values: Iterable[Number] = (), *,
                   color: str | tuple[int, int, int] | None = None) -> Series:
        return self.data.add_series(name, values, color=color)

    def append(self, name_or_value: str | Number, value: Number | None = None, *, label: Any = None) -> None:
        """append(42) ilk seriye, append("cpu", 42) adı verilen seriye; label= x etiketi."""
        self.data.append(name_or_value, value, label=label)

    def extend(self, name: str, values: Iterable[Number]) -> None:
        self.data.extend(name, values)

    def clear(self) -> None:
        self.data.clear()

    def text_lines(self, width: int = 56, height: int = 8) -> list[str]:
        return self.data.text_lines(width, height)

    # ── yerleşim ─────────────────────────────────────────

    def _show_legend(self) -> bool:
        return self.legend if self.legend is not None else (self.data.named or len(self.series) > 1)

    def _layout_parts(self, p: Painter) -> tuple[pygame.Rect, list[float], int]:
        """Çizim alanı, y ekseni değerleri ve sol etiket sütununun genişliği."""
        c = self.content
        header = p.row if (self.title or self._show_legend()) else 0
        top = c.y + header + p.row // 2
        height = max(p.row, c.bottom - p.row - top)
        lo, hi = self.data.value_range()
        ticks = nice_ticks(lo, hi, max(2, min(6, height // (p.row * 2) + 1)))
        if self.data.y_min is not None:
            ticks = [t for t in ticks if t >= self.data.y_min] or [self.data.y_min]
        if self.data.y_max is not None:
            ticks = [t for t in ticks if t <= self.data.y_max] or [self.data.y_max]
        gutter = max(p.text.width(self.data.format(t)) for t in ticks) + p.ch
        plot = pygame.Rect(c.x + gutter + p.ch // 2, top, max(1, c.w - gutter - p.ch), height)
        return plot, ticks, gutter

    def _y(self, value: float, plot: pygame.Rect, lo: float, hi: float) -> float:
        return plot.bottom - (value - lo) / ((hi - lo) or 1) * plot.h

    def _xs(self, plot: pygame.Rect, n: int) -> list[float]:
        """Noktaların x'leri: çizgi ve alanda uçtan uca, çubukta dilimlerin ortası."""
        if n <= 0:
            return []
        if self.kind == "bar":
            slot = plot.w / n
            return [plot.x + slot * (i + 0.5) for i in range(n)]
        if n == 1:
            return [plot.centerx]
        return [plot.x + i * (plot.w - 1) / (n - 1) for i in range(n)]

    def _colors(self, p: Painter) -> list[Color]:
        out = []
        for value in self.data.colors():
            out.append(p.theme.color(value) or p.theme.accent if isinstance(value, str) else tuple(value))
        return out

    # ── çizim ─────────────────────────────────────────────

    def render(self, p: Painter) -> None:
        th = p.theme
        c = self.content
        plot, ticks, gutter = self._layout_parts(p)
        self._plot = plot
        lo, hi = ticks[0], ticks[-1]
        colors = self._colors(p)
        if self.title:
            p.write(c.x, c.y, [(self.title, _BOLD)], color=th.text)
        if self._show_legend():
            self._draw_legend(p, c, colors)
        # y ekseni: etiketler, çentikler, noktalı ızgara
        for t in ticks:
            y = round(self._y(t, plot, lo, hi))
            p.write(plot.x - p.ch // 2 - p.ch // 2, y - p.row // 2, self.data.format(t), color=th.dim, right=True)
            p.surface.fill(th.border, (plot.x - 4, y, 4, 1))
            if self.grid and t != lo:
                dot = mix(th.bg, th.faint, 0.7)
                for x in range(plot.x + p.ch // 2, plot.right, p.ch):
                    p.surface.fill(dot, (x, y, 2, 1))
        p.surface.fill(th.border, (plot.x - 1, plot.y, 1, plot.h + 1))
        base = round(self._y(max(lo, min(hi, 0.0)), plot, lo, hi)) if lo <= 0 <= hi else plot.bottom
        p.surface.fill(th.border, (plot.x - 1, plot.bottom, plot.w + 1, 1))
        n = self.data.count
        if not n:
            p.write(plot.centerx, plot.centery - p.row // 2, "[faint]veri yok[/]")
            return
        xs = self._xs(plot, n)
        self._draw_x_labels(p, plot, xs)
        style = th.chart
        with p.clip(plot.inflate(2, 2)):
            if self.kind == "bar":
                self._draw_bars(p, plot, xs, lo, hi, base, colors, style)
            elif style == "braille":
                self._draw_braille(p, plot, xs, lo, hi, colors)
            elif style == "blocks":
                self._draw_blocks(p, plot, xs, lo, hi, base, colors)
            else:
                self._draw_smooth(p, plot, xs, lo, hi, base, colors)
        self._draw_hover(p, plot, xs, lo, hi, colors)

    def _draw_legend(self, p: Painter, c: pygame.Rect, colors: list[Color]) -> None:
        x = c.right
        for series, color in reversed(list(zip(self.series, colors))):
            x -= p.text.width(series.name)
            p.write(x, c.y, escape(series.name), color=p.theme.dim)
            x -= p.ch + p.ch // 2
            p.surface.fill(color, (x, c.y + p.row // 2 - 1, p.ch, 3))
            x -= p.ch * 2

    def _draw_x_labels(self, p: Painter, plot: pygame.Rect, xs: list[float]) -> None:
        labels = [self.data.label(i) for i in range(len(xs))]
        widest = max(p.text.width(label) for label in labels) + p.ch * 2
        spacing = (xs[1] - xs[0]) if len(xs) > 1 else plot.w
        stride = max(1, math.ceil(widest / max(1, spacing)))
        last = len(xs) - 1
        for i in range(0, len(xs), stride):
            if self.kind != "bar" and last - i < stride and i != last and last % stride:
                continue  # son etiket gösterilecekse ona yer bırak
            self._x_label(p, plot, xs[i], labels[i])
        if self.kind != "bar" and last % stride:
            self._x_label(p, plot, xs[last], labels[last])

    def _x_label(self, p: Painter, plot: pygame.Rect, x: float, label: str) -> None:
        w = p.text.width(label)
        left = max(self.content.x, min(round(x - w / 2), self.content.right - w))
        p.surface.fill(p.theme.border, (round(x), plot.bottom, 1, 4))
        p.write(left, plot.bottom + 4, label, color=p.theme.dim)

    def _points(self, series: Series, plot: pygame.Rect, xs: list[float], lo: float, hi: float) -> list[tuple]:
        return [(xs[i], self._y(v, plot, lo, hi)) for i, v in enumerate(series.values[:len(xs)])]

    def _draw_smooth(self, p: Painter, plot, xs, lo, hi, base, colors) -> None:
        for series, color in zip(self.series, colors):
            pts = self._points(series, plot, xs, lo, hi)
            if not pts:
                continue
            if self.kind == "area" and len(pts) > 1:
                fill = mix(p.theme.bg, color, 0.28)
                pygame.draw.polygon(p.surface, fill, [*pts, (pts[-1][0], base), (pts[0][0], base)])
            if len(pts) == 1:
                pygame.draw.circle(p.surface, color, (round(pts[0][0]), round(pts[0][1])), 3)
                continue
            pygame.draw.lines(p.surface, color, False, pts, 2)
            pygame.draw.aalines(p.surface, color, False, [(x, y - 0.5) for x, y in pts])
            pygame.draw.aalines(p.surface, color, False, [(x, y + 0.5) for x, y in pts])

    def _draw_bars(self, p: Painter, plot, xs, lo, hi, base, colors, style: str) -> None:
        n, k = len(xs), max(1, len(self.series))
        slot = plot.w / max(1, n)
        group = slot * 0.7
        bar_w = max(2, group / k - (2 if k > 1 else 0))
        if style in ("blocks", "braille"):  # karakter ızgarasına otur
            bar_w = max(p.ch - 2, (int(group / k) // p.ch) * p.ch - 2)
        for i, x in enumerate(xs):
            for j, (series, color) in enumerate(zip(self.series, colors)):
                if i >= len(series.values):
                    continue
                left = x - group / 2 + j * (group / k)
                y = self._y(series.values[i], plot, lo, hi)
                top, bottom = (y, base) if y < base else (base, y)
                rect = pygame.Rect(round(left), round(top), round(bar_w), max(1, round(bottom - top)))
                if style == "blocks":
                    self._block_column(p, rect, color, from_top=y >= base)
                elif style == "braille":
                    self._dot_column(p, rect, color)
                else:
                    p.surface.fill(color, rect)

    def _block_column(self, p: Painter, rect: pygame.Rect, color: Color, from_top: bool = False) -> None:
        """Bloklarla dolu sütun: yükseklik satırın sekizde biri adımlarla, hücreler arası 1 piksel."""
        step = max(1, p.row // 8)
        h = max(step, round(rect.h / step) * step)
        y = rect.y if from_top else rect.bottom - h
        for cx in range(rect.x, rect.right, p.ch):
            p.surface.fill(color, (cx, y, min(p.ch - 1, rect.right - cx), h))

    def _dot_column(self, p: Painter, rect: pygame.Rect, color: Color) -> None:
        r = max(1, p.ch // 6)
        for cx in range(rect.x, rect.right, max(2, p.ch // 2)):
            for cy in range(rect.bottom - r, rect.y, -max(2, p.row // 4)):
                pygame.draw.circle(p.surface, color, (cx + r, cy), r)

    def _draw_blocks(self, p: Painter, plot, xs, lo, hi, base, colors) -> None:
        """Her karakter sütunu bir blok: alan dolu sütun, çizgi kalın basamak."""
        cols = max(1, plot.w // p.ch)
        for series, color in zip(self.series, colors):
            values = series.values[:len(xs)]
            if not values:
                continue
            for col in range(cols):
                v = values[min(len(values) - 1, round(col * (len(values) - 1) / max(1, cols - 1)))] if len(values) > 1 \
                    else values[0]
                y = self._y(v, plot, lo, hi)
                x = plot.x + col * p.ch
                if self.kind == "area":
                    top = min(y, base)
                    self._block_column(p, pygame.Rect(x, round(top), p.ch, max(1, round(abs(base - y)))), color,
                                       from_top=y > base)
                else:
                    step = max(2, p.row // 4)
                    p.surface.fill(color, (x, round(y) - step // 2, p.ch - 1, step))

    def _draw_braille(self, p: Painter, plot, xs, lo, hi, colors) -> None:
        """Braille gibi: hücre başına 2×4 nokta; çizgiler nokta ızgarasında çizilir, alanın altı dolar."""
        dx, dy = max(2, p.ch / 2), max(2, p.row / 4)
        cols, rows = max(1, int(plot.w / dx)), max(1, int(plot.h / dy))
        r = max(1, round(min(dx, dy) / 3))
        for series, color in zip(self.series, colors):
            pts = [((x - plot.x) / dx, (y - plot.y) / dy) for x, y in self._points(series, plot, xs, lo, hi)]
            dots: set[tuple[int, int]] = set()
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]) if len(pts) > 1 else [(pts[0], pts[0])] if pts else []:
                steps = max(1, int(max(abs(x2 - x1), abs(y2 - y1))))
                for s in range(steps + 1):
                    t = s / steps
                    dots.add((round(x1 + (x2 - x1) * t), round(y1 + (y2 - y1) * t)))
            if self.kind == "area":
                tops: dict[int, int] = {}
                for gx, gy in dots:
                    tops[gx] = min(tops.get(gx, rows), gy)
                dots |= {(gx, gy) for gx, top in tops.items() for gy in range(top, rows)}
            for gx, gy in dots:
                if 0 <= gx <= cols and 0 <= gy <= rows:
                    pygame.draw.circle(p.surface, color, (round(plot.x + gx * dx), round(plot.y + gy * dy)), r)

    # ── fare ──────────────────────────────────────────────

    def _hover_index(self, xs: list[float]) -> int | None:
        if self._mouse is None or not xs or not self._plot.inflate(0, 8).collidepoint(self._mouse):
            return None
        mx = self._mouse[0]
        return min(range(len(xs)), key=lambda i: abs(xs[i] - mx))

    def _draw_hover(self, p: Painter, plot, xs, lo, hi, colors) -> None:
        i = self._hover_index(xs)
        if i is None:
            return
        th = p.theme
        x = round(xs[i])
        if self.kind == "bar":
            slot = plot.w / len(xs)
            p.hover(pygame.Rect(round(xs[i] - slot / 2), plot.y, round(slot), plot.h))
        else:
            for y in range(plot.y, plot.bottom, 6):
                p.surface.fill(th.dim, (x, y, 1, 3))
            for series, color in zip(self.series, colors):
                if i < len(series.values):
                    y = round(self._y(series.values[i], plot, lo, hi))
                    pygame.draw.circle(p.surface, th.bg, (x, y), 5)
                    pygame.draw.circle(p.surface, color, (x, y), 4)
        lines = [[(self.data.label(i), _BOLD)]]
        rows = [(s, col) for s, col in zip(self.series, colors) if i < len(s.values)]
        for series, _ in rows:
            name = f"{escape(series.name)}  " if len(self.series) > 1 or self.data.named else ""
            lines.append(f"  {name}[bold]{self.data.format(series.values[i])}[/]")
        w = max(p.text.width(line) for line in lines) + p.ch * 2
        h = len(lines) * p.row + p.row // 2
        left = x + p.ch if x + p.ch + w <= self.content.right else x - p.ch - w
        box = pygame.Rect(left, plot.y + p.row // 4, w, h)
        p.round_rect(box, mix(th.bg, th.raised, 0.85), radius=min(th.radius, 4))
        p.outline(box, th.border, radius=min(th.radius, 4))
        for k, line in enumerate(lines):
            y = box.y + p.row // 4 + k * p.row
            p.write(box.x + p.ch, y, line, color=th.text)
            if k:
                color = rows[k - 1][1]
                p.surface.fill(color, (box.x + p.ch, y + p.row // 2 - 1, p.ch - 2, 3))

    def on_mouse_move(self, event: MouseMove) -> None:
        self._mouse = event.pos
        self.refresh()

    def on_mouse_leave(self) -> None:
        self._mouse = None
        self.refresh()
