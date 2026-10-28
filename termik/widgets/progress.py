"""İlerleme çubuğu."""

from __future__ import annotations

from ..reactive import reactive
from ..widget import Widget


class ProgressBar(Widget):
    """İlerleme çubuğu: progress 0..1, sağında yüzde. Çubuk biçimi temadan (bar) gelir;
    style= ile tek bir çubuk için değiştirilebilir ("block", "segment", "line", "ascii")."""

    default_height = "auto"
    progress = reactive(0.0)

    def __init__(self, progress: float = 0.0, *, show_percent: bool = True, style: str | None = None,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.show_percent = show_percent
        self.bar_style = style
        self.progress = progress

    def advance(self, amount: float) -> None:
        self.progress = min(1.0, self.progress + amount)

    def measure(self, p, width: int) -> tuple[int, int]:
        return p.ch * 20, p.row

    def render(self, p) -> None:
        c = self.content
        value = min(1.0, max(0.0, self.progress))
        room = c.w
        if self.show_percent:
            # yüzdenin yeri sabit: sayı değişince çubuk oynamasın
            room -= p.text.width("[bold]100%[/]") + p.ch
            p.write(c.right, c.y, f"[bold]{round(value * 100)}%[/]", right=True)
        p.bar(c.x, c.y, max(0, room), value, style=self.bar_style)
