"""Tema: renk paleti ve ölçüler.

Renkler opak RGB olarak tutulur. Yarı saydam görünen her şey (seçili satır, hover zemini,
soluk yazı) zemine `mix()` ile karıştırılmış opak bir renktir: pygame'de alfa karıştırma hem
pahalı hem de yüzey tipine bağlı, opak renk ise her yerde aynı davranır.
"""

from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass, replace

Color = tuple[int, int, int]


def hex_color(value: str) -> Color:
    """'#38bdf8' ya da '38bdf8' → (56, 189, 248)."""
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise ValueError(f"geçersiz renk: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def mix(a: Color, b: Color, t: float) -> Color:
    """a'dan b'ye t oranında karıştır: 0 → a, 1 → b."""
    return (round(a[0] + (b[0] - a[0]) * t),
            round(a[1] + (b[1] - a[1]) * t),
            round(a[2] + (b[2] - a[2]) * t))


_COLOR_FIELDS = frozenset({
    "bg", "surface", "raised", "border", "text", "dim", "faint",
    "accent", "accent2", "accent3", "red", "green", "yellow", "blue", "magenta", "cyan",
})

# Paletin sıra adları: color="secondary", color="ikincil", color=2 aynı rengi verir
SLOT_NAMES = ("primary", "secondary", "tertiary", "quaternary", "quinary", "senary")
_SLOT_TR = ("birincil", "ikincil", "üçüncül", "dördüncül", "beşincil", "altıncıl")

# Markup'ta rich/ANSI alışkanlığıyla yazılabilecek eş anlamlılar
_ALIASES = {
    "white": "text", "black": "bg", "gray": "dim", "grey": "dim",
    "purple": "magenta",
    "ok": "green", "warn": "yellow", "err": "red", "error": "red", "info": "blue",
}


@dataclass(frozen=True)
class Theme:
    name: str
    # zeminler: pencere → panel → yükseltilmiş (buton, seçili satır, rozet)
    bg: Color
    surface: Color
    raised: Color
    # çizgi ve yazı tonları
    border: Color
    text: Color
    dim: Color      # ikincil yazı
    faint: Color    # ipucu, placeholder, zaman damgası
    # vurgular ve durum renkleri
    accent: Color   # birincil renk
    accent2: Color  # ikincil
    accent3: Color  # üçüncül
    red: Color
    green: Color
    yellow: Color
    blue: Color
    magenta: Color
    cyan: Color
    extra: tuple[Color, ...] = ()  # dördüncül ve sonraki renkler (make_theme(colors=[…]) ile)
    # ölçüler (ölçek 1.0'da piksel)
    font_size: int = 15
    line_height: float = 1.15   # fontun doğal satır yüksekliğinin katı (terminallerdeki gibi)
    radius: int = 0             # köşe yarıçapı; 0 = keskin ┌┐
    # biçim belirteçleri: varsayılanlar "terminal" görünümü + "rahat" yoğunluk
    pad_x: float = 1.75         # panel iç boşluğu, karakter cinsinden
    pad_y: float = 0.65         # panel iç boşluğu ve gruplar arası, satır cinsinden
    panel_fill: bool = False    # paneller zeminden ayrı renkte mi (kart görünümü)
    title: str = "inverse"      # inverse ters renkli etiket · inline ┌─ Başlık ─┐ · tab ┤ Başlık ├
    frame: str = "faint"        # panel çerçevesi: line çizgi · faint soluk çizgi · corners yalnızca köşeler · none çizgisiz
    focus: str = "title"        # içinde odak olan panel: color çerçeve vurgu renginde · double çift çizgi · title yalnızca başlık · bar solda ince çubuk · none işaret yok
    button: str = "solid"       # bracket [ Tamam ] · tinted zeminli [ Tamam ] · angle < Tamam > · solid dolu blok · boxed çerçeveli kutu · pill hap
    bar: str = "block"          # block █▊░ · segment ▰▱ · line ━━─ · ascii [##--]
    selection: str = "inverse"  # inverse: tam satır ters renk · pointer: ❯ + hafif zemin
    shadow: str = "hard"        # hard: kaydırılmış koyu blok · soft: bulanık · none
    toggle: str = "drawn"       # drawn çizilmiş kutucuk ve yuvarlak düğme · text [✓] ve radio belirteci
    radio: str = "paren"        # toggle = "text" iken: paren (•) ( ) · dot ● ○
    tabs: str = "inverse"       # inverse ters renkli · folder klasör sekmesi · underline alt çizgi · bracket [ Genel ]
    slider: str = "bar"         # bar ilerleme çubuğu gibi · line ince iz ve yuvarlak tutamak · value ◂ 60 ▸
    field: str = "boxed"        # Input, Select, Spinbox kutusu: boxed ince çerçeve · filled dolu zemin · underline alt çizgi · plain kutusuz
    select: str = "bracket"     # field = "plain" iken: bracket [ Artımlı ▾ ] · arrows ◂ Artımlı ▸ · underline altı çizili
    image: str = "smooth"       # smooth yumuşak ölçek · pixel iri pikseller · blocks terminal gibi ▀ yarım bloklar
    spin: str = "bracket"       # field = "plain" iken: bracket [ − 12 + ] · arrows ◂ 12 ▸ · stacked sağda ▴▾
    split: str = "line"         # line ince çizgi ve ⋮ tutamak · bar dolu sütun · hidden yalnızca fare gelince
    form_label: str = "left"    # left etiketler solda hizalı · top alanın üstünde
    chart: str = "smooth"       # smooth yumuşak çizgiler · braille ⣀⡠ noktaları · blocks ▁▃▇ blokları

    @property
    def palette(self) -> tuple[Color, ...]:
        """Temanın renkleri sırayla: birincil, ikincil, üçüncül, (dördüncül…)."""
        return (self.accent, self.accent2, self.accent3, *self.extra)

    def slot(self, n: int) -> Color:
        """n'inci renk (1 birincil); palette yetmezse baştan döner."""
        palette = self.palette
        return palette[(n - 1) % len(palette)]

    def color(self, name: str) -> Color | None:
        """Renk adını çöz: 'green', 'accent', 'secondary', 'ikincil', 'accent4', '#ff8800'…
        Bilinmiyorsa None."""
        if name.startswith("#"):
            try:
                return hex_color(name)
            except ValueError:
                return None
        name = _ALIASES.get(name, name)
        if name in _COLOR_FIELDS:
            return getattr(self, name)
        for names in (SLOT_NAMES, _SLOT_TR):
            if name in names:
                return self.slot(names.index(name) + 1)
        m = re.fullmatch(r"accent(\d)", name)
        return self.slot(int(m.group(1))) if m and m.group(1) != "0" else None

    def resolve(self, spec) -> Color | None:
        """Bir renk tanımını çöz: sıra numarası (2), ad ("ikincil", "green", "#ff8800") ya da (r, g, b)."""
        if spec is None:
            return None
        if isinstance(spec, bool):
            raise TypeError("renk bool olamaz")
        if isinstance(spec, int):
            return self.slot(spec)
        if isinstance(spec, str):
            return self.color(spec)
        return tuple(spec)[:3]

    def tinted(self, spec) -> Theme:
        """Bu temanın, vurgu rengi spec olan kopyası: bir öge kendi rengiyle çizilirken kullanılır.
        Sıra numarası verilirse ikincil ve üçüncül de paletteki sırayı izler (2 → 2, 3, 1)."""
        if isinstance(spec, int) and not isinstance(spec, bool):
            return replace(self, accent=self.slot(spec), accent2=self.slot(spec + 1), accent3=self.slot(spec + 2))
        color = self.resolve(spec)
        return self if color is None or color == self.accent else replace(self, accent=color)

    def scaled(self, k: float) -> Theme:
        """HiDPI ekranlar için font ve köşe yarıçapını k ile büyüt."""
        if k == 1:
            return self
        return replace(self, font_size=round(self.font_size * k), radius=max(1, round(self.radius * k)))


# Nötr taban: audn web arayüzündeki koyu lacivert-gri palet
_BASE = {
    "bg": "#0b0f17", "surface": "#0e131d", "raised": "#1a2232",
    "border": "#243049", "text": "#e8edf6",
}


def _hue_shift(color: Color, degrees: float) -> Color:
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in color))
    r, g, b = colorsys.hls_to_rgb((h + degrees / 360) % 1, l, s)
    return round(r * 255), round(g * 255), round(b * 255)


