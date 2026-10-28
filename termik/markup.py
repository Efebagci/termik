"""Markup ayrıştırma; pygame'e bağlı değil (terminal kipi de kullanır).

Markup, rich'in sözdiziminin bir alt kümesi:

    "[bold green]✓[/] Bitti"     "[dim]soluk[/dim]"     "[u]altı çizili[/u]"
    "[#ff8800 on #1a2232]rozet[/]"     "[accent]tema rengi[/]"

Bilinmeyen etiketler ("[1/3]", "[/usr/bin]" gibi) olduğu gibi yazılır. Köşeli parantezi
zorla yazdırmak için "\\[" kullanılır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .theme import THEMES, Color, Theme

_ANY_THEME = next(iter(THEMES.values()))  # renkleri önemsiz işler için (düz yazı çıkarmak gibi)


@dataclass(frozen=True)
class Style:
    fg: Color | None = None
    bg: Color | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    dim: bool = False

    def __add__(self, other: Style) -> Style:
        """İç içe etiketler: içteki renk dıştakini ezer, bayraklar birikir."""
        return Style(
            fg=other.fg or self.fg, bg=other.bg or self.bg,
            bold=self.bold or other.bold, italic=self.italic or other.italic,
            underline=self.underline or other.underline, strike=self.strike or other.strike,
            dim=self.dim or other.dim,
        )


PLAIN = Style()
Span = tuple[str, Style]
Markup = str | list[Span]

_TAG = re.compile(r"\\\[|\[(/?)([^\[\]\n]*)\]")
_FLAGS = {
    "bold": "bold", "b": "bold", "italic": "italic", "i": "italic",
    "underline": "underline", "u": "underline", "strike": "strike", "s": "strike",
    "dim": "dim", "d": "dim",
}


def parse_style(spec: str, theme: Theme) -> Style | None:
    """'bold red on #222' → Style. Tanınmayan bir kelime varsa None (etiket düz yazı sayılır)."""
    words = spec.lower().split()
    if not words:
        return None
    fields: dict = {}
    i = 0
    while i < len(words):
        w = words[i]
        if w == "on" and i + 1 < len(words):
            bg = theme.color(words[i + 1])
            if bg is None:
                return None
            fields["bg"] = bg
            i += 2
            continue
        if w in _FLAGS:
            fields[_FLAGS[w]] = True
        else:
            fg = theme.color(w)
            if fg is None:
                return None
            fields["fg"] = fg
        i += 1
    return Style(**fields)


def escape(text: str) -> str:
    """Dışarıdan gelen yazı markup sanılmasın: '[' → '\\['. Kullanıcı girdisini gösterirken kullanın."""
    return text.replace("[", "\\[")


def plain_text(markup: str) -> str:
    """Markup'ı soyup düz yazıyı döndür (sıralama ve arama için)."""
    return "".join(text for text, _ in parse_markup(markup, _ANY_THEME))


def parse_markup(text: str, theme: Theme, base: Style = PLAIN) -> list[Span]:
    if "[" not in text:
        return [(text, base)] if text else []
    stack = [base]
    spans: list[Span] = []

    def emit(s: str) -> None:
        if not s:
            return
        if spans and spans[-1][1] == stack[-1]:
            spans[-1] = (spans[-1][0] + s, stack[-1])
        else:
            spans.append((s, stack[-1]))

    pos = 0
    for m in _TAG.finditer(text):
        emit(text[pos:m.start()])
        pos = m.end()
        if m.group(0) == "\\[":
            emit("[")
            continue
        closing, spec = m.group(1), m.group(2).strip()
        if closing:
            # [/] ya da [/bold]: son açılan etiketi kapat. [/usr/bin] gibi şeyler düz yazıdır.
            if spec and parse_style(spec, theme) is None:
                emit(m.group(0))
            elif len(stack) > 1:
                stack.pop()
            continue
        style = parse_style(spec, theme)
        if style is None:
            emit(m.group(0))
        else:
            stack.append(stack[-1] + style)
    emit(text[pos:])
    return spans
