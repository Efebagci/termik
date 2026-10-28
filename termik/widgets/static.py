"""Yazı bileşenleri."""

from __future__ import annotations

from ..reactive import reactive
from ..widget import Widget

_NO_WRAP = 10**9  # kaydırma kapalıyken yalnızca "\n"de bölmek için


class Static(Widget):
    """Markup yazı ("[bold green]✓[/] Bitti"). Genişliğe göre satır kaydırır; update() ile değişir."""

    default_height = "auto"
    text = reactive("", layout=True)

    def __init__(self, text: str = "", *, wrap: bool = True, align: str = "left", **kwargs) -> None:
        super().__init__(**kwargs)
        self.wrap = wrap
        self.align = align  # left · center · right
        self.text = text

    def update(self, text: str) -> None:
        self.text = text

    def _lines(self, p, width: int):
        return p.text.wrap(self.text, max(1, width) if self.wrap else _NO_WRAP)

    def measure(self, p, width: int) -> tuple[int, int]:
        lines = self._lines(p, width)
        return max((p.text.width(line) for line in lines), default=0), len(lines) * p.row

    def render(self, p) -> None:
        c = self.content
        for i, line in enumerate(self._lines(p, c.w)):
            if not self.wrap:
                line = p.text.elide(line, c.w)
            x = c.x
            if self.align != "left":
                free = c.w - p.text.width(line)
                x += free if self.align == "right" else free // 2
            p.write(x, c.y + i * p.row, line)


class Label(Static):
    """Satır kaydırmayan, sığmazsa '…' ile kısalan kısa yazı."""

    def __init__(self, text: str = "", *, wrap: bool = False, **kwargs) -> None:
        super().__init__(text, wrap=wrap, **kwargs)
