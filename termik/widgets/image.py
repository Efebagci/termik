"""Resim."""

from __future__ import annotations

import os

import pygame

from ..draw import Painter
from ..markup import escape
from ..widget import Widget

FITS = ("contain", "cover", "stretch", "none")
ImageSource = str | os.PathLike | pygame.Surface  # resim dosyası yolu ya da hazır Surface


def load_image(source: ImageSource) -> pygame.Surface:
    """Dosya yolu ya da Surface → ölçeklenebilir (24/32 bit) Surface."""
    image = source if isinstance(source, pygame.Surface) else pygame.image.load(os.fspath(source))
    if image.get_bitsize() not in (24, 32):  # smoothscale 24/32 bit ister (paletli PNG, GIF)
        out = pygame.Surface(image.get_size(), pygame.SRCALPHA)
        out.blit(image, (0, 0))
        image = out
    return image


class Image(Widget):
    """Resim: dosya yolu ya da pygame.Surface.

        ui.Image("foto.png", height=12, caption="foto.png · 1920×1080")

    Kutuya oranı korunarak sığar (fit="contain"); "cover" kırparak doldurur, "stretch" esnetir,
    "none" asıl boyutunda ortalar. Boyut verilmezse doğal boyutu kadar yer kaplar (kabın genişliğini
    aşmaz, yükseklik orana göre). frame=False çerçeveyi kaldırır; caption altına soluk yazı ekler,
    placeholder resim yokken yazılır.
    image.source = "başka.png" resmi değiştirir.

    Görünüşü temadaki image belirtecinden gelir: smooth yumuşak ölçek, pixel karakter ızgarasına
    oturan iri pikseller, blocks terminal resim gösterenleri gibi hücre başına üst üste iki piksel
    (▀). Açılamayan resim uygulamayı düşürmez; yerinde hatayı yazar.
    """

    default_width = "auto"
    default_height = "auto"

    def __init__(self, source: ImageSource | None = None, *, fit: str = "contain", caption: str | None = None, frame: bool = True,
                 placeholder: str = "resim yok", **kwargs) -> None:
        if fit not in FITS:
            raise ValueError(f"Image: fit {', '.join(FITS)} olabilir, {fit!r} geldi")
        super().__init__(**kwargs)
        self.fit, self.caption, self.frame, self.placeholder = fit, caption, frame, placeholder
        self._image: pygame.Surface | None = None
        self._error: str | None = None
        self._cache: tuple[tuple, pygame.Surface] | None = None
        self.source = source

    @property
    def source(self) -> ImageSource | None:
        return self._source

    @source.setter
    def source(self, value: ImageSource | None) -> None:
        self._source = value
        self._image, self._error, self._cache = None, None, None
        if value is not None:
            try:
                self._image = load_image(value)
            except (pygame.error, OSError) as exc:
                self._error = f"açılamadı: {exc.strerror or exc}" if isinstance(exc, OSError) else str(exc)
        self.refresh(layout=True)

    @property
    def image(self) -> pygame.Surface | None:
        """Yüklenen resim (yoksa ya da açılamadıysa None)."""
        return self._image

    # ── yerleşim ─────────────────────────────────────────

    def _scale(self) -> float:
        return self._app._scale if self._app is not None else 1.0

    def chrome(self, p: Painter) -> tuple[int, int, int, int]:
        t, r, b, l = super().chrome(p)
        f = 1 if self.frame else 0
        return t + f, r + f, b + f + (p.row if self.caption else 0), l + f

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        if self._image is None:
            return min(width, p.ch * 24), p.row * 3
        k = self._scale()
        w, h = self._image.get_width() * k, self._image.get_height() * k
        if w > width > 0:
            w, h = width, h * width / w
        return round(w), max(1, round(h))

    def _box(self, area: pygame.Rect) -> pygame.Rect:
        """Resmin çizileceği dikdörtgen (fit'e göre; cover'da alandan taşar, kırpılır)."""
        iw, ih = self._image.get_size()
        if self.fit == "stretch":
            w, h = area.size
        elif self.fit == "none":
            k = self._scale()
            w, h = iw * k, ih * k
        else:
            pick = min if self.fit == "contain" else max
            k = pick(area.w / iw, area.h / ih)
            w, h = iw * k, ih * k
        w, h = max(1, round(w)), max(1, round(h))
        return pygame.Rect(area.x + (area.w - w) // 2, area.y + (area.h - h) // 2, w, h)

    # ── çizim ─────────────────────────────────────────────

    def _scaled(self, p, size: tuple[int, int]) -> pygame.Surface:
        style = p.theme.image
        key = (id(self._image), size, style, p.ch, p.row)
        if self._cache is not None and self._cache[0] == key:
            return self._cache[1]
        img, (w, h) = self._image, size
        if style == "pixel":  # iri kare pikseller: önce küçült (ortalama), sonra en yakın komşuyla büyüt
            s = max(2, p.ch // 2)
            cols, rows = max(1, w // s), max(1, h // s)
            out = pygame.transform.scale(pygame.transform.smoothscale(img, (cols, rows)), (cols * s, rows * s))
        elif style == "blocks":  # hücre başına üst üste iki piksel: terminaldeki ▀ resimler gibi
            cols, rows = max(1, w // p.ch), max(1, h // p.row)
            small = pygame.transform.smoothscale(img, (cols, rows * 2))
            out = pygame.Surface((cols * p.ch, rows * p.row), pygame.SRCALPHA)
            top = p.row // 2
            for y in range(rows):
                for x in range(cols):
                    out.fill(small.get_at((x, y * 2)), (x * p.ch, y * p.row, p.ch, top))
                    out.fill(small.get_at((x, y * 2 + 1)), (x * p.ch, y * p.row + top, p.ch, p.row - top))
        elif (w, h) == img.get_size():
            out = img
        else:
            out = pygame.transform.smoothscale(img, (w, h))
        self._cache = (key, out)
        return out

    def render(self, p: Painter) -> None:
        th = p.theme
        c = self.content
        if self.frame:
            p.outline(c.inflate(2, 2), th.border)
        if self.caption:
            f = 1 if self.frame else 0
            p.write(c.x, c.bottom + f, p.text.elide(f"[dim]{self.caption}[/]", c.w), color=th.dim)
        if c.w <= 0 or c.h <= 0:
            return
        if self._image is None:
            msg = f"[red]✗[/] [dim]{escape(self._error)}[/]" if self._error else f"[faint]{self.placeholder}[/]"
            p.write(c.x + p.ch, c.y + (c.h - p.row) // 2, p.text.elide(msg, c.w - p.ch * 2))
            return
        box = self._box(c)
        image = self._scaled(p, box.size)
        at = (box.x + (box.w - image.get_width()) // 2, box.y + (box.h - image.get_height()) // 2)
        with p.clip(c):
            p.surface.blit(image, at)
