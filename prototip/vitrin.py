"""termik · vitrin — görünüm prototipi.

Kütüphanenin bileşen ve yerleşim katmanı henüz yok. Bu dosya ekranı elle yerleştirip tema,
metin ve çizim katmanının nasıl göründüğünü ve hissettirdiğini denemek için var.

    python prototip/vitrin.py                          canlı pencere, terminal görünümü
    python prototip/vitrin.py --theme neon --density ferah
    python prototip/vitrin.py --look modern
    python prototip/vitrin.py --set title=inline --set bar=segment --set button=angle
    python prototip/vitrin.py --font yol/Hack-Regular.ttf
    python prototip/vitrin.py --shot vitrin.png        pencere açmadan ekran görüntüsü

Kısayollar: tab panel · ↑↓ seç · ⏎ başlat/duraklat · esc iptal · ctrl+p komut paleti
            F2 tema · F3 başlık biçimi · F4 yoğunluk · F5 bileşen takımı
            ctrl+l günlüğü temizle · ctrl+q çık
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from termik.draw import Painter  # noqa: E402  (termik, pygame'in karşılama satırını susturur)
from termik.fonts import default_font_paths  # noqa: E402
from termik.text import Style  # noqa: E402
from termik.theme import DENSITIES, LOOKS, THEMES, mix, with_look  # noqa: E402

import pygame  # noqa: E402

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
TOTAL = 640   # kopyalanacak dosya sayısı
RATE = 0.03   # saniye başına ilerleme (~33 sn'de biter)
NAMES = list(THEMES)

# F3 / F4 / F5 ile canlı değiştirilebilen görünüm seçenekleri
TITLES = ("inverse", "inline", "tab")
PARTS = {  # bileşen takımları: karşılaştırma sayfasındaki K1–K4
    "blok": dict(bar="block", button="bracket", selection="inverse", radio="paren"),
    "bölmeli": dict(bar="segment", button="angle", selection="inverse", radio="paren"),
    "ince": dict(bar="line", button="solid", selection="pointer", radio="dot"),
    "ascii": dict(bar="ascii", button="bracket", selection="inverse", radio="paren"),
}


# ───────────────────────────── örnek veri ─────────────────────────────

@dataclass
class Entry:
    name: str
    depth: int
    is_dir: bool = False
    size: str = ""
    open: bool = False


FILES = [
    Entry("Belgeler", 0, True, open=True),
    Entry("projeler", 1, True, open=True),
    Entry("termik", 2, True),
    Entry("audn-cli", 2, True),
    Entry("dolphin-cli", 2, True),
    Entry("fotoğraflar", 1, True),
    Entry("rapor.md", 1, size="12 KB"),
    Entry("notlar.txt", 1, size="3 KB"),
    Entry("sunum.pdf", 1, size="2.1 MB"),
    Entry("İndirilenler", 0, True),
    Entry("Masaüstü", 0, True),
]

SEED_LOG = [
    ("14:31:02", "ok", "yapılandırma yüklendi"),
    ("14:31:02", "info", "kaynak tarandı: [bold]640[/] dosya · 2.4 GB"),
    ("14:31:05", "warn", "3 gizli dosya atlandı"),
    ("14:31:09", "ok", "projeler/termik kopyalandı"),
    ("14:31:12", "err", "izin reddedildi: [dim]Thumbs.db[/]"),
    ("14:31:15", "ok", "projeler/audn-cli kopyalandı"),
    ("14:31:21", "info", "📦 arşiv: [accent]yedek-2026-10-28.tar.zst[/]"),
    ("14:31:26", "ok", "projeler/dolphin-cli kopyalandı"),
]

EVENTS = [
    ("ok", "fotoğraflar/2026/ekim kopyalandı"),
    ("info", "sıkıştırma oranı [accent]%38[/]"),
    ("ok", "rapor.md kopyalandı"),
    ("warn", "uzun yol kısaltıldı: [dim]…/node_modules/.cache[/]"),
    ("ok", "notlar.txt kopyalandı"),
    ("err", "kilitli dosya: [dim]~$sunum.pptx[/]"),
    ("ok", "sunum.pdf kopyalandı"),
]

CURRENT = [
    "fotoğraflar/2026/ekim/IMG_4021.jpg",
    "projeler/termik/termik/draw.py",
    "Belgeler/rapor.md",
    "fotoğraflar/2026/eylül/IMG_3310.jpg",
]

HISTORY = [
    ("ok", "27.10 22:14", "artımlı", "38", "412 MB", "0:42"),
    ("ok", "20.10 22:10", "tam", "612", "2.3 GB", "4:05"),
    ("warn", "13.10 22:12", "artımlı", "55", "601 MB", "0:51"),
    ("ok", "06.10 22:09", "tam", "598", "2.2 GB", "3:58"),
    ("ok", "29.09 22:11", "artımlı", "21", "88 MB", "0:19"),
    ("err", "22.09 22:15", "artımlı", "—", "—", "0:03"),
]

ICONS = {"ok": ("✓", "green"), "info": ("•", "blue"), "warn": ("⚠", "yellow"), "err": ("✗", "red")}


# ───────────────────────────── durum ─────────────────────────────

@dataclass
class State:
    theme_i: int = 0
    density: str = "rahat"
    title: str | None = None  # None: biçim kümesinin varsayılanı
    parts: str | None = None
    focus: str = "form"  # files | form | log
    files: list[Entry] = field(default_factory=lambda: [replace(e) for e in FILES])
    sel: int = 1
    fields: list[str] = field(default_factory=lambda: ["~/Belgeler/projeler", "D:\\Yedek\\2026-10-28"])
    field_i: int = 0
    mode: int = 0
    opts: list[bool] = field(default_factory=lambda: [True, False])
    progress: float = 0.64
    running: bool = True
    paused: bool = False
    log: list[tuple[str, str, str]] = field(default_factory=lambda: list(SEED_LOG))
    cpu: list[float] = field(default_factory=list)
    palette: bool = False
    query: str = ""
    pal_i: int = 0
    t: float = 0.0
    typed_at: float = -10.0   # yazarken imleç yanıp sönmesin
    next_event: float = 1.2
    next_cpu: float = 0.0
    mouse: tuple[int, int] | None = None
    hits: list = field(default_factory=list)  # [(Rect, eylem)] — son çizilen karenin tıklanabilir alanları
    clock: str | None = None   # ekran görüntüsünde sabit saat
    blink: bool | None = None  # ekran görüntüsünde sabit imleç
    quit: bool = False


def phase(s: State) -> str:
    if s.running:
        return "paused" if s.paused else "running"
    return "done" if s.progress >= 1 else "idle"


def hot(s: State, rect) -> bool:
    return s.mouse is not None and pygame.Rect(rect).collidepoint(s.mouse)


def clickable(s: State, rect, action) -> None:
    s.hits.append((pygame.Rect(rect), action))


def visible(files: list[Entry]) -> list[Entry]:
    """Kapalı klasörlerin altını gizleyerek görünen satırlar."""
    out, hide = [], None
    for e in files:
        if hide is not None and e.depth > hide:
            continue
        hide = None
        out.append(e)
        if e.is_dir and not e.open:
            hide = e.depth
    return out


def entry_path(vis: list[Entry], i: int) -> str:
    parts, depth = [vis[i].name], vis[i].depth
    for e in reversed(vis[:i]):
        if e.depth < depth:
            parts.insert(0, e.name)
            depth = e.depth
    return "~/" + "/".join(parts)


def add_log(s: State, kind: str, msg: str) -> None:
    s.log.append((time.strftime("%H:%M:%S"), kind, msg))
    del s.log[:-200]


# ───────────────────────────── eylemler ─────────────────────────────

def start_or_pause(s: State) -> None:
    if s.running:
        s.paused = not s.paused
        add_log(s, "info", "duraklatıldı" if s.paused else "devam ediliyor")
        return
    if s.progress >= 1:
        s.progress = 0
    s.running, s.paused = True, False
    add_log(s, "info", f"yedekleme başladı: [accent]{s.fields[0]}[/] → {s.fields[1]}")


def cancel(s: State) -> None:
    if s.running:
        s.running = s.paused = False
        s.progress = 0
        add_log(s, "warn", "yedekleme iptal edildi")


def next_theme(s: State, step: int = 1) -> None:
    s.theme_i = (s.theme_i + step) % len(NAMES)


def cycle(options, current, step: int = 1):
    options = list(options)
    return options[(options.index(current) + step) % len(options)] if current in options else options[0]


def next_title(s: State, step: int = 1) -> None:
    s.title = cycle(TITLES, s.title or TITLES[0], step)


def next_density(s: State, step: int = 1) -> None:
    s.density = cycle(DENSITIES, s.density, step)


def next_parts(s: State, step: int = 1) -> None:
    s.parts = cycle(PARTS, s.parts or "blok", step)


def focus(s: State, name: str, field_i: int | None = None) -> None:
    s.focus = name
    if field_i is not None:
        s.field_i = field_i


def select(s: State, i: int) -> None:
    """Satırı seç; seçili bir klasöre yeniden tıklamak onu açar/kapatır."""
    vis = visible(s.files)
    if s.focus == "files" and s.sel == i and vis[i].is_dir:
        vis[i].open = not vis[i].open
    s.focus, s.sel = "files", i


def use_selected(s: State) -> None:
    vis = visible(s.files)
    if vis[s.sel].is_dir:
        s.fields[0] = entry_path(vis, s.sel)
        focus(s, "form", 0)


def commands(s: State) -> list[tuple[str, str, object]]:
    run = "Yedeklemeyi duraklat" if phase(s) == "running" else "Yedeklemeyi başlat"
    return [
        (run, "⏎", lambda: start_or_pause(s)),
        ("Yedeklemeyi iptal et", "esc", lambda: cancel(s)),
        ("Yedeği doğrula", "ctrl+d", lambda: add_log(s, "info", "doğrulama sıraya alındı")),
        ("Yedekleme geçmişi", "ctrl+h", lambda: add_log(s, "info", "son yedek: [dim]dün 22:14[/]")),
        ("Son yedeği geri yükle", "", lambda: add_log(s, "warn", "geri yükleme bu prototipte yok")),
        ("Temayı değiştir", "F2", lambda: next_theme(s)),
        ("Başlık biçimini değiştir", "F3", lambda: next_title(s)),
        ("Yoğunluğu değiştir", "F4", lambda: next_density(s)),
        ("Bileşen takımını değiştir", "F5", lambda: next_parts(s)),
        ("Günlüğü temizle", "ctrl+l", lambda: s.log.clear()),
        ("Kaynak klasörü düzenle", "", lambda: focus(s, "form", 0)),
        ("Dosyalar paneline geç", "tab", lambda: focus(s, "files")),
        ("Çıkış", "ctrl+q", lambda: setattr(s, "quit", True)),
    ]


_FOLD = str.maketrans("İIıŞşĞğÇçÖöÜü", "iiissggccoouu")


def fold(text: str) -> str:
    """Türkçe harfleri gevşet: 'baslat' yazınca 'Başlat' da eşleşsin. Uzunluk değişmez."""
    return text.translate(_FOLD).lower()


def fuzzy(query: str, text: str) -> list[int] | None:
    """fzf benzeri alt dizi eşleşmesi; eşleşen karakterlerin sıraları ya da None."""
    q, t = fold(query).replace(" ", ""), fold(text)
    pos, i = [], 0
    for c in q:
        i = t.find(c, i)
        if i < 0:
            return None
        pos.append(i)
        i += 1
    return pos


def palette_items(s: State) -> list[tuple]:
    items = []
    for n, (name, key, action) in enumerate(commands(s)):
        pos = fuzzy(s.query, name) if s.query else []
        if pos is None:
            continue
        # bitişik ve başa yakın eşleşmeler önce
        score = (pos[-1] - pos[0] - len(pos) + 1) * 2 + pos[0] if pos else 0
        items.append((score, n, name, key, action, pos))
    items.sort(key=lambda it: (it[0], it[1]))
    return items


def run_command(s: State, action) -> None:
    s.palette, s.query = False, ""
    action()


def close_palette(s: State) -> None:
    s.palette, s.query = False, ""


# ───────────────────────────── çizim ─────────────────────────────

def form_layout(p: Painter) -> dict[str, int]:
    """Form satırlarının içerik üstünden uzaklıkları ve içeriğin toplam yüksekliği."""
    g = max(p.row // 2, round(p.row * p.theme.pad_y))  # gruplar arası boşluk
    out, y = {}, 0
    for i in range(2):
        out[f"field{i}"] = y
        y += p.row * 2 + g
    out["mode"], out["opts"] = y, y + p.row
    y += p.row * 2 + g
    out["head"], out["bar"], out["detail"] = y, y + p.row, y + p.row * 2
    y += p.row * 3 + g
    out["buttons"] = y
    out["height"] = y + p.button_size("Duraklat ⏎", True)[1]
    return out


def render(p: Painter, s: State) -> dict[str, pygame.Rect]:
    """Bütün ekranı çiz; panellerin dikdörtgenlerini döndür (testler ve kırpma için)."""
    th = p.theme
    W, H = p.surface.get_size()
    ch, row = p.ch, p.row
    M = ch * 2
    p.surface.fill(th.bg)

    # başlık: logo + sürüm solda, durum + saat sağda; hepsi aynı taban çizgisinde
    hy, hh = round(row * 0.5), row * 2
    base = hy + (hh - p.heading.height) // 2 + p.heading.stack.ascent
    lw = p.gradient_text(M, base - p.heading.stack.ascent, "termik", th.accent, th.accent2)
    p.text.draw(p.surface, M + lw + ch, 0, "[faint]v0.0.1 · vitrin[/]", baseline=base)
    right = f"[faint]{s.clock or time.strftime('%H:%M')}[/]"
    x = W - M - p.text.width(right)
    p.text.draw(p.surface, x, 0, right, baseline=base)
    status = header_status(s)
    p.text.draw(p.surface, x - ch * 3 - p.text.width(status), 0, status, baseline=base)

    # yerleşim: üç sütun, sağ sütun ikiye bölünmüş. Dar pencerede önce sağ sütun daralır,
    # orta sütun yine sığmıyorsa sağ sütun tamamen gizlenir.
    top = hy + hh + round(row * 0.4)
    sh = row + (6 if th.radius else 2)
    sy = H - round(row * 0.6) - sh
    ky = sy - row - 6
    bottom = ky - round(row * 0.5)
    gap = ch + 4
    inner = W - 2 * M
    left_w = max(22 * ch, min(30 * ch, inner // 4))
    right_w = max(32 * ch, min(46 * ch, inner * 3 // 8))
    mid_w = inner - left_w - right_w - 2 * gap
    if mid_w < 46 * ch:
        take = min(46 * ch - mid_w, right_w - 32 * ch)
        right_w -= take
        mid_w += take
    if mid_w < 44 * ch:
        right_w, mid_w = 0, inner - left_w - gap
    pad = p.pad[1]
    rects = {"files": pygame.Rect(M, top, left_w, bottom - top)}
    rects["form"] = pygame.Rect(rects["files"].right + gap, top, mid_w, form_layout(p)["height"] + pad * 2 + 2)
    hist = pygame.Rect(rects["form"].x, rects["form"].bottom + gap, mid_w, bottom - rects["form"].bottom - gap)
    if hist.h >= row * 4:
        rects["history"] = hist
    else:  # pencere kısaysa geçmiş tablosu gizlenir, form uzar
        rects["form"].h = bottom - top
    if right_w:
        rects["system"] = pygame.Rect(rects["form"].right + gap, top, right_w, row * 3 + pad * 2 + 2)
        sy_r = rects["system"]
        rects["log"] = pygame.Rect(sy_r.x, sy_r.bottom + gap, right_w, bottom - sy_r.bottom - gap)

    draw_files(p, s, rects["files"])
    draw_form(p, s, rects["form"])
    if "history" in rects:
        draw_history(p, s, rects["history"])
    if right_w:
        draw_system(p, s, rects["system"])
        draw_log(p, s, rects["log"])
    draw_footer(p, s, ky, sy, sh)
    if s.palette:
        rects["palette"] = draw_palette(p, s)
    return rects


def spinner(s: State) -> str:
    return SPINNER[int(s.t * 12) % len(SPINNER)]


def header_status(s: State) -> str:
    return {
        "running": f"[accent]{spinner(s)}[/] [dim]yedekleniyor · {round(s.progress * 100)}%[/]",
        "paused": "[yellow]‖[/] [dim]duraklatıldı[/]",
        "done": "[green]✓[/] [dim]tamamlandı[/]",
        "idle": "[faint]●[/] [dim]hazır[/]",
    }[phase(s)]


def draw_files(p: Painter, s: State, r: pygame.Rect) -> None:
    th = p.theme
    focused = s.focus == "files"
    pointer = th.selection == "pointer"
    vis = visible(s.files)
    s.sel = min(s.sel, len(vis) - 1)
    clickable(s, r, lambda: focus(s, "files"))
    with p.panel(r, "Dosyalar", focused=focused, footer=f"[faint]{s.sel + 1}/{len(vis)}[/]"):
        c = p.inset(r)
        y = c.y
        for i, e in enumerate(vis):
            if y + p.row > c.bottom:
                break
            row_r = pygame.Rect(c.x - p.ch, y, c.w + p.ch * 2, p.row)
            fg = None
            if i == s.sel:
                fg = p.selection(row_r, focused=focused)
                if pointer:
                    p.write(c.x - p.ch // 2, y, "❯", Style(bold=True), th.accent if focused else th.dim)
            elif hot(s, row_r):
                p.hover(row_r)
            tx = c.x + (p.ch * 2 if pointer else 0) + e.depth * p.ch * 2
            arrow = "▾" if e.open else "▸"
            if fg:  # ters renkli satırda bütün yazı tek renk
                name = [(f"{arrow} {e.name}" if e.is_dir else f"  {e.name}", Style(bold=True, fg=fg))]
            elif e.is_dir:
                name = f"[faint]{arrow}[/] [blue]{e.name}[/]"
            else:
                name = f"  {e.name}"
            size_w = p.text.width(e.size) + p.ch if e.size else 0
            p.write(tx, y, p.text.elide(name, c.right - size_w - tx, Style(bold=i == s.sel)))
            if e.size:
                p.write(c.right, y, e.size, color=fg or th.faint, right=True)
            clickable(s, row_r, lambda i=i: select(s, i))
            y += p.row


def option(p: Painter, s: State, x: int, y: int, markup: str, action) -> int:
    """Radyo/onay kutusu gibi tıklanabilir satır içi seçenek; genişliğini döndürür."""
    w = p.text.width(markup)
    rect = pygame.Rect(x - p.ch // 2, y, w + p.ch, p.row)
    if hot(s, rect):
        p.hover(rect)
    p.write(x, y, markup)
    clickable(s, rect, action)
    return w


def button(p: Painter, s: State, x: int, y: int, label: str, primary: bool, action) -> pygame.Rect:
    w, h = p.button_size(label, primary)
    rect = p.button(x, y, label, primary=primary, hot=hot(s, (x, y, w, h)))
    clickable(s, rect, action)
    return rect


def draw_form(p: Painter, s: State, r: pygame.Rect) -> None:
    th = p.theme
    focused = s.focus == "form"
    ph = phase(s)
    clickable(s, r, lambda: focus(s, "form"))
    with p.panel(r, "Yedekleme", focused=focused, info=f"[faint]{'tam' if s.mode == 0 else 'artımlı'} yedek[/]"):
        c = p.inset(r)
        L = form_layout(p)
        lx = c.x + p.ch + p.ch // 2  # alan çubuğunun sağındaki yazı hizası

        # metin alanları: etiket + "❯ değer█"; etkin alanın solunda vurgu çubuğu
        cursor_on = s.blink if s.blink is not None else (s.t - s.typed_at < 0.6 or (s.t % 1.1) < 0.65)
        for i, label in enumerate(("Kaynak klasör", "Hedef klasör")):
            y = c.y + L[f"field{i}"]
            active = focused and s.field_i == i
            p.surface.fill(th.accent if active else th.border, (c.x, y + 3, 2, p.row * 2 - 6))
            p.write(lx, y, label, color=th.text if active else th.dim)
            pw = p.write(lx, y + p.row, "❯ ", Style(bold=True), th.accent if active else th.faint)
            vw = p.write(lx + pw, y + p.row, p.text.elide(s.fields[i], c.right - lx - pw - p.ch))
            if active and cursor_on:
                p.surface.fill(th.accent, (lx + pw + vw, y + p.row + (p.row - p.text.height) // 2, p.ch, p.text.height))
            clickable(s, (c.x, y, c.w, p.row * 2), lambda i=i: focus(s, "form", i))

        # radyo ve onay kutuları
        label_w = p.ch * 12
        y = c.y + L["mode"]
        p.write(lx, y, "Mod", color=th.dim)
        ox = lx + label_w
        for i, name in enumerate(("Tam", "Artımlı")):
            on = s.mode == i
            markup = f"{p.radio(on)} " + (name if on else f"[dim]{name}[/]")
            ox += option(p, s, ox, y, markup, lambda i=i: setattr(s, "mode", i)) + p.ch * 3
        y = c.y + L["opts"]
        p.write(lx, y, "Seçenekler", color=th.dim)
        ox = lx + label_w
        for i, name in enumerate(("Sıkıştır", "Şifrele")):
            on = s.opts[i]
            markup = f"{p.check(on)} " + (name if on else f"[dim]{name}[/]")
            ox += option(p, s, ox, y, markup, lambda i=i: s.opts.__setitem__(i, not s.opts[i])) + p.ch * 3

        # ilerleme
        head = {
            "running": f"[accent]{spinner(s)}[/] Kopyalanıyor",
            "paused": "[yellow]‖[/] Duraklatıldı",
            "done": "[green]✓[/] Tamamlandı",
            "idle": "[faint]●[/] [dim]Başlamaya hazır[/]",
        }[ph]
        y = c.y + L["head"]
        p.write(lx, y, head)
        p.write(c.right, y, f"[bold]{round(s.progress * 100)}%[/]", right=True)
        p.bar(lx, c.y + L["bar"], c.right - lx, s.progress)
        done = round(s.progress * TOTAL)
        if ph == "running":
            remain = (1 - s.progress) / RATE
            speed = 38.2 + 3 * math.sin(s.t * 0.7)
            detail = f"{done} / {TOTAL} dosya · {speed:.1f} MB/s · ~{int(remain // 60):02d}:{int(remain % 60):02d} kaldı"
        else:
            detail = f"{done} / {TOTAL} dosya"
        p.write(lx, c.y + L["detail"], detail, color=th.dim)

        # butonlar: sağda, sağdan sola
        primary = {"running": "Duraklat", "paused": "Devam"}.get(ph, "Başlat")
        x, y = c.right, c.y + L["buttons"]
        for label, is_primary, action in ((f"{primary} ⏎", True, lambda: start_or_pause(s)),
                                          ("İptal", False, lambda: cancel(s))):
            x -= p.button_size(label, is_primary)[0]
            button(p, s, x, y, label, is_primary, action)
            x -= p.ch * 2


def draw_history(p: Painter, s: State, r: pygame.Rect) -> None:
    th = p.theme
    with p.panel(r, "Geçmiş", info=f"[faint]{len(HISTORY)} yedek[/]"):
        c = p.inset(r)
        # sütunlar: (başlık, genişlik ch, hizalama); 0 genişlik kalan yeri doldurur
        cols = [("", 3, "l"), ("Tarih", 14, "l"), ("Mod", 0, "l"), ("Dosya", 7, "r"), ("Boyut", 9, "r"), ("Süre", 7, "r")]
        flex = max(p.ch * 6, c.w - sum(w for _, w, _ in cols) * p.ch)
        edges = [c.x]
        for _, w, _ in cols:
            edges.append(edges[-1] + (w * p.ch if w else flex))

        def line(y: int, values: list[str], color=None, style: Style = Style()) -> None:
            for i, ((_, _, align), v) in enumerate(zip(cols, values)):
                if align == "r":
                    p.write(edges[i + 1], y, v, style, color, right=True)
                else:
                    p.write(edges[i], y, p.text.elide(v, edges[i + 1] - edges[i] - p.ch, style), color=color)

        y = c.y
        line(y, [col[0] for col in cols], th.dim, Style(bold=True))
        y += p.row + 2
        p.surface.fill(th.border, (c.x, y, c.w, 1))
        y += 3
        for kind, date, mode, count, size, dur in HISTORY:
            if y + p.row > c.bottom:
                break
            rr = pygame.Rect(c.x - p.ch // 2, y, c.w + p.ch, p.row)
            if hot(s, rr):
                p.hover(rr)
            icon, color = ICONS[kind]
            line(y, [f"[{color}]{icon}[/]", f"[dim]{date}[/]", mode, count, size, f"[dim]{dur}[/]"])
            y += p.row


def draw_system(p: Painter, s: State, r: pygame.Rect) -> None:
    th = p.theme
    with p.panel(r, "Sistem", info="[faint]0.5 sn[/]"):
        c = p.inset(r)
        lx, rx, y = c.x, c.right, c.y
        vx = lx + p.ch * 5

        cpu = s.cpu[-1] if s.cpu else 0
        p.write(lx, y, "CPU", color=th.dim)
        p.write(rx, y, f"{round(cpu * 100)}%", right=True)
        n = max(4, (rx - p.ch * 6 - vx) // p.ch)
        p.spark(vx, y, s.cpu[-n:], th.green)
        y += p.row

        ram = "6.1 / 16 GB"
        p.write(lx, y, "RAM", color=th.dim)
        p.write(rx, y, ram, right=True)
        p.bar(vx, y, rx - p.text.width(ram) - p.ch * 2 - vx, 6.1 / 16, style="line", colors=(th.accent2, th.accent2))
        y += p.row

        down = 38.2 + 3 * math.sin(s.t * 0.7) if phase(s) == "running" else 0.0
        p.write(lx, y, "Ağ", color=th.dim)
        p.write(vx, y, f"[green]↓[/] {down:.1f} MB/s   [accent]↑[/] 1.2 MB/s")


def draw_log(p: Painter, s: State, r: pygame.Rect) -> None:
    th = p.theme
    clickable(s, r, lambda: focus(s, "log"))
    with p.panel(r, "Günlük", focused=s.focus == "log", info=f"[faint]{len(s.log)} kayıt[/]"):
        c = p.inset(r)
        y = c.y
        fit = max(0, c.h // p.row)
        live = phase(s) == "running"
        k = fit - (1 if live else 0)
        if not s.log:
            p.write(c.x, y, "henüz kayıt yok", color=th.faint)
        for ts, kind, msg in s.log[-k:] if k > 0 else []:
            icon, color = ICONS[kind]
            p.write(c.x, y, p.text.elide(f"[faint]{ts}[/]  [{color}]{icon}[/] {msg}", c.w))
            y += p.row
        if live and fit:
            cur = CURRENT[int(s.t / 2.5) % len(CURRENT)]
            p.write(c.x, y, p.text.elide(f"{' ' * 10}[accent]{spinner(s)}[/] [dim]{cur}[/]", c.w))


def draw_footer(p: Painter, s: State, ky: int, sy: int, sh: int) -> None:
    th = p.theme
    W = p.surface.get_width()
    M = p.ch * 2

    hints = [("tab", "panel"), ("↑↓", "seç"), ("⏎", "başlat/duraklat"), ("esc", "iptal"),
             ("ctrl+p", "komutlar"), ("F2–F5", "görünüm"), ("ctrl+q", "çık")]
    p.write(M, ky, p.text.elide("  [faint]·[/]  ".join(f"{k} [dim]{d}[/]" for k, d in hints), W - 2 * M))

    # durum çubuğu: solda mod rozeti + bağlam, sağda bilgiler
    bar = pygame.Rect(M, sy, W - 2 * M, sh)
    p.round_rect(bar, th.raised)
    mode, color = {
        "running": ("ÇALIŞIYOR", th.green), "paused": ("DURAKLATILDI", th.yellow),
        "done": ("TAMAMLANDI", th.accent), "idle": ("HAZIR", th.accent),
    }[phase(s)]
    bw = p.small.width(mode, Style(bold=True)) + p.ch * 3
    p.pill(pygame.Rect(bar.x, bar.y, bw, sh), color, mode, th.bg, bold=True, font=p.small)
    right = (f"[green]●[/] [dim]bağlı[/]   [faint]UTF-8   py {sys.version_info.major}.{sys.version_info.minor}[/]"
             f"   [accent]{th.name}[/] [faint]· {s.density}[/]")
    rw = p.text.width(right)
    p.text.draw(p.surface, bar.right - p.ch * 2 - rw, bar.y, right, center_in=sh)
    left = f"yedekleme.py  [faint]{s.fields[0]} → {s.fields[1]}[/]"
    lx = bar.x + bw + p.ch * 2
    p.text.draw(p.surface, lx, bar.y, p.text.elide(left, bar.right - p.ch * 4 - rw - lx), center_in=sh)


def highlight(name: str, pos: list[int], inverse: bool = False) -> str:
    """Eşleşen harfleri vurgula; ters renkli satırda renk yerine altı çizili kalın."""
    hits, tag = set(pos), "bold u" if inverse else "bold accent"
    out = []
    for i, c in enumerate(name):
        c = "\\[" if c == "[" else c
        out.append(f"[{tag}]{c}[/]" if i in hits else c)
    return "".join(out)


def draw_palette(p: Painter, s: State) -> pygame.Rect:
    th = p.theme
    W, H = p.surface.get_size()
    veil = pygame.Surface((W, H), pygame.SRCALPHA)
    veil.fill((*th.bg, 175))
    p.surface.blit(veil, (0, 0))
    clickable(s, (0, 0, W, H), lambda: close_palette(s))  # dışarı tıklayınca kapan

    items = palette_items(s)
    s.pal_i = min(s.pal_i, max(0, len(items) - 1))
    n = max(1, len(items))
    pad = p.pad[1]
    pw = min(W - p.ch * 6, p.ch * 64)
    ph = pad * 2 + p.row * (n + 1) + p.row // 2 + 2
    box = pygame.Rect((W - pw) // 2, round(H * 0.17), pw, ph)
    p.shadow(box)
    p.frame(box, "Komutlar", focused=True, info="[faint]ctrl+p[/]",
            footer="[faint]↑↓ seç · ⏎ çalıştır · esc kapat[/]", fill=mix(th.bg, th.raised, 0.45))
    clickable(s, box, lambda: None)  # kutunun içine tıklamak paleti kapatmasın

    c = p.inset(box)
    y = c.y
    tx = c.x + p.write(c.x, y, "❯ ", Style(bold=True), th.accent)
    qw = p.write(tx, y, s.query) if s.query else 0
    p.surface.fill(th.accent, (tx + qw, y + (p.row - p.text.height) // 2, p.ch, p.text.height))
    if not s.query:
        p.write(tx + p.ch * 2, y, "komut ara…", color=th.faint)
    y += p.row + p.row // 4
    p.surface.fill(th.border, (box.x + 1, y, box.w - 2, 1))
    y += p.row // 4

    if not items:
        p.write(tx, y, "eşleşen komut yok", color=th.faint)
    for k, (_score, _n, name, key, action, pos) in enumerate(items):
        rr = pygame.Rect(c.x - p.ch, y, c.w + p.ch * 2, p.row)
        fg = None
        if k == s.pal_i:
            fg = p.selection(rr)
            if th.selection == "pointer":
                p.write(c.x, y, "❯", Style(bold=True), th.accent)
        elif hot(s, rr):
            p.hover(rr)
        p.write(tx, y, highlight(name, pos, inverse=fg is not None), color=fg or (th.text if k == s.pal_i else th.dim))
        if key and fg:  # ters renkli şeritte tuş kutusu şeridi bölmesin, düz yazı olsun
            p.write(c.right, y, key, color=fg, font=p.small, right=True)
        elif key:
            p.keycap(c.right, y, key, right=True)
        clickable(s, rr, lambda a=action: run_command(s, a))
        y += p.row
    return box


# ───────────────────────────── olaylar ─────────────────────────────

def handle(s: State, e: pygame.event.Event) -> None:
    if e.type == pygame.QUIT:
        s.quit = True
    elif e.type == pygame.MOUSEMOTION:
        s.mouse = e.pos
    elif e.type == pygame.WINDOWLEAVE:
        s.mouse = None
    elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
        for rect, action in reversed(s.hits):  # en son çizilen en üstte
            if rect.collidepoint(e.pos):
                action()
                break
    elif e.type == pygame.MOUSEWHEEL and s.focus == "files" and not s.palette:
        s.sel = max(0, min(len(visible(s.files)) - 1, s.sel - e.y))
    elif e.type == pygame.TEXTINPUT:
        if s.palette:
            s.query += e.text
            s.pal_i = 0
        elif s.focus == "form":
            s.fields[s.field_i] += e.text
            s.typed_at = s.t
    elif e.type == pygame.KEYDOWN:
        key(s, e)


def key(s: State, e: pygame.event.Event) -> None:
    k = e.key
    # AltGr, Windows'ta Ctrl+Alt olarak gelir: Türkçe klavyede AltGr+Q (@) "ctrl+q" sayılmasın
    ctrl = bool(e.mod & pygame.KMOD_CTRL) and not e.mod & pygame.KMOD_ALT
    shift = bool(e.mod & pygame.KMOD_SHIFT)
    enter = k in (pygame.K_RETURN, pygame.K_KP_ENTER)

    if ctrl and k == pygame.K_q:
        s.quit = True
    elif ctrl and k == pygame.K_p:
        s.palette, s.query, s.pal_i = not s.palette, "", 0
    elif k == pygame.K_F2:
        next_theme(s, -1 if shift else 1)
    elif k == pygame.K_F3:
        next_title(s, -1 if shift else 1)
    elif k == pygame.K_F4:
        next_density(s, -1 if shift else 1)
    elif k == pygame.K_F5:
        next_parts(s, -1 if shift else 1)
    elif ctrl and k == pygame.K_l:
        s.log.clear()
    elif s.palette:
        items = palette_items(s)
        if k == pygame.K_ESCAPE:
            close_palette(s)
        elif k in (pygame.K_DOWN, pygame.K_TAB):
            s.pal_i = (s.pal_i + 1) % max(1, len(items))
        elif k == pygame.K_UP:
            s.pal_i = (s.pal_i - 1) % max(1, len(items))
        elif enter and items:
            run_command(s, items[s.pal_i][4])
        elif k == pygame.K_BACKSPACE:
            s.query, s.pal_i = s.query[:-1], 0
    elif k == pygame.K_TAB:
        order = ["files", "form", "log"]
        s.focus = order[(order.index(s.focus) + (-1 if shift else 1)) % len(order)]
    elif k == pygame.K_ESCAPE:
        cancel(s)
    elif s.focus == "files":
        vis = visible(s.files)
        if k == pygame.K_DOWN:
            s.sel = min(len(vis) - 1, s.sel + 1)
        elif k == pygame.K_UP:
            s.sel = max(0, s.sel - 1)
        elif k in (pygame.K_RIGHT, pygame.K_LEFT) and vis[s.sel].is_dir:
            vis[s.sel].open = k == pygame.K_RIGHT
        elif enter:
            use_selected(s)
    elif s.focus == "form":
        if enter:
            start_or_pause(s)
        elif k in (pygame.K_UP, pygame.K_DOWN):
            s.field_i = 1 - s.field_i
        elif k == pygame.K_BACKSPACE:
            text = s.fields[s.field_i]
            if ctrl:  # kelime sil: son ayraca kadar
                stripped = text.rstrip("/\\ ")
                cut = max(stripped.rfind(c) for c in "/\\ ")
                s.fields[s.field_i] = stripped[:cut + 1]
            else:
                s.fields[s.field_i] = text[:-1]
            s.typed_at = s.t
    elif s.focus == "log" and enter:
        start_or_pause(s)


def update(s: State, dt: float) -> None:
    s.t += dt
    if phase(s) == "running":
        s.progress = min(1.0, s.progress + dt * RATE)
        s.next_event -= dt
        if s.next_event <= 0:
            add_log(s, *random.choice(EVENTS))
            s.next_event = random.uniform(0.9, 2.2)
        if s.progress >= 1:
            s.running = False
            add_log(s, "ok", f"🎉 yedekleme tamamlandı: [bold]{TOTAL}[/] dosya")
    s.next_cpu -= dt
    if s.next_cpu <= 0:
        s.next_cpu = 0.5
        last = s.cpu[-1] if s.cpu else 0.4
        target = 0.55 if phase(s) == "running" else 0.12
        s.cpu.append(min(0.97, max(0.04, last + (target - last) * 0.25 + random.uniform(-0.22, 0.22))))
        del s.cpu[:-64]


def seed_cpu(s: State) -> None:
    rnd = random.Random(3)
    v = 0.45
    for _ in range(64):
        v = min(0.97, max(0.06, v + (0.5 - v) * 0.2 + rnd.uniform(-0.22, 0.22)))
        s.cpu.append(v)


def dpi_scale() -> float:
    """Windows ekran ölçeği (%125 → 1.25). pygame.init()'ten sonra çağrılmalı."""
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes
        return ctypes.windll.user32.GetDpiForSystem() / 96
    except (AttributeError, OSError):
        return 1.0