def _as_color(value) -> Color:
    return hex_color(value) if isinstance(value, str) else tuple(value)[:3]


def make_theme(name: str, colors=None, *, accent=None, accent2=None, accent3=None,
               ok: str = "#34d399", warn: str = "#fbbf24", err: str = "#f87171", neutral: str = "#64748b",
               blue: str = "#60a5fa", magenta: str = "#c084fc", cyan: str = "#22d3ee",
               background: str | None = None, tint: float = 0.035) -> Theme:
    """Renklerden tam tema üret:

        ui.make_theme("deniz", ["#38bdf8", "#f472b6", "#a3e635", "#fbbf24"])   # birincil, ikincil, …

    colors birincil, ikincil, üçüncül ve isteğe bağlı sonraki renklerdir ("#rrggbb" ya da (r, g, b));
    accent=, accent2=, accent3= tek tek de verilebilir. Üçten az renk verilirse eksikler renk çemberinde
    döndürülerek türetilir. ok, warn, err durum renkleri; neutral soluk yazı tonu (ikincil yazı bununla
    ana yazı renginin arasından türetilir). background zeminin tabanını değiştirir. Zeminler birincil
    renge tint oranında çekilir; böylece her tema kendi havasını taşır.

    Kaydedilen tema (register_theme) adıyla seçilir: App(theme="deniz"), ayar dosyası, komut paleti.
    """
    given = [_as_color(c) for c in (colors or ())]
    for i, value in enumerate((accent, accent2, accent3)):
        if value is not None:
            while len(given) <= i:
                given.append(None)
            given[i] = _as_color(value)
    if not given or given[0] is None:
        raise ValueError("make_theme: en az birincil renk gerekli")
    a = given[0]
    second = given[1] if len(given) > 1 and given[1] is not None else _hue_shift(a, 60)
    third = given[2] if len(given) > 2 and given[2] is not None else _hue_shift(a, 180)
    bases = dict(_BASE)
    if background is not None:
        bg = hex_color(background)
        bases.update(bg=background, surface="#%02x%02x%02x" % mix(bg, (255, 255, 255), 0.02),
                     raised="#%02x%02x%02x" % mix(bg, (255, 255, 255), 0.07),
                     border="#%02x%02x%02x" % mix(bg, (255, 255, 255), 0.14))
    base = {k: mix(hex_color(v), a, tint if k != "text" else 0) for k, v in bases.items()}
    faint = hex_color(neutral)
    return Theme(
        name=name, **base,
        dim=mix(faint, base["text"], 0.38), faint=faint,
        accent=a, accent2=second, accent3=third, extra=tuple(c for c in given[3:] if c is not None),
        red=hex_color(err), green=hex_color(ok), yellow=hex_color(warn),
        blue=hex_color(blue), magenta=hex_color(magenta), cyan=hex_color(cyan),
    )


