"""Serbest çizim alanı."""

from __future__ import annotations

import math
from typing import Iterable

import pygame

from ..events import Click, Message, MouseDown, MouseMove
from ..widget import Widget
from .image import load_image

Point = tuple[float, float]


class Canvas(Widget):
    """Serbest çizim alanı: çağrılar saklanır, pencere yeniden çizilince kendiliğinden tekrar çizilir.

        c = ui.Canvas(width=40, height=12)
        c.rect(1, 1, 10, 4, fill="accent")
        c.line(0, 0, 39, 11, color="green")
        c.circle(20, 6, 3, color="yellow")
        c.text(2, 6, "[bold]merhaba[/]")
        c.clear()

    Koordinatlar karakter ve satır birimindedir (x=1 bir karakter, y=1 bir satır; kesirli olabilir)
    ve içerik alanının sol üstünden ölçülür; px=True verilen çağrı piksel kullanır. Renkler tema
    adları ("accent", "green", "dim"), "#ff8800" ya da (r, g, b) olabilir; tema değişince ad verilen
    renkler de değişir. Her çağrı bir numara döndürür; remove(numara) o çizimi siler.

    Fareyle tıklama Canvas.Clicked, basılıyken sürükleme Canvas.Dragged iletir; ikisi de konumu
    aynı birimlerle (x, y) taşır.
    """

    default_height = 10

    class Clicked(Message):
        def __init__(self, canvas: Canvas, x: float, y: float, button: int) -> None:
            super().__init__()
            self.canvas, self.x, self.y, self.button = canvas, x, y, button

    class Dragged(Message):
        def __init__(self, canvas: Canvas, x: float, y: float) -> None:
            super().__init__()
            self.canvas, self.x, self.y = canvas, x, y

    def __init__(self, *, background: str | tuple | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.background = background  # None: kabın zemini
        self._ops: dict[int, tuple] = {}
        self._next = 1
        self._dragging = False

    def __len__(self) -> int:
        return len(self._ops)

    # ── çizim çağrıları ──────────────────────────────────

    def _add(self, *op) -> int:
        handle = self._next
        self._next += 1
        self._ops[handle] = op
        self.refresh()
        return handle

    def line(self, x1: float, y1: float, x2: float, y2: float, *, color="text", width: int = 1,
             px: bool = False) -> int:
        """Çizgi; width piksel kalınlığıdır (1 ise kenarları yumuşatılır)."""
        return self._add("line", px, color, [(x1, y1), (x2, y2)], width)

    def lines(self, points: Iterable[Point], *, color="text", width: int = 1, closed: bool = False,
              px: bool = False) -> int:
        """Noktaları sırayla birleştiren kırık çizgi (grafikler için)."""
        return self._add("lines", px, color, list(points), width, closed)

    def rect(self, x: float, y: float, w: float, h: float, *, color=None, fill=None, width: int = 1,
             radius: int = 0, px: bool = False) -> int:
        """Dikdörtgen: fill içini doldurur, color çerçevesini çizer (ikisi de yoksa color="text")."""
        if color is None and fill is None:
            color = "text"
        return self._add("rect", px, color, [(x, y), (x + w, y + h)], fill, width, radius)

    def circle(self, x: float, y: float, r: float, *, color=None, fill=None, width: int = 1,
               px: bool = False) -> int:
        """Daire: merkezi (x, y), yarıçapı r karakter genişliği (px=True ise piksel)."""
        if color is None and fill is None:
            color = "text"
        return self._add("circle", px, color, [(x, y)], fill, width, r)

    def arc(self, x: float, y: float, r: float, start: float, end: float, *, color="text", width: int = 1,
            px: bool = False) -> int:
        """Yay: merkezi (x, y), yarıçapı r (karakter genişliği); açılar derece, 0 sağda, saat yönünün
        tersine artar (90 yukarı). width piksel kalınlığıdır: kalın yaylar dolu halka dilimi olarak
        çizilir (göstergeler, halka grafikler).

            c.arc(4, 2, 2.5, 0, 360, color="raised", width=6)        # zemin halkası
            c.arc(4, 2, 2.5, 90 - 360 * 0.62, 90, color="accent", width=6)  # %62, tepeden saat yönüne
        """
        return self._add("arc", px, color, [(x, y)], r, start, end, width)

    def polygon(self, points: Iterable[Point], *, color=None, fill=None, width: int = 1, px: bool = False) -> int:
        if color is None and fill is None:
            color = "text"
        return self._add("polygon", px, color, list(points), fill, width)

    def text(self, x: float, y: float, markup: str, *, color=None, px: bool = False) -> int:
        """Markup yazı; (x, y) satırın sol üstü."""
        return self._add("text", px, color, [(x, y)], markup)

    def image(self, x: float, y: float, source, *, w: float | None = None, h: float | None = None,
              px: bool = False) -> int:
        """Resim (dosya yolu ya da Surface); w ve h verilirse o boyuta ölçeklenir."""
        return self._add("image", px, None, [(x, y)], load_image(source), w, h)

    def remove(self, handle: int) -> None:
        if self._ops.pop(handle, None) is not None:
            self.refresh()

    def clear(self) -> None:
        self._ops.clear()
        self.refresh()

    # ── birimler ─────────────────────────────────────────

    @property
    def size(self) -> tuple[float, float]:
        """Çizim alanının boyutu karakter ve satır biriminde (yerleşimden sonra)."""
        p = self.app.painter
        return self.content.w / p.ch, self.content.h / p.row

    def to_units(self, pos: tuple[int, int]) -> tuple[float, float]:
        """Pencere pikseli → bu alandaki (x, y) birimi."""
        p = self.app.painter
        return (pos[0] - self.content.x) / p.ch, (pos[1] - self.content.y) / p.row

    def _xy(self, p, point: Point, px: bool) -> tuple[int, int]:
        c = self.content
        x, y = point
        return (round(c.x + x), round(c.y + y)) if px else (round(c.x + x * p.ch), round(c.y + y * p.row))

    @staticmethod
    def _color(p, value):
        if value is None:
            return None
        if isinstance(value, str):
            return p.theme.color(value) or p.theme.text
        return tuple(value)

    # ── çizim ─────────────────────────────────────────────

    def render(self, p) -> None:
        c = self.content
        if self.background is not None:
            p.surface.fill(self._color(p, self.background), c)
        with p.clip(c):
            for op in list(self._ops.values()):
                self._draw(p, op)

    def _draw(self, p, op: tuple) -> None:
        kind, px, color, points = op[:4]
        s = p.surface
        color = self._color(p, color)
        pts = [self._xy(p, pt, px) for pt in points]
        if kind in ("line", "lines"):
            width = op[4]
            closed = op[5] if kind == "lines" else False
            if len(pts) < 2:
                return
            if width <= 1:
                pygame.draw.aalines(s, color, closed, pts)
            else:
                pygame.draw.lines(s, color, closed, pts, width)
        elif kind == "rect":
            fill, width, radius = op[4:7]
            (x1, y1), (x2, y2) = pts
            rect = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
            if fill is not None:
                pygame.draw.rect(s, self._color(p, fill), rect, border_radius=radius)
            if color is not None:
                pygame.draw.rect(s, color, rect, width, border_radius=radius)
        elif kind == "circle":
            fill, width, r = op[4:7]
            radius = max(1, round(r if px else r * p.ch))
            if fill is not None:
                pygame.draw.circle(s, self._color(p, fill), pts[0], radius)
            if color is not None:
                aa = getattr(pygame.draw, "aacircle", None)
                if width <= 1 and aa is not None:
                    aa(s, color, pts[0], radius, 1)
                else:
                    pygame.draw.circle(s, color, pts[0], radius, width)
        elif kind == "arc":
            r, start, end, width = op[4:8]
            radius = r if px else r * p.ch
            if end < start:
                start, end = end, start
            steps = max(2, int((end - start) / 3) + 1)
            angles = [math.radians(start + (end - start) * i / steps) for i in range(steps + 1)]
            cx, cy = pts[0]
            ring = [(cx + radius * math.cos(a), cy - radius * math.sin(a)) for a in angles]
            if width <= 1:
                pygame.draw.aalines(s, color, False, ring)
            else:
                inner = radius - width
                ring += [(cx + inner * math.cos(a), cy - inner * math.sin(a)) for a in reversed(angles)]
                pygame.draw.polygon(s, color, ring)
                pygame.draw.aalines(s, color, True, ring)
        elif kind == "polygon":
            fill, width = op[4:6]
            if len(pts) < 3:
                return
            if fill is not None:
                pygame.draw.polygon(s, self._color(p, fill), pts)
            if color is not None:
                pygame.draw.aalines(s, color, True, pts) if width <= 1 else pygame.draw.polygon(s, color, pts, width)
        elif kind == "text":
            p.text.draw(s, pts[0][0], pts[0][1], op[4], color=color or p.theme.text)
        elif kind == "image":
            image, w, h = op[4:7]
            if w is not None and h is not None:
                size = (max(1, round(w if px else w * p.ch)), max(1, round(h if px else h * p.row)))
                if size != image.get_size():
                    image = pygame.transform.smoothscale(image, size)
            s.blit(image, pts[0])

    # ── fare ──────────────────────────────────────────────

    def on_mouse_down(self, event: MouseDown) -> None:
        self._dragging = event.button == 1

    def on_click(self, event: Click) -> None:
        x, y = self.to_units(event.pos)
        self.post_message(Canvas.Clicked(self, x, y, event.button))

    def on_mouse_move(self, event: MouseMove) -> None:
        if event.button and self._dragging:
            x, y = self.to_units(event.pos)
            self.post_message(Canvas.Dragged(self, x, y))