def parse_sets(items: list[str]) -> dict:
    """['bar=segment', 'radius=4', 'panel_fill=true'] → {'bar': 'segment', 'radius': 4, …}"""
    out = {}
    for item in items:
        k, _, raw = item.partition("=")
        if raw.lower() in ("true", "false"):
            value = raw.lower() == "true"
        else:
            try:
                value = int(raw)
            except ValueError:
                try:
                    value = float(raw)
                except ValueError:
                    value = raw
        out[k.strip()] = value
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="termik vitrin prototipi")
    ap.add_argument("--shot", metavar="PNG", help="pencere açmadan ekran görüntüsü kaydet")
    ap.add_argument("--palette", action="store_true", help="komut paleti açık başlasın")
    ap.add_argument("--theme", default="okyanus", choices=NAMES)
    ap.add_argument("--look", default="terminal", choices=list(LOOKS), help="hazır biçim kümesi")
    ap.add_argument("--density", default="rahat", choices=list(DENSITIES), help="yoğunluk kümesi")
    ap.add_argument("--set", action="append", default=[], metavar="ANAHTAR=DEĞER",
                    help="tek bir biçim belirtecini ez, ör. bar=segment (tekrarlanabilir)")
    ap.add_argument("--font", metavar="TTF", help="birincil monospace font; yanındaki -Bold dosyası da kullanılır")
    ap.add_argument("--size", default="1240x780", help="pencere boyutu, ör. 1440x900")
    args = ap.parse_args(argv)

    if args.font:
        os.environ["TERMIK_FONT"] = args.font
    if args.shot:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    else:
        # ölçekli ekranlarda Windows pencereyi bulanık büyütmesin, gerçek pikselleri kullanalım
        os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")
    pygame.init()
    scale = 1.0 if args.shot else dpi_scale()
    w, h = (round(int(v) * scale) for v in args.size.lower().split("x"))
    screen = pygame.display.set_mode((w, h), 0 if args.shot else pygame.RESIZABLE)
    pygame.display.set_caption("termik · vitrin")

    overrides = parse_sets(args.set)
    s = State(theme_i=NAMES.index(args.theme), density=args.density, palette=args.palette,
              query="yed" if args.palette else "")
    seed_cpu(s)

    def make():
        """Durumdaki seçimlerden tema: biçim kümesi → yoğunluk → --set → F3/F5 seçimleri."""
        tokens = dict(overrides)
        if s.title:
            tokens["title"] = s.title
        if s.parts:
            tokens.update(PARTS[s.parts])
        return with_look(THEMES[NAMES[s.theme_i]], args.look, density=s.density, **tokens).scaled(scale)

    look = (s.theme_i, s.density, s.title, s.parts)
    p = Painter(screen, make(), default_font_paths())

    if args.shot:
        s.clock, s.blink, s.t = "14:32", True, 0.25
        render(p, s)
        pygame.image.save(screen, args.shot)
        print("kaydedildi:", args.shot)
        return

    clock = pygame.time.Clock()
    while not s.quit:
        dt = clock.tick(60) / 1000
        for e in pygame.event.get():
            handle(s, e)
        update(s, dt)
        if (s.theme_i, s.density, s.title, s.parts) != look:
            look = (s.theme_i, s.density, s.title, s.parts)
            p.set_theme(make())
        p.surface = pygame.display.get_surface()
        s.hits.clear()
        render(p, s)
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
