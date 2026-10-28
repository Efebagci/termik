"""Metin ölçme, satır kaydırma ve çizim. Markup sözdizimi ve ayrıştırıcısı markup.py'de."""

from __future__ import annotations

import re
from collections import OrderedDict

import pygame

from .fonts import FontStack
# eski içe aktarmalar (from .text import Style, escape…) çalışmayı sürdürsün
from .markup import PLAIN, Markup, Span, Style, escape, parse_markup, parse_style, plain_text  # noqa: F401
from .theme import Color, Theme, mix


class Text:
    """Tek boyuttaki metni ölçer ve çizer; render edilen parçaları LRU önbellekte tutar."""

    def __init__(self, stack: FontStack, theme: Theme, cache_size: int = 4096):
        self.stack = stack
        self.theme = theme
        self._cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self._cache_size = cache_size

    @property
    def ch(self) -> int:
        return self.stack.ch

    @property
    def height(self) -> int:
        return self.stack.height

    def spans(self, markup: Markup, style: Style = PLAIN) -> list[Span]:
        if isinstance(markup, str):
            return parse_markup(markup, self.theme, style)
        return markup

    def _render(self, i: int, text: str, color: Color, bold: bool, italic: bool) -> pygame.Surface:
        key = (i, text, color, bold, italic)
        img = self._cache.get(key)
        if img is None:
            img = self.stack.font(i, bold, italic).render(text, True, color)
            self._cache[key] = img
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(key)
        return img

    def width(self, markup: Markup, style: Style = PLAIN) -> int:
        return sum(self.stack.width(text, st.bold, st.italic) for text, st in self.spans(markup, style))

    def wrap(self, markup: Markup, width: int, style: Style = PLAIN) -> list[list[Span]]:
        """Metni genişliğe sığan satırlara böl. "\\n" yeni satır açar; kelimeler bölünmez,
        tek başına sığmayan kelime harf harf bölünür, kaydırılan satırın başındaki boşluk atılır."""
        lines: list[list[Span]] = [[]]
        used = 0
        soft = False  # son satır kaydırmayla mı açıldı

        def add(piece: str, st: Style, w: int) -> None:
            nonlocal used
            line = lines[-1]
            if line and line[-1][1] == st:
                line[-1] = (line[-1][0] + piece, st)
            else:
                line.append((piece, st))
            used += w

        def newline(wrapped: bool) -> None:
            nonlocal used, soft
            if wrapped:  # kaydırılan satırın sonundaki boşluk atılır; genişliği şişirmesin
                line = lines[-1]
                while line and not line[-1][0].strip():
                    line.pop()
                if line:
                    line[-1] = (line[-1][0].rstrip(" "), line[-1][1])
            lines.append([])
            used, soft = 0, wrapped

        for text, st in self.spans(markup, style):
            for k, part in enumerate(text.split("\n")):
                if k:
                    newline(False)
                for token in re.findall(r" +|[^ ]+", part):
                    w = self.width([(token, st)])
                    if token[0] == " ":
                        if used == 0 and soft:
                            continue
                        if used + w <= width:
                            add(token, st, w)
                        else:
                            newline(True)  # satır sonuna düşen boşluk yutulur
                        continue
                    if used and used + w > width:
                        newline(True)
                    if w <= width:
                        add(token, st, w)
                        continue
                    for ch in token:
                        cw = self.width([(ch, st)])
                        if used and used + cw > width:
                            newline(True)
                        add(ch, st, cw)
        return lines

    def elide(self, markup: Markup, max_w: int, style: Style = PLAIN) -> list[Span]:
        """Sığmayan metni sondan kırpıp '…' ekle."""
        spans = self.spans(markup, style)
        if self.width(spans) <= max_w:
            return spans
        room = max_w - self.width("…")
        out: list[Span] = []
        used = 0
        for text, st in spans:
            w = self.width([(text, st)])
            if used + w <= room:
                out.append((text, st))
                used += w
                continue
            kept = ""
            for ch in text:
                cw = self.width([(ch, st)])
                if used + cw > room:
                    break
                kept += ch
                used += cw
            out.append((kept + "…", st))
            break
        return out

    def draw(self, surface: pygame.Surface, x: int, y: int, markup: Markup, style: Style = PLAIN,
             color: Color | None = None, *, center_in: int | None = None, baseline: int | None = None) -> int:
        """Metni çiz, genişliğini döndür.

        (x, y) metnin sol üstü. center_in verilirse metin o yükseklikteki bir satırda dikey
        ortalanır; baseline verilirse y yok sayılır ve metin o taban çizgisine oturtulur.
        """
        if baseline is None:
            top = y + (center_in - self.stack.height) // 2 if center_in else y
            baseline = top + self.stack.ascent
        top = baseline - self.stack.ascent
        x0 = x
        for text, st in self.spans(markup, style):
            fg = st.fg or color or self.theme.text
            if st.dim:
                fg = mix(fg, self.theme.bg, 0.45)
            span_x = x
            for i, run in self.stack.runs(text):
                img = self._render(i, run, fg, st.bold, st.italic)
                if st.bg:
                    surface.fill(st.bg, (x, top, img.get_width(), self.stack.height))
                surface.blit(img, (x, baseline - self.stack.font(i, st.bold, st.italic).get_ascent()))
                x += img.get_width()
            if st.underline:
                surface.fill(fg, (span_x, baseline + 2, x - span_x, 1))
            if st.strike:
                surface.fill(fg, (span_x, baseline - self.stack.ascent // 3, x - span_x, 1))
        return x - x0