# audn-cli'daki altı tema, aynı adlarla; her biri üç renkli: birincil, ikincil, üçüncül
THEMES: dict[str, Theme] = {t.name: t for t in (
    make_theme("okyanus", ["#38bdf8", "#818cf8", "#fdba74"], ok="#34d399", warn="#fbbf24", err="#f87171", neutral="#64748b"),
    make_theme("günbatımı", ["#fb923c", "#f472b6", "#a78bfa"], ok="#4ade80", warn="#facc15", err="#ef4444", neutral="#78716c"),
    make_theme("orman", ["#4ade80", "#a3e635", "#fbbf24"], ok="#22c55e", warn="#eab308", err="#f87171", neutral="#6b7280"),
    make_theme("neon", ["#22d3ee", "#e879f9", "#a3e635"], ok="#4ade80", warn="#fde047", err="#fb7185", neutral="#71717a"),
    make_theme("mono", ["#e5e7eb", "#9ca3af", "#cbd5e1"], ok="#d1d5db", warn="#9ca3af", err="#f87171", neutral="#6b7280", tint=0),
    make_theme("lavanta", ["#c084fc", "#f0abfc", "#6ee7b7"], ok="#86efac", warn="#fcd34d", err="#fb7185", neutral="#6b7280"),
)}


def register_theme(theme: Theme) -> Theme:
    """Temayı adıyla seçilebilir yap: App(theme="ad"), ayar dosyasında theme = "ad", komut paleti."""
    THEMES[theme.name] = theme
    return theme


