"""Akış API'sinin terminal arka ucu: pencere açılamadığında (SSH, CI, pygame yok) ya da
TERMIK_MODE=terminal ile.

Markup ANSI renklerine çevrilir, sorular satır satır sorulur. Etkileşimli bir terminalde
ilerleme ve spinner satırları yerinde güncellenir, cevaplanan soru tek satırlık özete döner.
Çıktı dosyaya ya da boruya gidiyorsa renk ve imleç hareketi kullanılmaz; ilerlemeler yalnızca
sonuç satırı olarak yazılır.
"""

from __future__ import annotations

import atexit
import getpass
import os
import shutil
import sys
import threading
import time

from ..fuzzy import fold, match
from ..markup import Span, escape, parse_markup, plain_text
from ..theme import THEMES, Color, Theme
from .common import LABEL_CAP, SPINNER, STATE_ICONS, amount, counts, display_width, duration


# ── ANSI ──────────────────────────────────────────────────

def to_ansi(markup: str | list[Span], theme: Theme, color: str | None) -> str:
    """Markup'ı ANSI kaçışlı yazıya çevir. color: None (renksiz), "256" ya da "truecolor"."""
    spans = parse_markup(markup, theme) if isinstance(markup, str) else markup
    if color is None:
        return "".join(text for text, _ in spans)
    out = []
    for text, st in spans:
        codes = [code for on, code in ((st.bold, "1"), (st.dim, "2"), (st.italic, "3"),
                                       (st.underline, "4"), (st.strike, "9")) if on]
        if st.fg:
            codes.append(_sgr(38, st.fg, color))
        if st.bg:
            codes.append(_sgr(48, st.bg, color))
        out.append(f"\x1b[{';'.join(codes)}m{text}\x1b[0m" if codes else text)
    return "".join(out)


def _sgr(base: int, rgb: Color, color: str) -> str:
    r, g, b = rgb
    if color == "truecolor":
        return f"{base};2;{r};{g};{b}"
    return f"{base};5;{_xterm256(r, g, b)}"


def _xterm256(r: int, g: int, b: int) -> int:
    """En yakın xterm-256 rengi: gri tonlar 232–255 rampasından, diğerleri 6×6×6 küpten."""
    if abs(r - g) < 12 and abs(g - b) < 12:
        gray = (r + g + b) / 3
        if gray < 8:
            return 16
        if gray > 238:
            return 231
        return 232 + round((gray - 8) / 247 * 23)

    def level(v: int) -> int:
        return 0 if v < 48 else 1 if v < 115 else (v - 35) // 40

    return 16 + 36 * level(r) + 6 * level(g) + level(b)


def _isatty(stream) -> bool:
    try:
        return stream is not None and stream.isatty()
    except (AttributeError, OSError, ValueError):
        return False


