"""Komut paleti: Ctrl+P ile açılır.

Odaktaki bileşenden uygulamaya kadar bütün @action'ları (palette=False olanlar hariç) ve
uygulamanın get_commands() ile verdiği komutları bulanık aramayla listeler. Türkçe harfler
gevşek eşleşir: "baslat" yazınca "Başlat" da bulunur.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pygame

from . import keys
from .events import Click, MouseMove, MouseScroll
from .fuzzy import match, score
from .text import Style
from .widget import Screen, Widget, action
from .widgets import Input, Panel


@dataclass
class Command:
    """Paletteki bir komut. key yalnızca gösterim içindir; kısayolu bağlamaz."""

    label: str
    run: Callable
    key: str | None = None


def _highlight(label: str, positions: list[int], inverse: bool) -> str:
    """Eşleşen harfleri vurgula; ters renkli satırda renk yerine altı çizili kalın."""
    hits, tag = set(positions), "bold u" if inverse else "bold accent"
    out = []
    for i, ch in enumerate(label):
        ch = "\\[" if ch == "[" else ch
        out.append(f"[{tag}]{ch}[/]" if i in hits else ch)
    return "".join(out)


class _CommandList(Widget):
    """Sonuç listesi: eşleşen harfler vurgulu, sağda kısayol."""

    default_height = "auto"
    MAX_ROWS = 10

    def __init__(self, palette: CommandPalette) -> None:
        super().__init__()
        self.palette = palette
        self._top = 0
        self._hover: int | None = None

    def _rows(self) -> int:
        return max(1, min(self.MAX_ROWS, len(self.palette.matches)))

    def measure(self, p, width: int) -> tuple[int, int]:
        return 0, self._rows() * p.row + p.row // 2

    def _row_at(self, y: int) -> int | None:
        p = self.app.painter
        row = (y - self.content.y - p.row // 2) // p.row
        i = self._top + row
        return i if 0 <= row < self._rows() and i < len(self.palette.matches) else None

    def render(self, p) -> None:
        th = p.theme
        c = self.content
        p.surface.fill(th.border, (c.x, c.y + p.row // 4, c.w, 1))
        y0 = c.y + p.row // 2
        matches = self.palette.matches
        if not matches:
            p.write(c.x, y0, "eşleşen komut yok", color=th.faint)
            return
        rows, sel = self._rows(), self.palette.index
        if sel < self._top:
            self._top = sel
        elif sel >= self._top + rows:
            self._top = sel - rows + 1
        self._top = max(0, min(self._top, len(matches) - rows))
        text_x = c.x + p.text.width("❯ ")  # sorgu yazısıyla aynı hizada
        for row, (command, positions) in enumerate(matches[self._top:self._top + rows]):
            i = self._top + row
            y = y0 + row * p.row
            rect = pygame.Rect(c.x, y, c.w, p.row)
            fg = None
            if i == sel:
                fg = p.selection(rect)
                if th.selection == "pointer":
                    p.write(c.x, y, "❯", Style(bold=True), th.accent)
            elif i == self._hover:
                p.hover(rect)
            p.write(text_x, y, _highlight(command.label, positions, fg is not None),
                    color=fg or (th.text if i == sel else th.dim))
            if command.key and fg:  # ters renkli şeritte tuş kutusu şeridi bölmesin
                p.write(c.right - p.ch // 2, y, [(keys.display(command.key), Style())], color=fg, font=p.small, right=True)
            elif command.key:
                p.keycap(c.right - p.ch // 2, y, keys.display(command.key), right=True)

    def on_mouse_move(self, event: MouseMove) -> None:
        i = self._row_at(event.y)
        if i != self._hover:
            self._hover = i
            self.refresh()

    def on_mouse_leave(self) -> None:
        self._hover = None
        self.refresh()

    def on_click(self, event: Click) -> None:
        i = self._row_at(event.y)
        if i is not None:
            event.stop()
            self.palette.index = i
            self.palette.run_selected()

    def on_mouse_scroll(self, event: MouseScroll) -> None:
        event.stop()
        self.palette.move(-event.dy)


class CommandPalette(Screen):
    """Ctrl+P ile açılan modal komut listesi: yaz, ↑/↓ ile seç, Enter ile çalıştır, Esc ile kapat."""

    modal = True

    def __init__(self, commands: list[Command]) -> None:
        super().__init__()
        self.commands = commands
        self.matches: list[tuple[Command, list[int]]] = [(c, []) for c in commands]
        self.index = 0
        self.box: Panel | None = None
        self.results = _CommandList(self)

    def compose(self):
        with Panel(title="Komutlar", info="[faint]ctrl+p[/]", footer="[faint]↑↓ seç · ⏎ çalıştır · esc kapat[/]",
                   floating=True) as box:
            self.box = box
            yield Input(placeholder="komut ara…", id="palette-query")
            yield self.results

    def arrange(self, p) -> None:
        r = self.region
        w = min(r.w - p.ch * 6, p.ch * 64)
        h = self.box.natural_size(p, w)[1]
        self.box._layout(p, pygame.Rect(r.x + (r.w - w) // 2, r.y + round(r.h * 0.17), w, h))

    def render(self, p) -> None:
        p.shadow(self.box.frame)

    def filter(self, query: str) -> None:
        found = []
        for n, command in enumerate(self.commands):
            positions = match(query, command.label) if query else []
            if positions is not None:
                found.append((score(positions), n, command, positions))
        found.sort(key=lambda f: (f[0], f[1]))
        self.matches = [(command, positions) for _, _, command, positions in found]
        self.index = 0
        self.results.refresh(layout=True)

    def move(self, step: int) -> None:
        if self.matches:
            self.index = (self.index + step) % len(self.matches)
            self.refresh()

    def run_selected(self) -> None:
        if not self.matches:
            return
        command = self.matches[self.index][0]
        app = self.app
        self.dismiss()  # önce kapan: komut, paletten önceki odakla çalışsın
        app._call(command.run)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.filter(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.run_selected()

    def on_click(self, event: Click) -> None:
        if not self.box.region.collidepoint(event.pos):  # kutunun dışına tıklamak kapatır
            self.dismiss()

    @action("Kapat", key="escape", hint="kapat", palette=False)
    def close(self) -> None:
        self.dismiss()

    @action("Yukarı", key="up,shift+tab", show=False, palette=False)
    def cursor_up(self) -> None:
        self.move(-1)

    @action("Aşağı", key="down,tab", show=False, palette=False)
    def cursor_down(self) -> None:
        self.move(1)

    @action("Sayfa yukarı", key="pageup", show=False, palette=False)
    def page_up(self) -> None:
        if self.matches:
            self.index = max(0, self.index - _CommandList.MAX_ROWS)
            self.refresh()

    @action("Sayfa aşağı", key="pagedown", show=False, palette=False)
    def page_down(self) -> None:
        if self.matches:
            self.index = min(len(self.matches) - 1, self.index + _CommandList.MAX_ROWS)
            self.refresh()
