"""Seçenek listesi."""

from __future__ import annotations

from typing import Callable, Iterable

import pygame

from ..draw import Painter
from ..events import Click, Key, Message, MouseMove, MouseScroll, TextInput
from ..fuzzy import match, score
from ..text import Style, escape
from ..widget import Widget


def _highlight(label: str, positions: list[int], inverse: bool) -> str:
    """Eşleşen harfleri vurgula; ters renkli satırda renk yerine altı çizili kalın."""
    hits, tag = set(positions), "bold u" if inverse else "bold accent"
    return "".join(f"[{tag}]{escape(ch)}[/]" if i in hits else escape(ch) for i, ch in enumerate(label))


class OptionList(Widget):
    """Süzülebilir seçenek listesi: yazdıkça bulanık süzer (Türkçe harfler gevşek eşleşir), ↑/↓ ve
    PgUp/PgDn gezer, ⏎ ya da tık seçer. multi=True ise space işaretler, ctrl+a görünenlerin hepsini
    işaretler ya da kaldırır, ⏎ onaylar.

        OptionList(["Tam", "Artımlı", "Diferansiyel"], index=1, rows=5)

    Etiketler düz yazıdır. İmleç değişince OptionList.Highlighted, tekli seçimde OptionList.Selected,
    çoklu kipte ⏎ ile OptionList.Submitted iletilir; on_select verilirse seçilen sıra (çoklu kipte
    sıraların listesi) onunla da bildirilir.
    """

    default_width = "auto"
    default_height = "auto"
    can_focus = True
    accepts_text = True
    cursor = "hand"

    class Highlighted(Message):
        def __init__(self, option_list: OptionList, index: int) -> None:
            super().__init__()
            self.option_list, self.index = option_list, index

    class Selected(Message):
        def __init__(self, option_list: OptionList, index: int) -> None:
            super().__init__()
            self.option_list, self.index = option_list, index

        @property
        def label(self) -> str:
            return self.option_list.options[self.index]

    class Submitted(Message):
        def __init__(self, option_list: OptionList, indices: list[int]) -> None:
            super().__init__()
            self.option_list, self.indices = option_list, indices

    def __init__(self, options: list[str], *, index: int = 0, multi: bool = False, selected: Iterable[int] = (), rows: int = 8,
                 filterable: bool = True, on_select: Callable | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.options = list(options)
        self.multi = multi
        self.selected: set[int] = set(selected)
        self.rows = rows
        self.accepts_text = filterable
        self.on_select = on_select
        self.query = ""
        self.matches: list[tuple[int, list[int]]] = [(i, []) for i in range(len(self.options))]
        self.cursor_line = max(0, min(index, len(self.options) - 1))
        self._top = 0
        self._hover: int | None = None
        self._longest: tuple[int, int] | None = None  # (karakter genişliği, en uzun seçenek pikseli)

    @property
    def index(self) -> int | None:
        """İmleçteki seçeneğin sırası (süzgeçte eşleşen yoksa None)."""
        return self.matches[self.cursor_line][0] if self.matches else None

    @property
    def value(self) -> str | None:
        """İmleçteki seçeneğin etiketi."""
        i = self.index
        return None if i is None else self.options[i]

    def _moved(self, before: int | None) -> None:
        if self.index != before and self.index is not None:
            self.post_message(OptionList.Highlighted(self, self.index))
        self.refresh()

    def filter(self, query: str) -> None:
        before = self.index
        self.query = query
        if not query:
            self.matches = [(i, []) for i in range(len(self.options))]
            # süzgeç silinince imleç son bakılan seçenekte kalsın
            self.cursor_line = next((n for n, (i, _) in enumerate(self.matches) if i == before), 0)
        else:
            found = []
            for i, label in enumerate(self.options):
                positions = match(query, label)
                if positions is not None:
                    found.append((score(positions), i, positions))
            found.sort(key=lambda f: (f[0], f[1]))
            self.matches = [(i, positions) for _, i, positions in found]
            self.cursor_line = 0
        self.refresh(layout=True)
        self._moved(before)

    def move(self, step: int, wrap: bool = True) -> None:
        if not self.matches:
            return
        before = self.index
        n = self.cursor_line + step
        self.cursor_line = n % len(self.matches) if wrap else max(0, min(len(self.matches) - 1, n))
        self._moved(before)

    def toggle(self) -> None:
        if self.matches:
            self.selected ^= {self.matches[self.cursor_line][0]}
            self.refresh()

    def toggle_all(self) -> None:
        shown = {i for i, _ in self.matches}
        self.selected = self.selected - shown if shown <= self.selected else self.selected | shown
        self.refresh()

    def select(self) -> None:
        """Tekli kipte imleçtekini seç, çoklu kipte işaretlileri onayla."""
        if self.multi:
            picked = sorted(self.selected)
            self.post_message(OptionList.Submitted(self, picked))
        elif self.index is not None:
            picked = self.index
            self.post_message(OptionList.Selected(self, picked))
        else:
            return
        if self.on_select is not None:
            self._call(self.on_select, picked)

    # ── yerleşim ve çizim ────────────────────────────────

    def _visible_rows(self) -> int:
        return max(1, min(self.rows, len(self.matches)))

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        if self._longest is None or self._longest[0] != p.ch:
            self._longest = (p.ch, max((p.text.width([(o, Style())]) for o in self.options), default=0))
        lead = p.ch * (6 if self.multi else 2) + p.ch // 2
        return min(width, max(p.ch * 30, self._longest[1] + lead + p.ch * 3)), self._visible_rows() * p.row

    def render(self, p: Painter) -> None:
        th = p.theme
        c = self.content
        if not self.matches:
            p.write(c.x + p.ch // 2, c.y, "eşleşen seçenek yok", color=th.faint)
            return
        rows = self._visible_rows()
        if self.cursor_line < self._top:
            self._top = self.cursor_line
        elif self.cursor_line >= self._top + rows:
            self._top = self.cursor_line - rows + 1
        self._top = max(0, min(self._top, len(self.matches) - rows))
        bar = p.ch if len(self.matches) > rows else 0
        focused = self.has_focus
        for row in range(rows):
            n = self._top + row
            if n >= len(self.matches):
                break
            i, positions = self.matches[n]
            y = c.y + row * p.row
            rect = pygame.Rect(c.x, y, c.w - bar, p.row)
            current = n == self.cursor_line
            fg = None
            if current:
                fg = p.selection(rect, focused=focused)
                if fg is None:  # pointer görünümü: ters renk yerine ❯
                    p.write(c.x + p.ch // 2, y, "❯", Style(bold=True), th.accent if focused else th.dim)
            elif n == self._hover:
                p.hover(rect)
            x = c.x + p.ch * 2 + p.ch // 2
            on = i in self.selected
            if self.multi:
                p.write(x, y, ("\\[✓]" if on else "\\[ ]") if fg else p.check(on), color=fg)
                x += p.ch * 4
            label = _highlight(self.options[i], positions, fg is not None)
            color = fg or (th.text if current or on else th.dim)
            p.write(x, y, p.text.elide(label, rect.right - x - p.ch // 2), color=color)
        p.scrollbar(c.right - 2, c.y, rows * p.row, len(self.matches), rows, self._top, active=focused)

    # ── klavye ve fare ───────────────────────────────────

    def on_key(self, event: Key) -> None:
        key = event.key
        if key in ("up", "down"):
            self.move(-1 if key == "up" else 1)
        elif key in ("pageup", "pagedown"):
            self.move((-1 if key == "pageup" else 1) * self.rows, wrap=False)
        elif key in ("home", "end"):
            self.move(-len(self.matches) if key == "home" else len(self.matches), wrap=False)
        elif key == "enter":
            self.select()
        elif key == "space" and self.multi:
            self.toggle()
        elif key == "ctrl+a" and self.multi:
            self.toggle_all()
        elif key == "backspace" and self.query:
            self.filter(self.query[:-1])
        elif key in ("ctrl+backspace", "escape") and self.query:
            self.filter("")
        else:
            return
        event.stop()

    def on_text_input(self, event: TextInput) -> None:
        text = event.text.strip()  # boşluk süzgece girmez (çoklu kipte işaretler)
        if text and self.accepts_text:
            self.filter(self.query + text)

    def _line_at(self, y: int) -> int | None:
        row = (y - self.content.y) // self.app.painter.row
        n = self._top + row
        return n if 0 <= row < self._visible_rows() and n < len(self.matches) else None

    def on_mouse_move(self, event: MouseMove) -> None:
        n = self._line_at(event.y)
        if n != self._hover:
            self._hover = n
            self.refresh()

    def on_mouse_leave(self) -> None:
        self._hover = None
        self.refresh()

    def on_click(self, event: Click) -> None:
        n = self._line_at(event.y)
        if n is None:
            return
        event.stop()
        before = self.index
        self.cursor_line = n
        self._moved(before)
        if self.multi:
            self.toggle()
        else:
            self.select()

    def on_mouse_scroll(self, event: MouseScroll) -> None:
        event.stop()
        self.move(-event.dy, wrap=False)
