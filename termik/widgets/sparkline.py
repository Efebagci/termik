"""Mini grafik."""

from __future__ import annotations

from typing import Callable

from ..widget import Widget


class Sparkline(Widget):
    """Akan değerler için mini grafik: en yenisi sağda, eskiler soluklaşır.

        cpu = Sparkline(label="CPU", value_format="{:.0%}", max_value=1.0)
        cpu.append(0.42)

    max_value verilmezse görünen değerlerin en büyüğüne göre ölçeklenir. value_format bir
    biçim dizgesi ya da fonksiyon olabilir; son değer sağda yazılır. Bileşen bir satırdan
    yüksekse çubuklar bütün yüksekliği kullanır.
    """

    default_height = "auto"

    def __init__(self, data=None, *, label: str | None = None, value_format: str | Callable | None = None,
                 max_value: float | None = None, color: str = "green", maxlen: int = 240, **kwargs) -> None:
        super().__init__(**kwargs)
        self.data: list[float] = list(data or [])[-maxlen:]
        self.label, self.value_format, self.max_value = label, value_format, max_value
        self.color, self.maxlen = color, maxlen

    def append(self, value: float) -> None:
        self.data.append(value)
        del self.data[: -self.maxlen]
        self.refresh()

    def measure(self, p, width: int) -> tuple[int, int]:
        return p.ch * 16, p.row

    def _format(self, value: float) -> str:
        fmt = self.value_format
        return fmt.format(value) if isinstance(fmt, str) else fmt(value)

    def render(self, p) -> None:
        th = p.theme
        c = self.content
        x, right = c.x, c.right
        if self.label:
            p.write(x, c.y + (c.h - p.row) // 2, self.label, color=th.dim)
            x += max(p.ch * 5, p.text.width(self.label) + p.ch)
        if self.value_format is not None and self.data:
            text = self._format(self.data[-1])
            p.write(right, c.y + (c.h - p.row) // 2, text, right=True)
            right -= max(p.ch * 6, p.text.width(text) + p.ch)  # sayının yeri sabit: çubuklar oynamasın
        values = self.data[-max(1, (right - x) // p.ch):]
        if not values:
            return
        top = self.max_value if self.max_value is not None else max(max(values), 1e-9)
        h = c.h - 2 if c.h > p.row else p.text.height
        y = c.y + (c.h - h) // 2 - (p.row - h) // 2  # spark() yüksekliği satıra göre ortalar
        p.spark(right - len(values) * p.ch, y, [max(0.0, v / top) for v in values],
                th.color(self.color) or th.green, height=h)
