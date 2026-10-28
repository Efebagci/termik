"""Çizim ilkelleri: çerçeveler, butonlar, seçim, çubuklar, gölge.

Görünümün biçimi temadaki belirteçlerle seçilir (köşe, boşluk, başlık ve odak biçimi, buton,
çubuk, seçim, gölge). Aynı bileşen kodu böylece hem "terminal" hem "modern" görünümü çizer.

pygame.draw kenar yumuşatma (anti-aliasing) yapmaz. Yuvarlak köşeler bu yüzden 4 kat büyük
çizilip küçültülen (supersampling) küçük köşe sprite'larıyla basılır; düz kenarlar ise piksele
tam oturan dolgulardır. Sprite'lar (yarıçap, renk, kalınlık) başına bir kez üretilir.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache

import pygame

from .fonts import FontStack
from .text import PLAIN, Markup, Span, Style, Text
from .theme import Color, Theme, mix

SS = 4  # köşe sprite'ları için supersampling katsayısı
RectLike = pygame.Rect | tuple[int, int, int, int]

_BRACKETS = {"bracket": ("[ ", " ]"), "angle": ("< ", " >")}


@lru_cache(maxsize=256)
def _corners(radius: int, color: Color, width: int) -> tuple[pygame.Surface, ...]:
    """Dört köşe sprite'ı (sol üst, sağ üst, sol alt, sağ alt), her biri radius×radius.

    width=0 → dolu çeyrek daire; >0 → o kalınlıkta yay.
    """
    big = pygame.Surface((radius * SS, radius * SS), pygame.SRCALPHA)
    big.fill((*color, 0))  # saydam ama aynı renkte zemin: küçültürken kenarlar kararmasın
    pygame.draw.circle(big, (*color, 255), (radius * SS, radius * SS), radius * SS, width * SS)
    tl = pygame.transform.smoothscale(big, (radius, radius))
    return (tl, pygame.transform.flip(tl, True, False),
            pygame.transform.flip(tl, False, True), pygame.transform.flip(tl, True, True))


@lru_cache(maxsize=64)
def _gradient(w: int, h: int, a: Color, b: Color) -> pygame.Surface:
    line = pygame.Surface((w, 1))
    for i in range(w):
        line.set_at((i, 0), mix(a, b, i / max(1, w - 1)))
    return pygame.transform.scale(line, (w, h))


@lru_cache(maxsize=16)
def _soft_shadow(w: int, h: int, radius: int, blur: int, alpha: int) -> pygame.Surface:
    pad = blur * 2
    img = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
    pygame.draw.rect(img, (0, 0, 0, alpha), (pad, pad, w, h), border_radius=radius)
    blur_fn = getattr(pygame.transform, "gaussian_blur", None)
    return blur_fn(img, blur) if blur_fn else img


class Painter:
    """Bir yüzeye temayla çizim yapan yardımcı.

    Ölçü birimleri `ch` (karakter genişliği) ve `row` (satır yüksekliği). Yerleşim serbest,
    ama boşlukları bu birimlerle vermek CLI ritmini korur.
    """

    def __init__(self, surface: pygame.Surface, theme: Theme, font_paths: list[str | None]):
        self.surface = surface
        self.theme = theme
        fs = theme.font_size
        self.text = Text(FontStack(font_paths, fs), theme)
        self.small = Text(FontStack(font_paths, round(fs * 0.87)), theme)
        self.heading = Text(FontStack(font_paths, round(fs * 1.6)), theme)
        self.ch = self.text.ch
        self.row = round(self.text.height * theme.line_height)

    def set_theme(self, theme: Theme) -> None:
        """Renkleri ve biçim belirteçlerini değiştir. Font boyutu değişiyorsa yeni Painter kur."""
        self.theme = theme
        self.row = round(self.text.height * theme.line_height)
        for t in (self.text, self.small, self.heading):
            t.theme = theme

    @property
    def panel_bg(self) -> Color:
        """Panel içinin zemin rengi: kart görünümünde surface, düz görünümde pencere zemini."""
        return self.theme.surface if self.theme.panel_fill else self.theme.bg

    # ── metin ─────────────────────────────────────────────

    def write(self, x: int, y: int, markup: Markup, style: Style = PLAIN, color: Color | None = None,
              *, font: Text | None = None, right: bool = False) -> int:
        """(x, y) satırın sol üstü; metin satırda dikey ortalanır. right=True ise x sağ kenardır."""
        f = font or self.text
        if right:
            x -= f.width(markup, style)
        return f.draw(self.surface, x, y, markup, style, color, center_in=self.row)

    def gradient_text(self, x: int, y: int, text: str, a: Color, b: Color, *,
                      font: Text | None = None, bold: bool = True) -> int:
        """Soldan sağa renk geçişli tek satır yazı (logo, başlık). (x, y) yazının sol üstü."""
        f = font or self.heading
        img = f.stack.font(0, bold).render(text, True, (255, 255, 255))
        img.blit(_gradient(img.get_width(), img.get_height(), a, b), (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        self.surface.blit(img, (x, y))
        return img.get_width()

    # ── şekiller ──────────────────────────────────────────

    def round_rect(self, rect: RectLike, color: Color, radius: int | None = None) -> None:
        x, y, w, h = rect
        r = min(self.theme.radius if radius is None else radius, w // 2, h // 2)
        s = self.surface
        if r <= 0:
            s.fill(color, (x, y, w, h))
            return
        tl, tr, bl, br = _corners(r, color, 0)
        s.fill(color, (x + r, y, w - 2 * r, h))
        s.fill(color, (x, y + r, r, h - 2 * r))
        s.fill(color, (x + w - r, y + r, r, h - 2 * r))
        s.blit(tl, (x, y))
        s.blit(tr, (x + w - r, y))
        s.blit(bl, (x, y + h - r))
        s.blit(br, (x + w - r, y + h - r))

    def outline(self, rect: RectLike, color: Color, radius: int | None = None, width: int = 1, *,
                top_gaps: list[tuple[int, int]] = (), bottom_gaps: list[tuple[int, int]] = ()) -> None:
        """Çerçeve çizgisi; *_gaps üst/alt kenarda boş bırakılacak x aralıkları."""
        x, y, w, h = rect
        r = min(self.theme.radius if radius is None else radius, w // 2, h // 2)
        s = self.surface
        if r <= 0:  # keskin köşe: dört düz kenar
            self._hline(x, x + w, y, width, color, top_gaps)
            self._hline(x, x + w, y + h - width, width, color, bottom_gaps)
            s.fill(color, (x, y, width, h))
            s.fill(color, (x + w - width, y, width, h))
            return
        r = max(r, width)
        self._hline(x + r, x + w - r, y, width, color, top_gaps)
        self._hline(x + r, x + w - r, y + h - width, width, color, bottom_gaps)
        s.fill(color, (x, y + r, width, h - 2 * r))
        s.fill(color, (x + w - width, y + r, width, h - 2 * r))
        tl, tr, bl, br = _corners(r, color, width)
        s.blit(tl, (x, y))
        s.blit(tr, (x + w - r, y))
        s.blit(bl, (x, y + h - r))
        s.blit(br, (x + w - r, y + h - r))

    def _hline(self, x0: int, x1: int, y: int, t: int, color: Color, gaps) -> None:
        for g0, g1 in sorted(gaps):
            if g0 > x0:
                self.surface.fill(color, (x0, y, min(g0, x1) - x0, t))
            x0 = max(x0, g1)
        if x1 > x0:
            self.surface.fill(color, (x0, y, x1 - x0, t))

    def frame(self, rect: RectLike, title: Markup | None = None, *, focused: bool = False,
              info: Markup | None = None, footer: Markup | None = None, fill: Color | bool = True) -> None:
        """┌─ Başlık ──── bilgi ─┐ biçiminde panel; yazılar çizginin üstüne oturur.

        Başlık biçimi theme.title, odak biçimi theme.focus ile seçilir. info üst kenarın, footer
        alt kenarın sağına yazılır. fill=True panel zeminini temaya göre doldurur (düz görünümde
        doldurmaz); bir renk verilirse her zaman o renkle doldurur (yüzen kutular için).
        """
        th = self.theme
        rect = pygame.Rect(rect)
        if fill is True:
            if th.panel_fill:
                self.round_rect(rect, th.surface)
        elif fill:
            self.round_rect(rect, fill)
        line = th.accent if focused else th.border
        double = focused and th.focus == "double"
        r = min(th.radius, rect.w // 2, rect.h // 2)
        pad, th_h = self.ch // 2, self.text.height
        lead = max(r, pad) + self.ch  # köşe + bir çizgi boyu: "┌─ Başlık"
        top_gaps: list[tuple[int, int]] = []
        bottom_gaps: list[tuple[int, int]] = []
        title_st = Style(bold=True)
        if title:
            tx, tw = rect.x + lead, self.text.width(title, title_st)
            top_gaps.append((tx - pad, tx + tw + pad))
        if info:
            iw = self.text.width(info)
            ix = rect.right - lead - iw
            top_gaps.append((ix - pad, ix + iw + pad))
        if footer:
            fw = self.text.width(footer)
            fx = rect.right - lead - fw
            bottom_gaps.append((fx - pad, fx + fw + pad))
        self.outline(rect, line, r, top_gaps=top_gaps, bottom_gaps=bottom_gaps)
        if double:  # ╔═ eski DOS diyaloglarındaki gibi odakta çift çizgi
            self.outline(rect.inflate(-6, -6), line, max(0, r - 3), top_gaps=top_gaps, bottom_gaps=bottom_gaps)
        mid = rect.y + (1 if double else 0)  # yazıların dikey ortası çizgi(ler)in üstüne gelir
        if title:
            g0, g1 = top_gaps[0]
            if th.title == "inverse":  # ters renkli etiket
                self.surface.fill(th.accent if focused else th.border, (g0, mid - th_h // 2 - 1, g1 - g0, th_h + 2))
                fg = th.bg if focused else th.text
            else:
                fg = th.accent if focused else th.dim
                if th.title == "tab":  # ┤ Başlık ├
                    tick = th_h // 3
                    self.surface.fill(line, (g0, rect.y - tick, 1, tick * 2 + 1))
                    self.surface.fill(line, (g1 - 1, rect.y - tick, 1, tick * 2 + 1))
            self.text.draw(self.surface, tx, mid - th_h // 2, title, title_st, fg)
        if info:
            self.text.draw(self.surface, ix, mid - th_h // 2, info, color=th.dim)
        if footer:
            self.text.draw(self.surface, fx, rect.bottom - 1 - th_h // 2, footer, color=th.dim)

    @property
    def pad(self) -> tuple[int, int]:
        """Panel iç boşluğu piksel olarak: (yanlar, üst/alt) = (pad_x karakter, pad_y satır).

        Üst boşluk, çizginin üstüne oturan başlığın yarısından az olamaz; yoksa ilk satıra biner.
        """
        return (round(self.ch * self.theme.pad_x),
                max(round(self.row * self.theme.pad_y), self.text.height // 2 + 2))

    def inset(self, rect: RectLike) -> pygame.Rect:
        """Çerçevenin içindeki içerik alanı."""
        r = pygame.Rect(rect)
        px, py = self.pad
        return pygame.Rect(r.x + px, r.y + py, r.w - 2 * px, r.h - 2 * py)

    @contextmanager
    def clip(self, rect: RectLike):
        """Bu blokta çizilen hiçbir şey rect dışına taşmaz (iç içe kullanılabilir)."""
        old = self.surface.get_clip()
        self.surface.set_clip(pygame.Rect(rect).clip(old))
        try:
            yield
        finally:
            self.surface.set_clip(old)

    @contextmanager
    def panel(self, rect: RectLike, title: Markup | None = None, **frame_kw):
        """Çerçeveyi çiz, bloğun içeriğini çerçevenin içine kırp."""
        self.frame(rect, title, **frame_kw)
        with self.clip(pygame.Rect(rect).inflate(-2, -2)):
            yield

    def shadow(self, rect: RectLike) -> None:
        """Yüzen kutunun gölgesi (theme.shadow): hard = bir hücre kaydırılmış koyu blok, soft = bulanık."""
        x, y, w, h = rect
        if self.theme.shadow == "hard":
            veil = pygame.Surface((w, h), pygame.SRCALPHA)
            veil.fill((0, 0, 0, 150))
            self.surface.blit(veil, (x + self.ch, y + self.row // 2))
        elif self.theme.shadow == "soft":
            b = self.ch * 3
            self.surface.blit(_soft_shadow(w, h, self.theme.radius, b, 220), (x - b * 2, y - b * 2 + 8))

    def pill(self, rect: RectLike, bg: Color, markup: Markup, fg: Color, *, bold: bool = False,
             font: Text | None = None, radius: int | None = None) -> None:
        """İçinde ortalanmış yazı olan dolu kutu: rozet, dolu buton."""
        x, y, w, h = rect
        self.round_rect(rect, bg, radius)
        f = font or self.text
        st = Style(bold=bold)
        f.draw(self.surface, x + (w - f.width(markup, st)) // 2, y, markup, st, fg, center_in=h)

    def keycap(self, x: int, y: int, label: str, *, right: bool = False) -> int:
        """Klavye tuşu görünümlü küçük etiket ("ctrl+p"); satırda dikey ortalanır. Genişliği döner."""
        f = self.small
        tw = f.width(label)
        w, h = tw + self.ch, f.height + 4
        if right:
            x -= w
        top = y + (self.row - h) // 2
        self.round_rect((x, top, w, h), self.theme.raised, radius=min(self.theme.radius, 4))
        f.draw(self.surface, x + (w - tw) // 2, top, label, color=self.theme.dim, center_in=h)
        return w

    # ── bileşen parçaları ─────────────────────────────────

    def hover(self, rect: RectLike) -> None:
        """Farenin üstünde olduğu satır ya da seçeneğin hafif zemini."""
        self.round_rect(rect, mix(self.panel_bg, self.theme.raised, 0.6), radius=min(self.theme.radius, 4))

    def selection(self, rect: RectLike, *, focused: bool = True) -> Color | None:
        """Seçili satırın zeminini çiz (theme.selection).

        Satır yazısı için kullanılacak rengi döndürür: inverse'te zemine karşıt renk, pointer'da
        None (yazı kendi renklerini korur, işaretçiyi çağıran çizer).
        """
        th = self.theme
        r = min(th.radius, 4)
        if th.selection == "inverse":
            self.round_rect(rect, th.accent if focused else th.border, radius=r)
            return th.bg if focused else th.text
        self.round_rect(rect, th.raised if focused else mix(self.panel_bg, th.raised, 0.55), radius=r)
        return None

    def radio(self, on: bool) -> str:
        """Radyo işareti markup'ı: (•) ( ) ya da ● ○."""
        if self.theme.radio == "paren":
            return "[faint]([/][accent]•[/][faint])[/]" if on else "[faint]( )[/]"
        return "[accent]●[/]" if on else "[faint]○[/]"

    def check(self, on: bool) -> str:
        """Onay kutusu markup'ı: [✓] [ ]."""
        return "[faint]\\[[/][green]✓[/][faint]][/]" if on else "[faint]\\[ ][/]"

    def button_size(self, label: str, primary: bool = False) -> tuple[int, int]:
        th = self.theme
        st = Style(bold=primary)
        if th.button in _BRACKETS:
            a, b = _BRACKETS[th.button]
            return self.text.width(a + label + b, st), self.row
        return self.text.width(label, st) + self.ch * 4, self.row + (6 if th.button == "pill" else 2)

    def button(self, x: int, y: int, label: str, *, primary: bool = False, hot: bool = False) -> pygame.Rect:
        """Buton çiz (theme.button), kapladığı alanı döndür. label düz yazıdır, markup değil.

        Köşeli/açılı butonlarda birincil buton hep ters renktedir (Enter'ın varsayılanı); ikincil
        buton sade yazıdır ve üstüne gelince ters renge döner.
        """
        th = self.theme
        w, h = self.button_size(label, primary)
        rect = pygame.Rect(x, y, w, h)
        if th.button in _BRACKETS:
            a, b = _BRACKETS[th.button]
            if primary or hot:
                bg = (mix(th.accent, th.text, 0.25) if hot else th.accent) if primary else th.text
                self.surface.fill(bg, rect)
                spans: list[Span] = [(a + label + b, Style(bold=primary, fg=th.bg))]
            else:
                spans = [(a, Style(fg=th.faint)), (label, Style(fg=th.text)), (b, Style(fg=th.faint))]
            self.text.draw(self.surface, x, y, spans, center_in=h)
            return rect
        radius = max(th.radius, 6) if th.button == "pill" else th.radius
        if primary:
            bg, fg = (mix(th.accent, th.text, 0.2) if hot else th.accent), th.bg
        else:
            bg, fg = (mix(th.raised, th.border, 0.7) if hot else th.raised), th.text
        self.pill(rect, bg, [(label, Style(bold=primary))], fg, bold=primary, radius=radius)
        return rect

    # ── veri gösterimleri ─────────────────────────────────

    def bar(self, x: int, y: int, w: int, value: float, *, style: str | None = None,
            colors: tuple[Color, Color] | None = None, track: Color | None = None) -> None:
        """Bir satır yüksekliğinde ilerleme çubuğu; (x, y) satırın sol üstü.

        block:   CLI'daki █ dolgu + ░ iz; dolgu piksel hassasiyetinde ve renk geçişli
        segment: ▰▰▰▱▱ bölmeli; son bölme kısmen dolabilir
        line:    rich/pip tarzı ince çizgi
        ascii:   [#####-----]
        """
        th = self.theme
        style = style or th.bar
        a, b = colors or (th.accent, th.accent2)
        value = min(1.0, max(0.0, value))
        if style == "block":
            n = w // self.ch
            w = n * self.ch
            h = self.text.height
            top = y + (self.row - h) // 2
            # ░ glifi fonta göre hücreden taşabiliyor; iz ile dolgu aynı kutuda kalsın
            with self.clip((x, top, w, h)):
                self.text.draw(self.surface, x, top, "░" * n, color=track or th.faint)
            fill = round(w * value)
            if fill:
                self.surface.blit(_gradient(w, h, a, b), (x, top), (0, 0, fill, h))
        elif style == "segment":
            n = max(1, w // self.ch)
            h = round(self.text.height * 0.6)
            top = y + (self.row - h) // 2
            done = value * n
            for i in range(n):
                sx, sw = x + i * self.ch + 1, self.ch - 2
                self.surface.fill(track or th.raised, (sx, top, sw, h))
                part = min(1.0, done - i)
                if part > 0:
                    self.surface.fill(mix(a, b, i / max(1, n - 1)), (sx, top, max(1, round(sw * part)), h))
        elif style == "ascii":
            n = max(3, w // self.ch) - 2
            k = round(value * n)
            # kalın yok: sentetik kalınlık her harfe bir piksel ekleyip eş genişliği bozar
            spans = [("[", Style(fg=th.faint)), ("#" * k, Style(fg=a)),
                     ("-" * (n - k), Style(fg=th.faint)), ("]", Style(fg=th.faint))]
            self.text.draw(self.surface, x, y, spans, center_in=self.row)
        else:  # line
            h = max(2, round(self.row / 7))
            top = y + (self.row - h) // 2
            r = min(th.radius, h // 2)
            self.round_rect((x, top, w, h), track or th.raised, radius=r)
            fill = round(w * value)
            if fill and r:
                self.round_rect((x, top, max(fill, h), h), a, radius=r)
            elif fill:
                self.surface.blit(_gradient(w, h, a, b), (x, top), (0, 0, fill, h))

    def scrollbar(self, x: int, y: int, h: int, total: int, visible: int, start: int, *, active: bool = False) -> None:
        """İnce dikey kaydırma çubuğu: iz ve görünen kısmın yeri. Hepsi görünüyorsa çizilmez."""
        if total <= visible or h <= 0:
            return
        th = self.theme
        self.surface.fill(th.border, (x, y, 2, h))
        thumb = max(self.row // 2, round(h * visible / total))
        top = y + round((h - thumb) * start / max(1, total - visible))
        self.surface.fill(th.accent if active else th.dim, (x, top, 2, thumb))

    def spark(self, x: int, y: int, values: list[float], color: Color, *, height: int | None = None) -> int:
        """Mini grafik: her değer (0..1) bir karakter genişliğinde dikey çubuk; eskiler soluklaşır."""
        h = height or self.text.height
        top = y + (self.row - h) // 2
        n = len(values)
        for i, v in enumerate(values):
            bh = max(1, round(h * min(1.0, max(0.0, v))))
            c = mix(self.panel_bg, color, 0.35 + 0.65 * (i + 1) / n)
            self.surface.fill(c, (x + i * self.ch, top + h - bh, self.ch - 1, bh))
        return n * self.ch
