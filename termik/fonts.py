"""Font bulma ve yedek zinciri.

Hiçbir font her glifi içermez: Consolas'ta braille ve ❯ yok, Cascadia'da ⚠ yok, ikisinde de
emoji yok. FontStack metni "bu karakteri hangi font çizebiliyor" sorusuna göre parçalara (run)
böler; her parça kendi fontuyla, ortak taban çizgisine (baseline) oturtularak çizilir.

Glif kapsamı pygame.freetype ile sorulur (eksik glifte None döner); çizim ise pygame.font
(SDL_ttf) ile yapılır, çünkü renkli emojiyi yalnızca o çizebiliyor.
"""

from __future__ import annotations

import os
import sys

import pygame
import pygame.freetype

# Pakete gömülü varsayılan font: JetBrains Mono'nun ligatürsüz (NL) kesimi, OFL lisanslı.
# Ligatürsüz, çünkü pygame-ce ligatürleri kapatamıyor; "=>" ve "!=" iki karakter kalmalı.
BUNDLED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "JetBrainsMonoNL-Regular.ttf")

# Gömülü font yoksa öncelik sırasıyla sistemde aranacak adaylar (küçük harfle karşılaştırılır)
MONO = (
    "JetBrainsMono-Regular.ttf", "CascadiaMono.ttf", "CascadiaMono-Regular.ttf", "CascadiaCode.ttf",
    "GeistMono-Regular.ttf", "FiraCode-Regular.ttf", "consola.ttf", "Menlo.ttc", "DejaVuSansMono.ttf",
)
SYMBOL = ("seguisym.ttf", "Apple Symbols.ttf", "NotoSansSymbols2-Regular.ttf", "DejaVuSans.ttf")
EMOJI = ("seguiemj.ttf", "Apple Color Emoji.ttc", "NotoColorEmoji.ttf")

# Kendinden önceki karakterle aynı fontta kalması gerekenler (❤️, 👩‍💻 gibi diziler)
_JOINERS = frozenset("\u200d\ufe0e\ufe0f")

# Yan yana g\u00f6r\u00fcnen akraba simgeler ayn\u0131 fonttan gelmeli; yoksa kal\u0131nl\u0131k ve boylar\u0131 tutmaz.
# Bir gruptaki karakter, grubun tamam\u0131n\u0131 \u00e7izebilen ilk fonttan al\u0131n\u0131r.
_GROUPS = ("\u2713\u2717\u26a0", "\u25cf\u25cb\u25c9", "\u25b8\u25be", "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f")
_GROUP_OF = {ch: g for g in _GROUPS for ch in g}


def _windows_terminal_dir() -> str | None:
    """Windows Terminal paketinin klasörü; içinde Cascadia Mono gelir.

    WindowsApps klasörü listelenemediği için yol kayıt defterinden okunur.
    """
    if sys.platform != "win32":
        return None
    import winreg

    key = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as packages:
            names = []
            i = 0
            while True:
                try:
                    names.append(winreg.EnumKey(packages, i))
                except OSError:
                    break
                i += 1
            for name in sorted(names, reverse=True):
                if name.startswith("Microsoft.WindowsTerminal_"):
                    with winreg.OpenKey(packages, name) as pkg:
                        return winreg.QueryValueEx(pkg, "PackageRootFolder")[0]
    except OSError:
        pass
    return None


def _font_dirs() -> list[str]:
    if sys.platform == "win32":
        dirs = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
        ]
        wt = _windows_terminal_dir()
        if wt:
            dirs.append(wt)
    elif sys.platform == "darwin":
        dirs = [os.path.expanduser("~/Library/Fonts"), "/Library/Fonts",
                "/System/Library/Fonts", "/System/Library/Fonts/Supplemental"]
    else:
        dirs = [os.path.expanduser("~/.local/share/fonts"), os.path.expanduser("~/.fonts"),
                "/usr/share/fonts", "/usr/local/share/fonts"]
    return [d for d in dirs if os.path.isdir(d)]


def _index_fonts() -> dict[str, str]:
    """{küçük harf dosya adı: tam yol} — ilk bulunan kazanır (kullanıcı fontları önce)."""
    index: dict[str, str] = {}
    for d in _font_dirs():
        for root, _dirs, files in os.walk(d):
            for f in files:
                index.setdefault(f.lower(), os.path.join(root, f))
    return index


def default_font_paths() -> list[str | None]:
    """[birincil monospace, sembol yedeği, emoji yedeği] — bulunabilenler.

    Birincil font sırasıyla: TERMIK_FONT ortam değişkeni, pakete gömülü font, sistemdeki
    adaylar. Hiçbiri yoksa pygame'in kendi fontu (None) kullanılır.
    """
    index = _index_fonts()

    def first(names: tuple[str, ...]) -> str | None:
        return next((index[n.lower()] for n in names if n.lower() in index), None)

    env = os.environ.get("TERMIK_FONT")
    if env and os.path.isfile(env):
        primary = env
    elif os.path.isfile(BUNDLED):
        primary = BUNDLED
    else:
        primary = first(MONO)
    paths: list[str | None] = [primary]
    for group in (SYMBOL, EMOJI):
        p = first(group)
        if p and p not in paths:
            paths.append(p)
    return paths


