"""Başlıklı çerçeve."""

from __future__ import annotations

import pygame

from ..reactive import reactive
from ..theme import mix
from ..widget import Widget


class Panel(Widget):
    """Başlıklı çerçeve; içindekileri alt alta dizer. İçinde odak varsa çerçevesi yanar.

        Panel(Log(), title="Günlük", info="12 kayıt", footer="2/11")

    Başlık ve alt yazı çizginin üstüne oturur; çerçevenin biçimi temadan (title, focus) gelir.
    İç boşluk temanın yoğunluğundan gelir, padding= bunun üstüne eklenir. floating=True yüzen
    kutular (palet, diyalog) içindir: zemin her zaman doludur, alttaki görünmez.
    """

    title = reactive(None)
    info = reactive(None)
    footer = reactive(None, layout=True)

    def __init__(self, *children: Widget, title: str | None = None, info: str | None = None,
                 footer: str | None = None, floating: bool = False, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self.title, self.info, self.footer = title, info, footer
        self.floating = floating
        self.frame = pygame.Rect(0, 0, 0, 0)

    def _half(self, p) -> int:
        """Çizginin üstüne oturan yazının yarı yüksekliği: çerçeve bu kadar içeriden başlar."""
        return p.text.height // 2 + 1

    def chrome(self, p) -> tuple[int, int, int, int]:
        px, py = p.pad
        t, r, b, l = super().chrome(p)
        half = self._half(p)
        return t + half + py, r + px, b + py + (half if self.footer else 0), l + px

    def _layout(self, p, region: pygame.Rect) -> None:
        half = self._half(p)
        bottom = half if self.footer else 0
        self.frame = pygame.Rect(region.x, region.y + half, region.w, max(0, region.h - half - bottom))
        super()._layout(p, region)

    def child_clip(self) -> pygame.Rect:
        return self.frame.inflate(-2, -2)

    def render(self, p) -> None:
        fill = mix(p.theme.bg, p.theme.raised, 0.45) if self.floating else True
        p.frame(self.frame, self.title, focused=self.focus_within, info=self.info, footer=self.footer, fill=fill)