def _enable_vt(stream) -> bool:
    """Windows konsolunda ANSI kaçışlarını aç (Windows 10 ve sonrası)."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        import msvcrt
        handle = msvcrt.get_osfhandle(stream.fileno())
        kernel32 = ctypes.windll.kernel32
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(mode.value & 4 or kernel32.SetConsoleMode(handle, mode.value | 4))
    except (AttributeError, OSError, ValueError):
        return False


def _color_mode(stream) -> str | None:
    if os.environ.get("NO_COLOR"):
        return None
    forced = bool(os.environ.get("FORCE_COLOR"))
    if not forced and (not _isatty(stream) or os.environ.get("TERM") == "dumb"):
        return None
    if sys.platform == "win32":
        return "truecolor" if _enable_vt(stream) or forced else None
    return "truecolor" if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") else "256"


def _rows(text: str, cols: int) -> int:
    """Yazının terminalde kapladığı satır sayısı (uzun satırlar kayar)."""
    return max(1, -(-display_width(text) // max(1, cols)))


def _clip(spans: list[Span], width: int) -> list[Span]:
    """Satırı width hücreye sığdır; taşan kısım '…' olur."""
    if display_width("".join(text for text, _ in spans)) <= width:
        return spans
    out: list[Span] = []
    used = 0
    for text, st in spans:
        kept = ""
        for ch in text:
            w = display_width(ch)
            if used + w > width - 1:
                out.append((kept + "…", st))
                return out
            kept += ch
            used += w
        out.append((kept, st))
    return out


def _frame() -> str:
    return SPINNER[int(time.monotonic() * 10) % len(SPINNER)]


# ── arka uç ───────────────────────────────────────────────

class TerminalBackend:
    """Terminale yazar, terminalden okur. En alttaki "canlı" satırlar (ilerlemeler) normal
    çıktıdan önce silinip sonra yeniden çizilir; böylece çıktı onların üstüne akar."""

    kind = "terminal"

    def __init__(self, session) -> None:
        self.session = session
        self.theme = THEMES.get(session.theme or "", THEMES["okyanus"])
        self.color = _color_mode(sys.stdout)
        self.fancy = self.color is not None and _isatty(sys.stdout)  # imleç hareketi serbest
        self.label_chars = 0
        self._lock = threading.RLock()
        self._live: list = []
        self._drawn = 0           # çizili canlı satır sayısı
        self._open_line = False   # son yazı satır sonuyla bitmedi
        self._paused = False      # soru sorulurken canlı satırlar çizilmez
        self._ticker: threading.Thread | None = None
        atexit.register(self._at_exit)

    def _ansi(self, markup: str) -> str:
        return to_ansi(markup, self.theme, self.color)

    @staticmethod
    def _cols() -> int:
        return shutil.get_terminal_size((80, 24)).columns

    @staticmethod
    def _put(text: str) -> None:
        out = sys.stdout
        if out is None or not text:
            return
        try:
            try:
                out.write(text)
            except UnicodeEncodeError:  # konsol kod sayfası simgeleri yazamıyor
                encoding = getattr(out, "encoding", None) or "ascii"
                out.write(text.encode(encoding, "replace").decode(encoding))
            out.flush()
        except (OSError, ValueError):
            pass

    # ── canlı satırlar ───────────────────────────────────

    def _clear(self) -> str:
        if not self._drawn:
            return ""
        self._drawn = 0
        return "\r\x1b[J"  # imleç canlı alanın başında: oradan sona kadar sil

    def _live_area(self) -> str:
        if not self.fancy or self._paused or self._open_line:
            return ""
        running = [p for p in self._live if p.running]
        if not running:
            return ""
        width = self._cols() - 1
        lines = [self._live_line(p, width) for p in running]
        self._drawn = len(lines)
        up = f"\x1b[{len(lines) - 1}A" if len(lines) > 1 else ""
        return "\n".join(lines) + "\r" + up  # imleç alanın başına döner

    def _live_line(self, prog, width: int) -> str:
        head = f"[accent]{_frame()}[/] {prog.label}"
        frac = prog.fraction
        if prog.kind == "bar" and frac is not None:
            tail = f"  [bold]{round(frac * 100):>3}%[/]  [dim]{counts(prog.done, prog.total, prog.unit)}[/]"
            if prog.eta is not None:
                tail += f" [faint]· ~{duration(prog.eta)}[/]"
            cells = min(30, width - display_width(plain_text(head + tail)) - 2)
            bar = ""
            if cells >= 6:
                k = round(frac * cells)
                bar = f"  [accent]{'█' * k}[/][faint]{'░' * (cells - k)}[/]"
            markup = head + bar + tail
        else:
            parts = [prog.text] if prog.text else []
            if prog.kind == "bar":
                parts.append(amount(prog.done, prog.unit))
            parts.append(duration(prog.elapsed))
            markup = head + "  [faint]" + " · ".join(parts) + "[/]"
        return to_ansi(_clip(parse_markup(markup, self.theme), width), self.theme, self.color)

    def _tick(self) -> None:
        while True:
            time.sleep(0.1)
            with self._lock:
                if not any(p.running for p in self._live):
                    self._ticker = None
                    return
                if not self._paused and not self._open_line:
                    self._put(self._clear() + self._live_area())

    def _note_label(self, label: str) -> None:
        width = display_width(plain_text(label)) + 2
        if self.label_chars < width <= LABEL_CAP:
            self.label_chars = width

    def _labeled(self, label: str, text: str) -> str:
        pad = max(2, self.label_chars - display_width(plain_text(label)))
        return f"[dim]{label}[/]{' ' * pad}{text}"

    # ── akış API'sinin istekleri ─────────────────────────

    def write(self, markup: str) -> None:
        with self._lock:
            text = self._clear() + self._ansi(markup)
            if markup:
                self._open_line = not markup.endswith("\n")
            self._put(text + self._live_area())

    def rule(self, title: str) -> None:
        width = self._cols() - 1
        if title:
            rest = max(0, width - display_width(plain_text(f"── {title} ")))
            self.write(f"[faint]──[/] [bold]{title}[/] [faint]{'─' * rest}[/]\n")
        else:
            self.write(f"[faint]{'─' * width}[/]\n")

    def table(self, lines: list[str]) -> None:
        self.write("".join(line + "\n" for line in lines))

    def prompt(self, what: str, label: str, **spec) -> _TermPrompt:
        return _TermPrompt(self, what, label, spec)

    def live(self, progress) -> _TermLive:
        with self._lock:
            self._live.append(progress)
            if self.fancy and self._ticker is None:
                self._ticker = threading.Thread(target=self._tick, name="termik-terminal", daemon=True)
                self._ticker.start()
        return _TermLive(self, progress)

    def _finish(self, prog) -> None:
        with self._lock:
            if prog in self._live:
                self._live.remove(prog)
            self._note_label(prog.label)
            icon, color = STATE_ICONS[prog.state]
            lead = "\n" if self._open_line else ""
            self._open_line = False
            line = f"[{color}]{icon}[/] {self._labeled(prog.label, prog.summary())}\n"
            self._put(self._clear() + lead + self._ansi(line) + self._live_area())

    def close(self) -> None:
        """Terminalde kapatılacak pencere yok."""

    def _at_exit(self) -> None:
        for prog in list(self._live):
            prog.finish("stopped")
        with self._lock:
            self._put(self._clear())


class _TermLive:
    def __init__(self, backend: TerminalBackend, progress) -> None:
        self.backend, self.progress = backend, progress

    def finish(self) -> None:
        self.backend._finish(self.progress)


class _TermPrompt:
    """Terminalde bir soru. wait() cevabı okur (biçimsiz girişte yeniden sorar), reject() hatayı
    yazar, accept() soruyu tek satırlık özete çevirir."""

    def __init__(self, backend: TerminalBackend, kind: str, label: str, spec: dict) -> None:
        self.b = backend
        self.kind = kind
        self.label = label
        self.spec = spec
        self.lines = 0  # sorunun kapladığı satırlar; özete çevirirken silinir
        self._shown = False

    def _header(self) -> list[str]:
        if self.kind not in ("choose", "many"):
            return []
        options = self.spec["options"]
        width = len(str(len(options)))
        if self.kind == "choose":
            lines = [f"[accent]?[/] [bold]{self.label}[/]"]
            current = self.spec.get("index", 0)
            for n, name in enumerate(options):
                mark = "[accent]❯[/]" if n == current else " "
                lines.append(f"  {mark} [dim]{n + 1:>{width}})[/] {escape(name)}")
            return lines
        selected = set(self.spec.get("selected", ()))
        lines = [f"[accent]?[/] [bold]{self.label}[/]  [faint](numaralar: 1,3 · 2-4 · * hepsi)[/]"]
        for n, name in enumerate(options):
            mark = "[green]✓[/]" if n in selected else " "
            lines.append(f"  [faint]\\[[/]{mark}[faint]][/] [dim]{n + 1:>{width}})[/] {escape(name)}")
        return lines

    def _prompt(self) -> str:
        if self.kind in ("choose", "many"):
            return "  [faint]›[/] "
        head = f"[accent]?[/] [bold]{self.label}[/]"
        if self.kind == "confirm":
            yes, no = self.spec["yes"][:1], self.spec["no"][:1]
            hint = f"{yes.upper()}/{no.lower()}" if self.spec["default"] else f"{yes.lower()}/{no.upper()}"
            return f"{head} [faint]({hint}) ›[/] "
        value = self.spec.get("value")
        return f"{head}{f' [faint]({escape(value)})[/]' if value else ''} [faint]›[/] "

    def wait(self):
        b = self.b
        with b._lock:
            b._paused = True
            text = b._clear()
            if b._open_line:
                text += "\n"
                b._open_line = False
            if not self._shown:
                self._shown = True
                for line in self._header():
                    text += b._ansi(line) + "\n"
                    self.lines += _rows(plain_text(line), b._cols())
            b._put(text)
        try:
            while True:
                raw = self._read(self._prompt())
                try:
                    return self._parse(raw)
                except ValueError as exc:
                    self.reject(str(exc))
        except BaseException:
            b._paused = False
            raise

    def _read(self, prompt: str) -> str:
        b = self.b
        b._put(b._ansi(prompt))
        secret = bool(self.spec.get("password")) and _isatty(sys.stdin)
        try:
            raw = getpass.getpass("") if secret else input()
        except EOFError:
            raise EOFError(f"termik: '{plain_text(self.label)}' sorusu cevaplanamadı, girdi yok") from None
        if not _isatty(sys.stdin):  # boru ya da dosyadan gelen cevap ekranda da görünsün
            b._put(("•" * 6 if self.spec.get("password") else raw) + "\n")
        self.lines += _rows(plain_text(prompt) + ("" if secret else raw), b._cols())
        return raw

    def _parse(self, raw: str):
        kind, spec = self.kind, self.spec
        text = raw.strip()
        if kind in ("ask", "path"):
            return raw
        if kind == "confirm":
            if not text:
                return spec["default"]
            word, yes, no = fold(text), fold(spec["yes"]), fold(spec["no"])
            if word in (yes, "e", "evet", "y", "yes"):
                return True
            if word in (no, "h", "hayir", "n", "no"):
                return False
            if yes[:1] != no[:1] and word in (yes[:1], no[:1]):
                return word == yes[:1]
            raise ValueError(f"{yes[:1]} ya da {no[:1]} yazın")
        options = spec["options"]
        if kind == "choose":
            if not text:
                return spec.get("index", 0)
            return self._pick(text, options)
        if not text:
            return sorted(spec.get("selected", ()))
        if fold(text) in ("*", "hepsi", "tumu", "all"):
            return list(range(len(options)))
        picked: set[int] = set()
        for token in text.replace(",", " ").split():
            first, dash, last = token.partition("-")
            if dash and first.isdigit() and last.isdigit():
                a, z = self._number(first, options), self._number(last, options)
                picked.update(range(min(a, z), max(a, z) + 1))
            else:
                picked.add(self._pick(token, options))
        return sorted(picked)

    @staticmethod
    def _number(text: str, options: list[str]) -> int:
        n = int(text)
        if not 1 <= n <= len(options):
            raise ValueError(f"1 ile {len(options)} arasında bir numara girin")
        return n - 1

    @classmethod
    def _pick(cls, text: str, options: list[str]) -> int:
        """Numara ya da yazıyla seçenek bul: tam eşleşme, sonra tek başlangıç, sonra tek bulanık eşleşme."""
        if text.isdigit():
            return cls._number(text, options)
        key = fold(text)
        for candidates in ([i for i, o in enumerate(options) if fold(o) == key],
                           [i for i, o in enumerate(options) if fold(o).startswith(key)],
                           [i for i, o in enumerate(options) if match(text, o) is not None]):
            if len(candidates) == 1 or (candidates and fold(options[candidates[0]]) == key):
                return candidates[0]
            if len(candidates) > 1:
                raise ValueError(f"{len(candidates)} seçenek eşleşti, numarasını yazın")
        raise ValueError(f"eşleşen seçenek yok: {text}")

    def reject(self, message: str) -> None:
        b = self.b
        line = f"  [red]✗ {escape(message)}[/]"
        b._put(b._ansi(line) + "\n")
        self.lines += _rows(plain_text(line), b._cols())

    def accept(self, summary: str) -> None:
        b = self.b
        with b._lock:
            b._note_label(self.label)
            line = b._ansi(f"[green]✓[/] {b._labeled(self.label, summary)}") + "\n"
            if b.fancy and self.lines:
                b._put(f"\x1b[{self.lines}F\x1b[J" + line)  # soruyu ve cevabı sil, yerine özet
            elif self.kind in ("choose", "many"):  # numarayla cevaplandı: neyin seçildiği de yazsın
                b._put(line)
            b._paused = False
            b._put(b._live_area())
