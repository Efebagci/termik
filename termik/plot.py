"""Grafik verisi ve ölçeği: seriler, eksen adımları, sayı biçimi ve yazıyla (terminal) çizim.

pygame istemez: Chart bileşeni de, akış API'sinin terminal kipi de bunu kullanır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

KINDS = ("line", "area", "bar")
PALETTE = ("accent", "accent2", "green", "yellow", "magenta", "cyan", "blue", "red")
_BLOCKS = " ▁▂▃▄▅▆▇█"
Number = int | float


def fmt(value: Number) -> str:
    """Kısa Türkçe sayı: 12400 → '12.400', 0.25 → '0,25', 3.0 → '3'."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    if float(value).is_integer() and abs(value) < 1e15:
        return f"{int(value):,}".replace(",", ".")
    magnitude = abs(value)
    places = 0 if magnitude >= 1000 else 1 if magnitude >= 10 else 2 if magnitude >= 0.1 else 4
    text = f"{value:,.{places}f}".rstrip("0").rstrip(".")
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """lo..hi aralığını kapsayan yuvarlak eksen değerleri (1-2-2,5-5 adımlarla)."""
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        lo, hi = (lo - 1, hi + 1) if lo else (0, 1)
    raw = (hi - lo) / max(1, count - 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw - 1e-12)
    start, end = math.floor(lo / step + 1e-9) * step, math.ceil(hi / step - 1e-9) * step
    return [round(start + i * step, 10) for i in range(int(round((end - start) / step)) + 1)]


@dataclass
class Series:
    """Bir veri serisi: adı, değerleri ve rengi (tema adı, "#ff8800" ya da (r, g, b); None: sıradaki)."""

    name: str
    values: list[float] = field(default_factory=list)
    color: str | tuple[int, int, int] | None = None


