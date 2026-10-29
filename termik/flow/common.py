"""Akış API'sinin iki arka ucunun (pencere, terminal) ortak parçaları: ilerleme kaydı ve biçimleme."""

from __future__ import annotations

import time
import unicodedata
from typing import Any, Iterable

from ..markup import escape, plain_text

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
ICONS = {"ok": ("✓", "green"), "info": ("•", "blue"), "warn": ("⚠", "yellow"), "error": ("✗", "red")}
STATE_ICONS = {"ok": ("✓", "green"), "stopped": ("■", "yellow"), "error": ("✗", "red")}
LABEL_CAP = 26  # özet satırlarında cevap sütunu en fazla bu kadar karakter içeride başlar


# ── sayılar ve süreler ────────────────────────────────────

def number(n: float) -> str:
    """12400 → '12.400' (binlik ayırıcı nokta)."""
    return f"{int(n):,}".replace(",", ".")


def decimal(x: float) -> str:
    """4.13 → '4,1' (ondalık ayırıcı virgül)."""
    return f"{x:.1f}".replace(".", ",")


def duration(seconds: float) -> str:
    if seconds < 60:
        return f"{decimal(seconds)} sn"
    minutes, s = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes} dk {s:02d} sn"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} sa {minutes:02d} dk"


def size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} {unit}" if unit == "B" else f"{decimal(n)} {unit}"
        n /= 1024
    return ""


def amount(n: float, unit: str) -> str:
    """Miktar ve birim: '640 dosya'; unit="B" ise bayt boyutu: '1,2 MB'."""
    return size(n) if unit == "B" else f"{number(n)} {unit}".rstrip()


def counts(done: float, total: float | None, unit: str) -> str:
    """İlerleme sayacı: '412/640 dosya', '1,2 MB / 4,0 MB'."""
    if total is None:
        return amount(done, unit)
    if unit == "B":
        return f"{size(done)} / {size(total)}"
    return f"{number(done)}/{number(total)} {unit}".rstrip()


def display_width(text: str) -> int:
    """Eş genişlikli yazıda kapladığı hücre: geniş (Doğu Asya, emoji) karakterler iki hücre."""
    width = 0
    for ch in text:
        if unicodedata.combining(ch) or ch in "‍︎️":
            continue
        width += 2 if unicodedata.east_asian_width(ch) in "WF" else 1
    return width


# ── ilerleme ──────────────────────────────────────────────

class Progress:
    """track(), progress() ve spinner()'ın ilerleme kaydı.

    Script thread'i advance()/update() ile yazar; arayüz değerleri kendi hızında okur, yani
    döngünün her adımı bir mesaj göndermez. with bloğu bitince ya da finish() ile kapanır:

        with termik.progress("İndiriliyor", total=boyut, unit="B") as p:
            for parça in parçalar:
                p.advance(len(parça))
    """

    def __init__(self, session, label: str = "", *, total: float | None = None, unit: str = "öğe",
                 kind: str = "bar") -> None:
        self.label = label
        self.total = total
        self.unit = unit
        self.kind = kind             # bar · spinner
        self.done: float = 0
        self.text = ""               # değişen açıklama; etiketin yanında yazar
        self.state = "running"       # running · ok · stopped · error
        self.error = ""
        self.started = time.monotonic()
        self.ended: float | None = None
        self._view = session._io().live(self)

    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def elapsed(self) -> float:
        return (self.ended or time.monotonic()) - self.started

    @property
    def fraction(self) -> float | None:
        if not self.total:
            return None
        return min(1.0, max(0.0, self.done / self.total))

    @property
    def eta(self) -> float | None:
        """Kalan süre tahmini; ilk saniyede ve belirsiz ilerlemede None."""
        f = self.fraction
        if f is None or not 0 < f < 1 or self.elapsed < 1:
            return None
        return self.elapsed * (1 - f) / f

    def advance(self, n: float = 1) -> None:
        self.done += n

    def update(self, text: str | None = None, *, done: float | None = None, total: float | None = None,
               label: str | None = None) -> None:
        """Açıklamayı, sayacı, toplamı ya da etiketi değiştir: sp.update("12 MB alındı")."""
        if text is not None:
            self.text = text
        if done is not None:
            self.done = done
        if total is not None:
            self.total = total
        if label is not None:
            self.label = label

    def finish(self, state: str = "ok", error: BaseException | None = None) -> None:
        """Kapat: state ok, stopped ya da error. İkinci çağrı bir şey yapmaz."""
        if self.state != "running":
            return
        self.ended = time.monotonic()
        if error is not None:
            self.error = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
        self.state = state
        self._view.finish()

    def __enter__(self) -> Progress:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.finish("ok")
        elif issubclass(exc_type, (KeyboardInterrupt, GeneratorExit)):
            self.finish("stopped")
        else:
            self.finish("error", exc)
        return False

    def summary(self) -> str:
        """Bitince gösterilen özet (markup): '640 dosya · 4,1 sn', '412/640 dosya · 2,9 sn · durduruldu'."""
        parts = [self.text] if self.text else []
        if self.kind == "bar":
            whole = self.total is None or (self.state == "ok" and self.done >= self.total)
            parts.append(amount(self.done, self.unit) if whole else counts(self.done, self.total, self.unit))
        parts.append(duration(self.elapsed))
        if self.state == "stopped":
            parts.append("durduruldu")
        elif self.state == "error":
            parts.append(f"[red]{escape(self.error) or 'hata'}[/]")
        return " · ".join(parts)