def bold_sibling(path: str | None) -> str | None:
    """Fontun ayrı kalın kesim dosyası: JetBrainsMono-Regular → -Bold, consola → consolab.

    TERMIK_FONT_BOLD ortam değişkeni bunu zorlar. Bulunamazsa None (kalınlık sentetik olur).
    """
    env = os.environ.get("TERMIK_FONT_BOLD")
    if env and os.path.isfile(env):
        return env
    if not path:
        return None
    folder, filename = os.path.split(path)
    name, ext = os.path.splitext(filename)
    names = [name.replace(a, b) for a, b in (("-Regular", "-Bold"), ("Regular", "Bold")) if a in name]
    names += [name + "-Bold", name + "b"]
    for n in names:
        p = os.path.join(folder, n + ext)
        if p != path and os.path.isfile(p):
            return p
    return None


class FontStack:
    """Birincil font + yedekleri, tek bir piksel boyutunda."""

    def __init__(self, paths: list[str | None], size: int):
        if not pygame.freetype.get_init():
            pygame.freetype.init()
        self.paths = paths
        self.size = size
        self.bold_path = bold_sibling(paths[0])
        self._fonts: dict[tuple[int, bool, bool], pygame.font.Font] = {}
        self._probes = [pygame.freetype.Font(p, size) for p in paths]
        self._index: dict[str, int] = {}
        self._primary: set[str] = set()  # birincil fonttan çizildiği bilinen karakterler
        # sembol fontları bazı emojilerin tek renkli kopyasını taşır; resimli emoji renkli fonttan gelsin
        self._emoji = next((n for n, p in enumerate(paths)
                            if p and any(m in os.path.basename(p).lower() for m in ("emoji", "seguiemj"))), None)
        primary = self.font(0)
        self.ascent: int = primary.get_ascent()
        self.descent: int = -primary.get_descent()
        self.height: int = self.ascent + self.descent
        self.ch: int = primary.size("M")[0]  # monospace karakter genişliği
        self._advance: dict[tuple[bool, bool], int | None] = {}

    def _mono(self, bold: bool, italic: bool) -> int | None:
        """Birincil font bu kesimde eş genişlikliyse harf genişliği, değilse None (bir kez ölçülür)."""
        key = (bold, italic)
        if key not in self._advance:
            f = self.font(0, bold, italic)
            w = f.size("M")[0]
            same = all(f.size(s)[0] == w * len(s) for s in ("i", "W", ".", "MiW.Ty", "rnmw ıİşĞ"))
            self._advance[key] = w if same else None
        return self._advance[key]

    def width(self, text: str, bold: bool = False, italic: bool = False) -> int:
        """Yazının piksel genişliği. Birincil font eş genişlikliyse ve bütün harfler ondan
        çiziliyorsa çarpmayla hesaplanır; satır kaydırma bunu kelime kelime çok kez sorar."""
        advance = self._mono(bold, italic)
        if advance is not None and self._primary.issuperset(text):
            return advance * len(text)
        return sum(self.font(i, bold, italic).size(run)[0] for i, run in self.runs(text))

    def font(self, i: int = 0, bold: bool = False, italic: bool = False) -> pygame.font.Font:
        key = (i, bold, italic)
        f = self._fonts.get(key)
        if f is None:
            if bold and i == 0 and self.bold_path:
                f = pygame.font.Font(self.bold_path, self.size)  # gerçek kalın kesim
            else:
                f = pygame.font.Font(self.paths[i], self.size)
                f.bold = bold  # sentetik kalınlık
            f.italic = italic
            self._fonts[key] = f
        return f

    def _covers(self, n: int, chars: str) -> bool:
        return all(m is not None for m in self._probes[n].get_metrics(chars))

    def index_for(self, ch: str) -> int:
        """Bu karakteri (ya da grubunun tamamını) çizebilen ilk fontun sırası; yoksa birincil (0)."""
        i = self._index.get(ch)
        if i is None and self._emoji is not None and ord(ch) >= 0x1F000 and self._covers(self._emoji, ch):
            i = self._index[ch] = self._emoji
        if i is None:
            need = _GROUP_OF.get(ch, ch)
            i = next((n for n in range(len(self._probes)) if self._covers(n, need)), None)
            if i is None:  # grubu tek başına kapsayan yok: karakter karakter düş
                i = next((n for n in range(len(self._probes)) if self._covers(n, ch)), 0)
            self._index[ch] = i
            if i == 0 and ch not in _JOINERS:
                self._primary.add(ch)
        return i

    def runs(self, text: str) -> list[tuple[int, str]]:
        """Metni aynı fontla çizilecek ardışık parçalara böl: [(font sırası, parça), …]."""
        out: list[tuple[int, str]] = []
        for ch in text:
            i = out[-1][0] if ch in _JOINERS and out else self.index_for(ch)
            if out and out[-1][0] == i:
                out[-1] = (i, out[-1][1] + ch)
            else:
                out.append((i, ch))
        return out