class ChartData:
    """Grafiğin verisi: seriler, x etiketleri, eksen sınırları. Chart bileşeni bunu çizer.

    data: sayı listesi (tek seri), {ad: liste} (birden çok seri) ya da {etiket: sayı} (kategoriler).
    max_points verilirse her seride en son o kadar değer tutulur (canlı veri için).
    """

    def __init__(self, data: Any = None, *, kind: str = "line", title: str | None = None,
                 x: Iterable | None = None, y_min: Number | None = None, y_max: Number | None = None,
                 max_points: int | None = None, y_format: str | Callable[[Number], str] | None = None) -> None:
        if kind not in KINDS:
            raise ValueError(f"grafik türü {', '.join(KINDS)} olabilir, {kind!r} geldi")
        self.kind, self.title = kind, title
        self.y_min, self.y_max, self.max_points, self.y_format = y_min, y_max, max_points, y_format
        self.series: list[Series] = []
        self.x: list[str] | None = [str(v) for v in x] if x is not None else None
        self.named = False  # seriler adlarıyla mı verildi (gösterge buna göre)
        self.on_change: Callable[[], None] | None = None
        self.set_data(data)

    # ── veri ─────────────────────────────────────────────

    def set_data(self, data: Any) -> None:
        """Bütün veriyi değiştir (biçimler yukarıdaki gibi)."""
        self.series = []
        if isinstance(data, dict):
            values = list(data.values())
            if values and all(isinstance(v, (int, float)) for v in values):  # {"Ocak": 12, …}
                self.x = [str(k) for k in data]
                self.series.append(Series("değer", [float(v) for v in values]))
            else:
                self.named = True
                for name, items in data.items():
                    self.series.append(Series(str(name), [float(v) for v in items or ()]))
        elif data is not None:
            self.series.append(Series("değer", [float(v) for v in data]))
        self._trim()
        self._changed()

    def add_series(self, name: str, values: Iterable[Number] = (), *,
                   color: str | tuple[int, int, int] | None = None) -> Series:
        """Yeni seri ekle (aynı adda varsa onun değerleri değişir)."""
        self.named = True
        series = self.get(name)
        if series is None:
            series = Series(name, color=color)
            self.series.append(series)
        series.values = [float(v) for v in values]
        if color is not None:
            series.color = color
        self._trim()
        self._changed()
        return series

    def get(self, name: str) -> Series | None:
        return next((s for s in self.series if s.name == name), None)

    def append(self, name_or_value: str | Number, value: Number | None = None, *, label: Any = None) -> None:
        """Canlı veri: append(42) ilk seriye, append("cpu", 42) adı verilen seriye ekler (yoksa açılır).
        label= o noktanın x etiketidir; max_points aşılınca en eski değerler düşer."""
        if isinstance(name_or_value, str):
            series = self.get(name_or_value) or self.add_series(name_or_value)
            series.values.append(float(value))
        else:
            if not self.series:
                self.series.append(Series("değer"))
            self.series[0].values.append(float(name_or_value))
        if label is not None:
            self.x = (self.x or [])
            self.x.append(str(label))
        self._trim()
        self._changed()

    def extend(self, name: str, values: Iterable[Number]) -> None:
        series = self.get(name) or self.add_series(name)
        series.values.extend(float(v) for v in values)
        self._trim()
        self._changed()

    def clear(self) -> None:
        """Değerleri sil; seriler (adları, renkleri) kalır."""
        for series in self.series:
            series.values.clear()
        if self.x is not None:
            self.x = []
        self._changed()

    def _trim(self) -> None:
        if self.max_points:
            for series in self.series:
                del series.values[:-self.max_points]
            if self.x is not None:
                del self.x[:-self.max_points]

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()

    # ── ölçek ve etiketler ───────────────────────────────

    @property
    def count(self) -> int:
        """En uzun serinin nokta sayısı."""
        return max((len(s.values) for s in self.series), default=0)

    def value_range(self) -> tuple[float, float]:
        """Görünen değer aralığı: verilen sınırlar ya da verinin uçları (çubuk ve alanda sıfır dahil)."""
        values = [v for s in self.series for v in s.values]
        lo = min(values, default=0.0)
        hi = max(values, default=1.0)
        if self.kind in ("bar", "area"):
            lo, hi = min(lo, 0.0), max(hi, 0.0)
        lo = self.y_min if self.y_min is not None else lo
        hi = self.y_max if self.y_max is not None else hi
        return lo, hi

    def label(self, i: int) -> str:
        """i'nci noktanın x etiketi (verilmediyse sırası)."""
        if self.x is not None and i < len(self.x):
            return self.x[i]
        return str(i + 1) if self.kind == "bar" else str(i)

    def format(self, value: Number) -> str:
        if self.y_format is None:
            return fmt(value)
        return self.y_format(value) if callable(self.y_format) else self.y_format.format(value)

    def colors(self) -> list[str | tuple[int, int, int]]:
        """Serilerin renkleri: verilmeyenlere paletten sırayla."""
        return [s.color if s.color is not None else PALETTE[i % len(PALETTE)] for i, s in enumerate(self.series)]

    # ── yazıyla çizim (terminal) ─────────────────────────

    def text_lines(self, width: int = 56, height: int = 8) -> list[str]:
        """Terminal için markup satırları: çizgi ve alan ▁▃▇ bloklarıyla, çubuk yatay ███ olarak."""
        out = [f"[bold]{self.title}[/]"] if self.title else []
        colors = self.colors()
        if not self.series or not self.count:
            return out + ["[faint](veri yok)[/]"]
        if self.kind == "bar":
            labels = [self.label(i) for i in range(self.count)]
            room = max(len(label) for label in labels)
            hi = max((abs(v) for s in self.series for v in s.values), default=1.0) or 1.0
            for i, label in enumerate(labels):
                for series, color in zip(self.series, colors):
                    if i >= len(series.values):
                        continue
                    value = series.values[i]
                    bar = "█" * max(1 if value else 0, round(abs(value) / hi * (width - room - 10)))
                    name = label if series is self.series[0] else ""
                    out.append(f"{name:<{room}}  [{color}]{bar}[/] {self.format(value)}")
            return out
        lo, hi = self.value_range()
        span = (hi - lo) or 1.0
        top, bottom = self.format(hi), self.format(lo)
        gutter = max(len(top), len(bottom))
        rows = max(2, height)
        series, color = self.series[0], colors[0]
        values = series.values
        cols = [values[min(len(values) - 1, int(c * len(values) / width))] for c in range(width)] if values else []
        levels = [round((v - lo) / span * rows * 8) for v in cols]
        for r in range(rows - 1, -1, -1):
            cells = "".join(_BLOCKS[max(0, min(8, level - r * 8))] for level in levels)
            axis = top if r == rows - 1 else bottom if r == 0 else ""
            out.append(f"[dim]{axis:>{gutter}}[/] [faint]┤[/][{color}]{cells}[/]")
        legend = "   ".join(f"[{c}]━[/] {s.name} [dim]{self.format(s.values[-1]) if s.values else '–'}[/]"
                           for s, c in zip(self.series, colors))
        if self.named or len(self.series) > 1:
            out.append(" " * (gutter + 2) + legend)
        return out
