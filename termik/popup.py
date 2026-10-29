"""Yüzen kutular: açılır liste ve menüler.

Bir bileşenin altına (yer yoksa üstüne) ya da bir noktaya yerleşir. Diyalogların aksine arka planı
karartmaz, ama bütün girdiyi alır: dışarı basılınca ya da Esc ile kapanır ve o tık alttaki bileşene
geçmez. Kapanınca odak açılmadan önceki yerine döner.
"""

from __future__ import annotations

from typing import Iterable

import pygame

from .draw import Painter
from .events import MouseDown
from .theme import mix
from .widget import Screen, Widget, action


class PopupBox(Widget):
    """Yüzen kutunun gövdesi: dolu zemin, ince vurgu çerçevesi; içindekileri alt alta dizer."""

    def __init__(self, *children: Widget, **kwargs) -> None:
        super().__init__(*children, padding=(0.25, 0.5), **kwargs)

    def chrome(self, p: Painter) -> tuple[int, int, int, int]:
        t, r, b, l = super().chrome(p)
        return t + 1, r + 1, b + 1, l + 1  # çerçeve çizgisi

    def render(self, p: Painter) -> None:
        th = p.theme
        p.round_rect(self.region, mix(th.bg, th.raised, 0.45))
        p.outline(self.region, th.accent)


class Popup(Screen):
    """Bir dikdörtgene (bileşenin yeri) ya da noktaya bağlı yüzen kutu. Alt sınıflar compose_body()
    ile içeriği verir; dismiss(sonuç) ile kapanır."""

    modal = True
    veil = False

    def __init__(self, anchor: pygame.Rect | tuple, *, min_width: int = 0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.anchor = pygame.Rect(anchor) if len(anchor) == 4 else pygame.Rect(anchor[0], anchor[1], 0, 0)
        self.min_width = min_width
        self.box: PopupBox | None = None

    def compose_body(self) -> Iterable[Widget]:
        return ()

    def compose(self) -> Iterable[Widget]:
        self.box = PopupBox(*self.compose_body())
        yield self.box

    def arrange(self, p: Painter) -> None:
        r = self.region
        room = r.w - p.ch * 2
        width = min(room, max(self.min_width, self.box.natural_size(p, room)[0]))
        height = min(r.h - p.row, self.box.natural_size(p, width)[1])
        a = self.anchor
        x = max(r.x + p.ch // 2, min(a.x, r.right - width - p.ch // 2))
        y = a.bottom + 2
        if y + height > r.bottom and a.y - height - 2 >= r.y:  # altta yer yoksa üste aç
            y = a.y - height - 2
        y = max(r.y, min(y, r.bottom - height))
        self.box._layout(p, pygame.Rect(x, y, width, height))

    def render(self, p: Painter) -> None:
        p.shadow(self.box.region)

    def on_mouse_down(self, event: MouseDown) -> None:
        if not self.box.region.collidepoint(event.pos):
            event.stop()
            self.outside(event)

    def outside(self, event: MouseDown) -> None:
        """Kutunun dışına basıldı; varsayılan: kapan."""
        self.dismiss(None)

    @action("Kapat", key="escape", show=False, palette=False)
    def close(self) -> None:
        self.dismiss(None)