# ── tablo ─────────────────────────────────────────────────

def _cell(value: Any) -> tuple[str, int]:
    markup = value if isinstance(value, str) else "" if value is None else escape(str(value))
    return markup, display_width(plain_text(markup))


def format_table(rows: Iterable, headers: Iterable | None = None) -> list[str]:
    """Satırları hizalı markup satırlarına çevir: başlık kalın, altında ince çizgi, sayılar sağa yaslı.

    rows dizi ya da sözlük olabilir; sözlüklerde başlıklar verilmezse anahtarlardan gelir.
    Yazı hücreleri markup'tır, diğer değerler olduğu gibi yazılır.
    """
    rows = list(rows)
    if rows and isinstance(rows[0], dict):
        if headers is None:
            headers = list(dict.fromkeys(key for row in rows for key in row))
        headers = list(headers)
        rows = [[row.get(h, "") for h in headers] for row in rows]
    rows = [list(row) for row in rows]
    head = [_cell(str(h)) for h in headers] if headers is not None else None
    columns = max((len(r) for r in rows + ([head] if head else [])), default=0)
    numeric = [bool(rows) and all(isinstance(r[i], (int, float)) and not isinstance(r[i], bool)
                                  for r in rows if i < len(r) and r[i] not in ("", None))
               for i in range(columns)]
    body = [[_cell(v) for v in row] for row in rows]
    widths = [0] * columns
    for cells in body + ([head] if head else []):
        for i, (_, w) in enumerate(cells):
            widths[i] = max(widths[i], w)

    def line(cells: list[tuple[str, int]], bold: bool = False) -> str:
        out = []
        for i in range(columns):
            markup, w = cells[i] if i < len(cells) else ("", 0)
            if bold and markup:
                markup = f"[bold]{markup}[/]"
            pad = " " * (widths[i] - w)
            out.append(pad + markup if numeric[i] else markup + pad)
        return "  ".join(out).rstrip()

    lines = []
    if head:
        lines.append(line(head, bold=True))
        lines.append("[faint]" + "  ".join("─" * w for w in widths) + "[/]")
    lines.extend(line(cells) for cells in body)
    return lines


class WidgetValue:
    """Pencerede form()'a verilen bileşenden okunan değer (terminaldeki cevaptan ayırt etmek için)."""

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value


def is_widget(value: Any) -> bool:
    """Bileşen katmanından bir bileşen mi (pygame'i içe aktarmadan)."""
    return hasattr(value, "bind_value") and hasattr(value, "compose")


def widget_lines(widget: Any) -> list[str]:
    """Terminalde gösterilecek hali: tablo hizalı satırlar, yazı kendisi, öbürleri kısa bir not."""
    from ..markup import plain_text

    text_lines = getattr(widget, "text_lines", None)  # grafik: ▁▃▇ bloklarıyla
    if callable(text_lines):
        return text_lines()
    columns, rows = getattr(widget, "columns", None), getattr(widget, "rows", None)
    if isinstance(columns, list) and isinstance(rows, list):
        headers = [plain_text(str(getattr(c, "label", c))) for c in columns]
        return format_table([[plain_text(str(cell)) for cell in cells] for cells, _ in rows], headers)
    text = getattr(widget, "text", None)
    if isinstance(text, str):
        return text.split("\n")
    return [f"[faint]({type(widget).__name__} pencerede gösterilir)[/]"]


class Shown:
    """show()'un döndürdüğü tutamak: bileşenin metotları çağrılıp öznitelikleri okunup yazılabilir;
    hepsi pencerenin kendi thread'inde yapılır, böylece script'ten güvenle güncellenir.

        tablo = termik.show(ui.Table("Dosya", "Boyut"))
        tablo.add_row("rapor.pdf", "1.2 MB")
    """

    __slots__ = ("_run", "widget")

    def __init__(self, run: Any, widget: Any) -> None:
        object.__setattr__(self, "_run", run)
        object.__setattr__(self, "widget", widget)

    def __getattr__(self, name: str) -> Any:
        value = self._run(getattr, self.widget, name)
        if callable(value) and not isinstance(value, type):
            return lambda *args, **kwargs: self._run(value, *args, **kwargs)
        return value

    def __setattr__(self, name: str, value: Any) -> None:
        self._run(setattr, self.widget, name, value)

    def __repr__(self) -> str:
        return f"<Shown {self.widget!r}>"