# Hangi öge türü paletin kaçıncı rengiyle çizilir; temadan bağımsızdır. Anahtar bileşen sınıfının adı
# (alt sınıflar üst sınıfınkini kullanır), değer sıra numarası ya da renk adı. App(roles={…}),
# sınıfta ROLES = {…} ya da app.set_roles(Tabs=3) değiştirir; tek bir öge için color= verilir.
ROLES: dict[str, int | str] = {
    # birincil: etkileşim ve odak
    "Button": 1, "Input": 1, "TextArea": 1, "Select": 1, "Spinbox": 1, "Checkbox": 1, "RadioSet": 1,
    "OptionList": 1, "Panel": 1, "MenuBar": 1, "Split": 1, "Canvas": 1, "Chart": 1,
    # ikincil: değer ve ilerleme
    "ProgressBar": 2, "Slider": 2, "Sparkline": 2,
    # üçüncül: gezinme ve yapı
    "Tabs": 3, "Tree": 3, "Table": 3, "Header": 3, "StatusBar": 3, "KeyBar": 3,
}

# Hazır biçim kümeleri: herhangi bir renk temasıyla birleştirilebilir
LOOKS: dict[str, dict] = {
    "terminal": dict(radius=0, panel_fill=False, title="inverse", frame="faint", focus="title", button="solid",
                     bar="block", selection="inverse", shadow="hard", radio="paren",
                     tabs="inverse", slider="bar", select="bracket", image="smooth", spin="bracket",
                     split="line", field="boxed", toggle="drawn"),
    "modern": dict(radius=6, panel_fill=True, title="inline", frame="none", focus="title", button="pill",
                   bar="block", selection="pointer", shadow="soft", radio="dot",
                   tabs="underline", slider="line", select="underline", image="smooth", spin="stacked",
                   split="line", field="filled", toggle="drawn"),
}

# Yoğunluk kümeleri: satır yüksekliği (doğal yüksekliğin katı) ve panel iç boşlukları
DENSITIES: dict[str, dict] = {
    "sıkı": dict(line_height=1.0, pad_x=1.0, pad_y=0.35),
    "dengeli": dict(line_height=1.1, pad_x=1.5, pad_y=0.5),
    "rahat": dict(line_height=1.15, pad_x=1.75, pad_y=0.65),
    "ferah": dict(line_height=1.25, pad_x=2.0, pad_y=0.8),
}


# Biçim belirteçlerinin alabileceği değerler; ayar dosyası ve ortam değişkenleri bunlarla denetlenir
CHOICES: dict[str, tuple[str, ...]] = {
    "title": ("inverse", "inline", "tab"),
    "frame": ("line", "faint", "corners", "none"),
    "focus": ("color", "double", "title", "bar", "none"),
    "button": ("bracket", "tinted", "angle", "solid", "boxed", "pill"),
    "bar": ("block", "segment", "line", "ascii"),
    "selection": ("inverse", "pointer"),
    "shadow": ("hard", "soft", "none"),
    "toggle": ("drawn", "text"),
    "radio": ("paren", "dot"),
    "tabs": ("inverse", "folder", "underline", "bracket"),
    "slider": ("bar", "line", "value"),
    "field": ("boxed", "filled", "underline", "plain"),
    "select": ("bracket", "arrows", "underline"),
    "image": ("smooth", "pixel", "blocks"),
    "spin": ("bracket", "arrows", "stacked"),
    "split": ("line", "bar", "hidden"),
    "form_label": ("left", "top"),
    "chart": ("smooth", "braille", "blocks"),
}


def with_look(theme: Theme, look: str = "terminal", density: str | None = None, **overrides) -> Theme:
    """Renk temasına biçim ve yoğunluk kümesi uygula; overrides tek tek belirteçleri ezer.

        with_look(THEMES["neon"], "terminal", density="ferah", title="inline", bar="segment")

    Renkler "#ff8800" biçiminde de verilebilir: with_look(tema, accent="#ff8800").
    """
    overrides = {k: hex_color(v) if k in _COLOR_FIELDS and isinstance(v, str) else v for k, v in overrides.items()}
    return replace(theme, **{**LOOKS[look], **(DENSITIES[density] if density else {}), **overrides})
