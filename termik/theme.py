"""Tema: renk paleti ve ölçüler.

Renkler opak RGB olarak tutulur. Yarı saydam görünen her şey (seçili satır, hover zemini,
soluk yazı) zemine `mix()` ile karıştırılmış opak bir renktir: pygame'de alfa karıştırma hem
pahalı hem de yüzey tipine bağlı, opak renk ise her yerde aynı davranır.
"""

from __future__ import annotations

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
    "accent", "accent2", "red", "green", "yellow", "blue", "magenta", "cyan",
})

# Markup'ta rich/ANSI alışkanlığıyla yazılabilecek eş anlamlılar
_ALIASES = {
    "white": "text", "black": "bg", "gray": "dim", "grey": "dim",
    "primary": "accent", "secondary": "accent2", "purple": "magenta",
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
    accent: Color
    accent2: Color
    red: Color
    green: Color
    yellow: Color
    blue: Color
    magenta: Color
    cyan: Color
    # ölçüler (ölçek 1.0'da piksel)
    font_size: int = 15
    line_height: float = 1.15   # fontun doğal satır yüksekliğinin katı (terminallerdeki gibi)
    radius: int = 0             # köşe yarıçapı; 0 = keskin ┌┐
    # biçim belirteçleri: varsayılanlar "terminal" görünümü + "rahat" yoğunluk
    pad_x: float = 1.75         # panel iç boşluğu, karakter cinsinden
    pad_y: float = 0.65         # panel iç boşluğu ve gruplar arası, satır cinsinden
    panel_fill: bool = False    # paneller zeminden ayrı renkte mi (kart görünümü)
    title: str = "inverse"      # inverse ters renkli etiket · inline ┌─ Başlık ─┐ · tab ┤ Başlık ├
    focus: str = "color"        # color: odakta vurgu rengi · double: odakta çift çizgi
    button: str = "bracket"     # bracket [ Tamam ] · angle < Tamam > · solid dolu blok · pill hap
    bar: str = "block"          # block █▊░ · segment ▰▱ · line ━━─ · ascii [##--]
    selection: str = "inverse"  # inverse: tam satır ters renk · pointer: ❯ + hafif zemin
    shadow: str = "hard"        # hard: kaydırılmış koyu blok · soft: bulanık · none
    radio: str = "paren"        # paren (•) ( ) · dot ● ○
    tabs: str = "inverse"       # inverse ters renkli · folder klasör sekmesi · underline alt çizgi · bracket [ Genel ]
    slider: str = "bar"         # bar ilerleme çubuğu gibi · line ince iz ve yuvarlak tutamak · value ◂ 60 ▸
    select: str = "bracket"     # bracket [ Artımlı ▾ ] · arrows ◂ Artımlı ▸ · underline altı çizili
    image: str = "smooth"       # smooth yumuşak ölçek · pixel iri pikseller · blocks terminal gibi ▀ yarım bloklar
    spin: str = "bracket"       # bracket [ − 12 + ] · arrows ◂ 12 ▸ · stacked sağda ▴▾
    split: str = "line"         # line ince çizgi ve ⋮ tutamak · bar dolu sütun · hidden yalnızca fare gelince
    form_label: str = "left"    # left etiketler solda hizalı · top alanın üstünde
    chart: str = "smooth"       # smooth yumuşak çizgiler · braille ⣀⡠ noktaları · blocks ▁▃▇ blokları

    def color(self, name: str) -> Color | None:
        """Markup'taki renk adını çöz: 'green', 'accent', '#ff8800'… Bilinmiyorsa None."""
        if name.startswith("#"):
            try:
                return hex_color(name)
            except ValueError:
                return None
        name = _ALIASES.get(name, name)
        return getattr(self, name) if name in _COLOR_FIELDS else None

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


def make_theme(name: str, *, accent: str, accent2: str, ok: str, warn: str, err: str, neutral: str,
               blue: str = "#60a5fa", magenta: str = "#c084fc", cyan: str = "#22d3ee",
               tint: float = 0.035) -> Theme:
    """Birkaç vurgu renginden tam tema üret.

    Zeminler vurgu rengine `tint` oranında çekilir; böylece her tema kendi havasını taşır
    (günbatımı hafif sıcak, orman hafif yeşil…). `neutral` soluk yazı tonudur; ikincil yazı
    (dim) bununla ana yazı renginin arasından türetilir.
    """
    a = hex_color(accent)
    base = {k: mix(hex_color(v), a, tint if k != "text" else 0) for k, v in _BASE.items()}
    faint = hex_color(neutral)
    return Theme(
        name=name, **base,
        dim=mix(faint, base["text"], 0.38), faint=faint,
        accent=a, accent2=hex_color(accent2),
        red=hex_color(err), green=hex_color(ok), yellow=hex_color(warn),
        blue=hex_color(blue), magenta=hex_color(magenta), cyan=hex_color(cyan),
    )


# audn-cli'daki altı tema, aynı adlar ve vurgularla
THEMES: dict[str, Theme] = {t.name: t for t in (
    make_theme("okyanus", accent="#38bdf8", accent2="#818cf8", ok="#34d399", warn="#fbbf24", err="#f87171", neutral="#64748b"),
    make_theme("günbatımı", accent="#fb923c", accent2="#f472b6", ok="#4ade80", warn="#facc15", err="#ef4444", neutral="#78716c"),
    make_theme("orman", accent="#4ade80", accent2="#a3e635", ok="#22c55e", warn="#eab308", err="#f87171", neutral="#6b7280"),
    make_theme("neon", accent="#22d3ee", accent2="#e879f9", ok="#4ade80", warn="#fde047", err="#fb7185", neutral="#71717a"),
    make_theme("mono", accent="#e5e7eb", accent2="#9ca3af", ok="#d1d5db", warn="#9ca3af", err="#f87171", neutral="#6b7280", tint=0),
    make_theme("lavanta", accent="#c084fc", accent2="#f0abfc", ok="#86efac", warn="#fcd34d", err="#fb7185", neutral="#6b7280"),
)}

# Hazır biçim kümeleri: herhangi bir renk temasıyla birleştirilebilir
LOOKS: dict[str, dict] = {
    "terminal": dict(radius=0, panel_fill=False, title="inverse", focus="color", button="bracket",
                     bar="block", selection="inverse", shadow="hard", radio="paren",
                     tabs="inverse", slider="bar", select="bracket", image="smooth", spin="bracket",
                     split="line"),
    "modern": dict(radius=6, panel_fill=True, title="inline", focus="color", button="pill",
                   bar="block", selection="pointer", shadow="soft", radio="dot",
                   tabs="underline", slider="line", select="underline", image="smooth", spin="stacked",
                   split="line"),
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
    "focus": ("color", "double"),
    "button": ("bracket", "angle", "solid", "pill"),
    "bar": ("block", "segment", "line", "ascii"),
    "selection": ("inverse", "pointer"),
    "shadow": ("hard", "soft", "none"),
    "radio": ("paren", "dot"),
    "tabs": ("inverse", "folder", "underline", "bracket"),
    "slider": ("bar", "line", "value"),
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
