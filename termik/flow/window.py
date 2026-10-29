"""Akış API'sinin pencere arka ucu: ayrı thread'de dönen döküm penceresi.

Script thread'i işleri bir kuyruğa koyar, pencere thread'i onları kendi döngüsünde sırayla
uygular. İlerleme değerleri kuyruğa girmez, pencere onları her karede doğrudan okur; böylece
döngünün her adımı bir mesaj göndermez. Sorular concurrent.futures.Future ile beklenir.

Pencere kapanınca bekleyen soru KeyboardInterrupt fırlatır; script o an kendi işindeyse ana
thread'e SIGINT gönderilir, terminalde Ctrl+C'ye basılmış gibi.
"""

from __future__ import annotations

import asyncio
import atexit
import functools
import os
import signal
import sys
import threading
import time
import traceback
import weakref
from concurrent.futures import Future
from typing import Any, Callable

import pygame

from .. import clipboard, filedialog
from ..app import App
from ..events import Click, Drop, Key, MouseDown, MouseMove
from ..markup import Span, escape, plain_text
from ..widget import Widget, action
from ..widgets import Button, Checkbox, Input, OptionList, RadioSet, ScrollView
from . import capture
from .common import LABEL_CAP, SPINNER, STATE_ICONS, Progress, amount, counts, display_width, duration

MAX_LINES = 2000  # dökümde tutulan en çok çıktı satırı; eskiler atılır


def _keys(*pairs: tuple[str, str]) -> str:
    """İpucu satırı: _keys(("⏎", "onayla"), ("tab", "tamamla")) → '⏎ onayla · tab tamamla'."""
    return "  [faint]·[/]  ".join(f"[dim]{escape(key)}[/] [faint]{text}[/]" for key, text in pairs)


def _frame() -> str:
    return SPINNER[int(time.monotonic() * 10) % len(SPINNER)]


# ── döküm ve girdileri ────────────────────────────────────

class Transcript(ScrollView):
    """Döküm: girdiler alt alta. Yeni girdi gelince en alta kayar; kullanıcı yukarı
    kaydırdıysa yerinde durur, en alta inince takip sürer."""

    def __init__(self) -> None:
        super().__init__(id="transcript")
        self.follow = True

    def scroll_to(self, y: float) -> None:
        super().scroll_to(y)
        self.follow = self.scroll_y >= self.max_scroll

    def _reveal(self, widget: Widget) -> None:
        if widget.region.h:  # henüz yerleşmediyse bir şey yapma; yeni soru zaten en alta kaydırır
            super()._reveal(widget)

    def arrange(self, p) -> None:
        if self.follow:
            self.scroll_y = 1 << 30  # aşağıda en alta sıkıştırılır
        kids = [c for c in self.children if c.display]
        box = self.content
        # çubuğa yer hep ayrılır: içerik uzayınca bütün satırlar yeni genişlikte yeniden kaydırılmasın
        self._bar = p.ch
        width = box.w - self._bar
        gap = self._gap_px(p)
        heights = self._heights(p, kids, width)
        self._virtual = sum(heights) + gap * max(0, len(kids) - 1)
        self.scroll_y = max(0, min(self.scroll_y, self.max_scroll))
        y = box.y - self.scroll_y
        for c, h in zip(kids, heights):
            c._layout(p, pygame.Rect(box.x, y, self._child_width(c, p, width), h))
            y += h + gap


class OutputBlock(Widget):
    """print() çıktısı: markup satırları. Satırlar genişliğe göre kaydırılır, tablo satırları kırpılır.

    Kaydırılmış görsel satırlar önbellekte tutulur; yeni satır gelince yalnızca o kaydırılır.
    Çizimde yalnızca görünen satırlar basılır.
    """

    default_height = "auto"

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[list[str]] = []  # her satır: ayrı ayrı ayrıştırılan markup parçaları
        self.wraps: list[bool] = []
        self.open = False                 # son satır "\n" ile bitmedi: sonraki yazı ona eklenir
        self._rows: list[list[Span]] = []
        self._counts: list[int] = []      # her satırın kaç görsel satıra kaydırıldığı
        self._cache_width = -1  # önbelleğin geçerli olduğu genişlik ve tema
        self._cache_theme = None

    def add(self, text: str, wrap: bool = True) -> None:
        parts = text.split("\n")
        tail_open = parts[-1] != ""
        if not tail_open:
            parts.pop()
        for i, part in enumerate(parts):
            reset = "\r" in part  # satır başına dönüş: ardından gelen yazı satırın yerine geçer (tqdm gibi)
            part = part.rsplit("\r", 1)[-1]
            if i == 0 and self.open and self.lines:
                if reset:
                    self.lines[-1] = [part]
                else:
                    self.lines[-1].append(part)
                if len(self._counts) == len(self.lines):  # son satır yeniden kaydırılsın
                    del self._rows[len(self._rows) - self._counts.pop():]
            else:
                self.lines.append([part])
                self.wraps.append(wrap)
        if parts:
            self.open = tail_open
        self.refresh(layout=True)

    def drop(self, n: int) -> int:
        """En eski n satırı at; atılan satır sayısını döndür."""
        n = min(n, len(self.lines))
        if n <= 0:
            return 0
        if len(self._counts) >= n:
            del self._rows[:sum(self._counts[:n])]
            del self._counts[:n]
        else:
            self._rows, self._counts = [], []
        del self.lines[:n]
        del self.wraps[:n]
        if not self.lines:
            self.open = False
        self.refresh(layout=True)
        return n

    def _sync(self, p, width: int) -> None:
        if width != self._cache_width or p.theme is not self._cache_theme:
            self._rows, self._counts = [], []
            self._cache_width, self._cache_theme = width, p.theme
        for i in range(len(self._counts), len(self.lines)):
            spans = [span for part in self.lines[i] for span in p.text.spans(part)]
            rows = p.text.wrap(spans, max(p.ch, width)) if self.wraps[i] else [p.text.elide(spans, width)]
            self._rows.extend(rows)
            self._counts.append(len(rows))

    def measure(self, p, width: int) -> tuple[int, int]:
        self._sync(p, width)
        return width, len(self._rows) * p.row

    def render(self, p) -> None:
        c = self.content
        self._sync(p, c.w)
        clip = p.surface.get_clip()
        first = max(0, (clip.top - c.y) // p.row)
        last = min(len(self._rows), (clip.bottom - c.y) // p.row + 1)
        for i in range(first, last):
            p.write(c.x, c.y + i * p.row, self._rows[i])

    def plain(self) -> str:
        return "\n".join("".join(plain_text(part) for part in line) for line in self.lines)


class RuleLine(Widget):
    """Ayraç: ── Başlık ──────────"""

    default_height = "auto"

    def __init__(self, title: str = "") -> None:
        super().__init__(padding=(0.5, 0, 0.25, 0))
        self.title = title

    def measure(self, p, width: int) -> tuple[int, int]:
        return width, p.row

    def render(self, p) -> None:
        c = self.content
        x = c.x
        if self.title:
            x += p.write(x, c.y, f"[faint]──[/] [bold]{self.title}[/] ")
        p.write(x, c.y, "─" * max(0, (c.right - x) // p.ch), color=p.theme.faint)

    def plain(self) -> str:
        return f"── {plain_text(self.title)} ──" if self.title else "─" * 40


class LiveEntry(Widget):
    """track(), progress() ve spinner() satırı: çalışırken dönen işaret, çubuk ve sayaç; bitince özet."""

    default_height = "auto"

    def __init__(self, progress: Progress) -> None:
        super().__init__()
        self.progress = progress  # script thread'i yazar, burada yalnızca okunur
        self._timer = None

    def on_mount(self) -> None:
        if self.progress.running:
            self._timer = self.set_interval(0.1, self.refresh)

    def finish(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.app.note_label(self.progress.label)
        self.refresh()

    def measure(self, p, width: int) -> tuple[int, int]:
        return width, p.row

    def render(self, p) -> None:
        th = p.theme
        c = self.content
        prog = self.progress
        lx = c.x + p.ch * 2
        x = self.app.answer_x(p, lx, prog.label)
        if not prog.running:
            icon, color = STATE_ICONS[prog.state]
            p.write(c.x, c.y, f"[{color}]{icon}[/]")
            p.write(lx, c.y, f"[dim]{prog.label}[/]")
            p.write(x, c.y, p.text.elide(prog.summary(), c.right - x))
            return
        p.write(c.x, c.y, _frame(), color=th.accent)
        p.write(lx, c.y, prog.label)
        frac = prog.fraction
        if prog.kind == "bar" and frac is not None:
            stats = f"[bold]{round(frac * 100):>3}%[/]  [dim]{counts(prog.done, prog.total, prog.unit)}[/]"
            if prog.eta is not None:
                stats += f" [faint]· ~{duration(prog.eta)}[/]"
            room = c.right - x - p.text.width(stats) - p.ch * 2
            bar = min(p.ch * 40, room) // p.ch * p.ch
            if bar >= p.ch * 8:
                p.bar(x, c.y, bar, frac)
                x += bar + p.ch * 2
            p.write(x, c.y, p.text.elide(stats, c.right - x))
            return
        parts = [prog.text] if prog.text else []
        if prog.kind == "bar":
            parts.append(f"[dim]{amount(prog.done, prog.unit)}[/]")
        parts.append(f"[faint]{duration(prog.elapsed)}[/]")
        p.write(x, c.y, p.text.elide(" [faint]·[/] ".join(parts), c.right - x))

    def plain(self) -> str:
        prog = self.progress
        icon = STATE_ICONS[prog.state][0] if not prog.running else _frame()
        return f"{icon} {plain_text(prog.label)}  {plain_text(prog.summary())}"


# ── sorular ───────────────────────────────────────────────

class PromptEntry(Widget):
    """Dökümdeki soru. Etkinken solda vurgu çubuğu, başlık, gövde ve ipucu satırı; cevaplanınca
    tek satırlık özete döner ve gövdesi kaldırılır.

    Cevap script thread'ine bir Future ile gider. Script doğrularsa accept(özet), doğrulamazsa
    reject(hata, yeni Future) gelir ve soru yeniden dinler.
    """

    default_height = "auto"

    def __init__(self, label: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.summary: str | None = None
        self.error = ""
        self._future: Future | None = None

    @property
    def body(self) -> Widget | None:
        """Soru etkinken odağı alan bileşen."""
        return None

    @property
    def answered(self) -> bool:
        return self.summary is not None

    @property
    def listening(self) -> bool:
        return self._future is not None

    def hints(self) -> str:
        return _keys(("⏎", "onayla"))

    def badge(self) -> str:
        """Başlığın sağındaki küçük bilgi (süzgeç, seçim sayısı)."""
        return ""

    def extra_rows(self) -> int:
        """Gövdeyle ipucu satırı arasındaki ek satırlar (yol adayları gibi)."""
        return 0

    # ── script ile alışveriş ─────────────────────────────

    def listen(self, future: Future) -> None:
        self._future = future
        self.refresh()

    def answer(self, value: Any) -> None:
        """Kullanıcı cevapladı: script'e ilet. Doğrulanınca accept, olmazsa reject gelir."""
        future, self._future = self._future, None
        if future is not None and not future.done():
            future.set_result(value)
        self.refresh()

    def reject(self, message: str, future: Future) -> None:
        self.error = message
        self.listen(future)
        self.refresh(layout=True)

    def accept(self, summary: str) -> None:
        self.summary = summary
        self.error = ""
        self._future = None
        self.remove_children()
        self.app.prompt_done(self)
        self.refresh(layout=True)

    # ── yerleşim ve çizim ────────────────────────────────

    def chrome(self, p) -> tuple[int, int, int, int]:
        if self.answered:
            return 0, 0, 0, 0
        return round(p.row * 1.5), 0, p.row * (1 + self.extra_rows()), p.ch * 2

    def measure(self, p, width: int) -> tuple[int, int]:
        if self.answered:
            return width, p.row
        return super().measure(p, width)

    def render(self, p) -> None:
        th = p.theme
        r, c = self.region, self.content
        if self.answered:
            p.write(r.x, r.y, "[green]✓[/]")
            x = r.x + p.ch * 2
            p.write(x, r.y, f"[dim]{self.label}[/]")
            ax = self.app.answer_x(p, x, self.label)
            p.write(ax, r.y, p.text.elide(self.summary, r.right - ax))
            return
        top = r.y + p.row // 2
        p.surface.fill(th.red if self.error else th.accent, (r.x, top + 3, 2, c.bottom - top - 6))
        title = f"[bold]{self.label}[/]"
        p.write(c.x, top, title)
        badge = self.badge()
        if badge:
            p.write(c.x + p.text.width(title) + p.ch * 3, top, badge)
        hint = f"[red]✗ {escape(self.error)}[/]" if self.error else self.hints()
        p.write(c.x, r.bottom - p.row, p.text.elide(hint, c.w))

    def on_mouse_down(self, event: MouseDown) -> None:
        if not self.answered and self.body is not None:
            self.body.focus()

    def plain(self) -> str:
        if self.answered:
            return f"✓ {plain_text(self.label)}  {plain_text(self.summary)}"
        return f"? {plain_text(self.label)}"


class AskPrompt(PromptEntry):
    """Yazı sorusu."""

    def __init__(self, label: str, *, value: str = "", placeholder: str = "", password: bool = False) -> None:
        super().__init__(label)
        self.input = Input(value, placeholder=placeholder, password=password)
        if value:  # varsayılan seçili gelir: yazmaya başlamak onun yerine geçer
            self.input._anchor = 0

    @property
    def body(self) -> Widget:
        return self.input

    def compose(self):
        yield self.input

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.answer(self.input.value)


def _tail(raw: str) -> str:
    """Yolun son parçası (son ayraçtan sonrası)."""
    cut = max(raw.rfind("/"), raw.rfind("\\") if os.sep == "\\" else -1)
    return raw[cut + 1:]


def complete_path(text: str, kind: str | None = None) -> tuple[str, list[str]]:
    """Yolun son parçasını tamamla: (yeni yazı, adaylar). Klasör adayları ayraçla biter ve önce gelir.

    Tek aday varsa tamamı, birden çoksa ortak başlangıçları yazılır. kind="dir" dosyaları atlar.
    """
    raw = text.strip().strip('"')
    tail = _tail(raw)
    head = raw[: len(raw) - len(tail)]
    folder = os.path.expandvars(os.path.expanduser(head)) if head else "."
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return text, []
    key = tail.casefold()
    names = []
    for entry in entries:
        if not entry.name.casefold().startswith(key) or (entry.name.startswith(".") and not tail.startswith(".")):
            continue
        try:
            is_dir = entry.is_dir()
        except OSError:
            continue
        if kind == "dir" and not is_dir:
            continue
        names.append(entry.name + (os.sep if is_dir else ""))
    names.sort(key=lambda n: (not n.endswith(os.sep), n.casefold()))
    if not names:
        return text, []
    if len(names) == 1:
        return head + names[0], names
    common = os.path.commonprefix([n.casefold() for n in names])
    if len(common) > len(tail):
        return head + names[0][: len(common)], names
    return text, names


def _browse_start(value: str) -> str:
    raw = os.path.expandvars(os.path.expanduser(value.strip().strip('"')))
    for candidate in (raw, os.path.dirname(raw)):
        if candidate and os.path.isdir(candidate):
            return os.path.abspath(candidate)
    return os.getcwd()


class PathPrompt(AskPrompt):
    """Yol sorusu: Tab son parçayı tamamlar (birden çok aday varsa aralarında döner), Ctrl+O
    dosya diyaloğunu açar; dosya yöneticisinden bırakılan yol alana yazılır."""

    def __init__(self, label: str, *, value: str = "", kind: str | None = None) -> None:
        super().__init__(label, value=value)
        self.input.drop_replaces = True
        self.kind = kind
        self.candidates: list[str] = []
        self._cycle: tuple[str, list[str], int] | None = None  # (baş, adaylar, sıradaki)
        self._completing = False

    def hints(self) -> str:
        return _keys(("⏎", "onayla"), ("tab", "tamamla"), ("ctrl+o", "gözat"))

    def extra_rows(self) -> int:
        return 1 if self.candidates else 0

    def render(self, p) -> None:
        super().render(p)
        if self.answered or not self.candidates:
            return
        c = self.content
        current = self._cycle[1][self._cycle[2]] if self._cycle else None
        x, shown = c.x + p.ch * 2, 0
        for name in self.candidates:
            markup = f"[accent bold]{escape(name)}[/]" if name == current else f"[dim]{escape(name)}[/]"
            w = p.text.width(markup)
            if x + w > c.right - p.ch * 6:
                p.write(x, c.bottom, f"[faint]+{len(self.candidates) - shown}[/]")
                break
            p.write(x, c.bottom, markup)
            x += w + p.ch * 2
            shown += 1

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        if not self._completing and (self._cycle or self.candidates):
            self._cycle, self.candidates = None, []
            self.refresh(layout=True)

    def _set(self, text: str) -> None:
        self._completing = True
        try:
            self.input.value = text
            self.input.cursor_position = len(text)
            self.input._anchor = None
        finally:
            self._completing = False

    @action("Tamamla", key="tab", show=False, palette=False)
    def complete(self) -> None:
        self._complete(1)

    @action("Önceki aday", key="shift+tab", show=False, palette=False)
    def complete_back(self) -> None:
        self._complete(-1)

    def _complete(self, step: int) -> None:
        if self._cycle is not None:
            head, names, i = self._cycle
            i = (i + step) % len(names)
            self._cycle = (head, names, i)
            self._set(head + names[i])
            self.refresh()
            return
        text, names = complete_path(self.input.value, self.kind)
        self.candidates = names if len(names) > 1 else []
        if text != self.input.value:
            self._set(text)
        elif len(names) > 1:  # ortak kısım zaten yazılı: adaylar arasında dön
            raw = text.strip().strip('"')
            head = raw[: len(raw) - len(_tail(raw))]
            i = 0 if step > 0 else len(names) - 1
            self._cycle = (head, names, i)
            self._set(head + names[i])
        self.refresh(layout=True)

    @action("Gözat", key="ctrl+o", hint="gözat")
    async def browse(self) -> None:
        """Dosya diyaloğundan seç: `dialogs` ayarına göre işletim sisteminin ya da termik'in gezgini."""
        mode = {"file": "open", "dir": "folder"}.get(self.kind, "any")
        chosen = await filedialog.ask(self.window, mode, plain_text(self.label), folder=_browse_start(self.input.value))
        if chosen and not self.answered:
            self._set(str(chosen))


class ChoosePrompt(PromptEntry):
    """Seçim sorusu (tekli ya da çoklu)."""

    def __init__(self, label: str, options: list[str], *, index: int = 0, multi: bool = False,
                 selected=()) -> None:
        super().__init__(label)
        self.list = OptionList(options, index=index, multi=multi, selected=selected)

    @property
    def body(self) -> Widget:
        return self.list

    def compose(self):
        yield self.list

    def on_option_list_selected(self, event: OptionList.Selected) -> None:
        event.stop()
        self.answer(event.index)

    def on_option_list_submitted(self, event: OptionList.Submitted) -> None:
        event.stop()
        self.answer(event.indices)

    def badge(self) -> str:
        lst = self.list
        parts = []
        if lst.query:
            parts.append(f"[faint]süz:[/] [accent]{escape(lst.query)}[/]")
        if lst.query or len(lst.options) > lst.rows:
            parts.append(f"[faint]{len(lst.matches)}/{len(lst.options)}[/]")
        if lst.multi:
            parts.append(f"[faint]{len(lst.selected)} seçili[/]")
        return "   ".join(parts)

    def hints(self) -> str:
        if self.list.multi:
            return _keys(("↑↓", "gez"), ("space", "işaretle"), ("⏎", "onayla"), ("ctrl+a", "hepsi"), ("yaz", "süz"))
        return _keys(("↑↓", "seç"), ("⏎", "onayla"), ("yaz", "süz"))


class ConfirmChoice(Widget):
    """[ Evet ]  [ Hayır ] — seçili olan öne çıkar; ←/→ değiştirir, ⏎ onaylar, baş harfler doğrudan cevaplar."""

    default_width = "auto"
    default_height = "auto"
    can_focus = True
    cursor = "hand"

    def __init__(self, yes: str, no: str, default: bool) -> None:
        super().__init__()
        self.labels = {True: yes, False: no}
        self.value = default
        self.hotkeys = {"y": True, "n": False}
        a, b = yes[:1].lower(), no[:1].lower()
        if a and b and a != b:
            self.hotkeys.update({a: True, b: False})
        self._rects: dict[bool, pygame.Rect] = {}
        self._hover: bool | None = None

    def measure(self, p, width: int) -> tuple[int, int]:
        sizes = [p.button_size(label, True) for label in self.labels.values()]
        return sum(w for w, _ in sizes) + p.ch * 3, max(h for _, h in sizes)

    def render(self, p) -> None:
        c = self.content
        x = c.x
        for value in (True, False):
            rect = p.button(x, c.y, self.labels[value], primary=value == self.value,
                            hot=value != self.value and value == self._hover)
            self._rects[value] = rect
            x = rect.right + p.ch * 3

    def on_key(self, event: Key) -> None:
        key = event.key
        char = (event.char or "").lower()
        if key in ("left", "right", "up", "down", "tab", "shift+tab"):
            self.value = not self.value
            self.refresh()
        elif key in ("enter", "space"):
            self.parent.answer(self.value)
        elif char in self.hotkeys and not key.startswith(("ctrl+", "alt+", "altgr+")):
            self.value = self.hotkeys[char]
            self.parent.answer(self.value)
        else:
            return
        event.stop()

    def _value_at(self, x: int, y: int) -> bool | None:
        return next((v for v, r in self._rects.items() if r.collidepoint(x, y)), None)

    def on_mouse_move(self, event: MouseMove) -> None:
        value = self._value_at(event.x, event.y)
        if value != self._hover:
            self._hover = value
            self.refresh()

    def on_mouse_leave(self) -> None:
        self._hover = None
        self.refresh()

    def on_click(self, event: Click) -> None:
        value = self._value_at(event.x, event.y)
        if value is not None:
            event.stop()
            self.value = value
            self.parent.answer(value)


class ConfirmPrompt(PromptEntry):
    """Evet/hayır sorusu."""

    def __init__(self, label: str, *, default: bool = True, yes: str = "Evet", no: str = "Hayır") -> None:
        super().__init__(label)
        self.choice = ConfirmChoice(yes, no, default)

    @property
    def body(self) -> Widget:
        return self.choice

    def compose(self):
        yield self.choice

    def hints(self) -> str:
        letters = "/".join(k for k in self.choice.hotkeys if k not in "yn") or "y/n"
        return _keys(("←→", "seç"), ("⏎", "onayla"), (letters, "cevapla"))


class _FormCheck(Checkbox):
    """Formdaki onay kutusu: space değiştirir; ⏎ formda sonraki alana geçer."""

    @action("Değiştir", key="space", show=False, palette=False)
    def press(self) -> None:
        self.toggle()


def _field_widget(spec: dict) -> Widget:
    """Alan tanımından bileşen: kısa seçim radyo, uzun seçim süzülebilir liste, onay kutusu, yazı alanı."""
    kind, value = spec["kind"], spec["value"]
    if kind == "check":
        return _FormCheck("", bool(value))
    if kind == "choice":
        options = spec["options"]
        if len(options) <= 4 and sum(len(o) for o in options) <= 40:
            return RadioSet(*(escape(o) for o in options), index=value)
        return OptionList(options, index=value, rows=5)
    return Input(value, password=spec["password"], placeholder=spec["placeholder"], width=48)


class _FormRow(Widget):
    """Form satırı: solda etiket sütunu, sağda alan. Hatalı alanın etiketi kırmızıdır."""

    default_height = "auto"

    def __init__(self, label: str, field: Widget, name: str | None = None) -> None:
        super().__init__()
        self.label, self.field, self.name = label, field, name
        self.error = ""

    def compose(self):
        yield self.field

    @property
    def raw(self) -> Any:
        f = self.field
        if isinstance(f, Checkbox):
            return f.value
        if isinstance(f, (RadioSet, OptionList)):
            return f.index if f.index is not None else 0
        return f.value

    def chrome(self, p) -> tuple[int, int, int, int]:
        return 0, 0, 0, self.parent.label_width(p)

    def render(self, p) -> None:
        th = p.theme
        if self.label:
            color = th.red if self.error else th.text if self.focus_within else th.dim
            p.write(self.region.x, self.region.y, p.text.elide(self.label, self.content.x - self.region.x - p.ch),
                    color=color)


class FormPrompt(PromptEntry):
    """Birkaç alanı tek seferde soran form. Tab alanlar arasında gezer, ⏎ sonraki alana geçer
    (sonuncusunda gönderir), ctrl+⏎ her yerden gönderir. Cevaplanınca alan başına bir özet satırı."""

    def __init__(self, label: str, *, fields: list[dict]) -> None:
        super().__init__(label, gap=0.25)
        self.specs = fields
        self.rows = [_FormRow(spec["label"], _field_widget(spec), spec["name"]) for spec in fields]
        self.button = Button("Tamam", variant="primary", on_press=lambda _button: self.submit())
        self.summaries: list[tuple[str, str]] = []

    @property
    def body(self) -> Widget:
        return self.rows[0].field

    def compose(self):
        yield from self.rows
        yield _FormRow("", self.button)

    def label_width(self, p) -> int:
        return max(p.text.width(spec["label"]) for spec in self.specs) + p.ch * 3

    def hints(self) -> str:
        return _keys(("tab", "sonraki alan"), ("⏎", "ilerle"), ("ctrl+⏎", "gönder"))

    # ── gezinme ve gönderme ──────────────────────────────

    def advance(self) -> None:
        """⏎: odaktaki alandan sonrakine geç; sonuncudaysa gönder."""
        current = next((i for i, row in enumerate(self.rows) if row.focus_within), None)
        if current is None or current == len(self.rows) - 1:
            self.submit()
        else:
            self.rows[current + 1].field.focus()

    @action("Gönder", key="ctrl+enter", show=False)
    def submit(self) -> None:
        if self.listening:
            self.answer({row.name: row.raw for row in self.rows})

    def on_key(self, event: Key) -> None:
        if event.key == "enter" and not self.answered:  # onay kutusu ve radyoda ⏎ ilerletir
            event.stop()
            self.advance()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.advance()

    def on_option_list_selected(self, event: OptionList.Selected) -> None:
        event.stop()
        self.advance()

    # ── script ile alışveriş ─────────────────────────────

    def reject(self, errors: dict[str, str], future: Future) -> None:
        for row in self.rows:
            row.error = errors.get(row.name, "")
        first = next((row for row in self.rows if row.error), None)
        super().reject(f"{plain_text(first.label)}: {first.error}" if first else "geçersiz değer", future)
        if first is not None:
            first.field.focus()

    def accept(self, summary: dict[str, str]) -> None:
        self.summaries = [(spec["label"], summary[spec["name"]]) for spec in self.specs]
        super().accept("")

    def measure(self, p, width: int) -> tuple[int, int]:
        if self.answered:
            return width, p.row * (len(self.summaries) + (1 if self.label else 0))
        return super().measure(p, width)

    def render(self, p) -> None:
        if not self.answered:
            super().render(p)
            return
        r = self.region
        x, y = r.x + p.ch * 2, r.y
        if self.label:  # başlık, altında girintili alanlar
            p.write(r.x, y, "[green]✓[/]")
            p.write(x, y, f"[dim]{self.label}[/]")
            x, y = x + p.ch * 2, y + p.row
        column = x + max(p.text.width(label) for label, _ in self.summaries) + p.ch * 2
        for label, value in self.summaries:
            if not self.label:
                p.write(r.x, y, "[green]✓[/]")
            p.write(x, y, f"[dim]{label}[/]")
            p.write(column, y, p.text.elide(value, r.right - column))
            y += p.row

    def plain(self) -> str:
        if not self.answered:
            return f"? {plain_text(self.label)}"
        head = [f"✓ {plain_text(self.label)}"] if self.label else []
        return "\n".join(head + [f"  {plain_text(label)}  {plain_text(value)}" for label, value in self.summaries])


# ── pencere ───────────────────────────────────────────────

class StatusLine(Widget):
    """En alttaki durum satırı: script çalışıyor mu, cevap mı bekliyor, bitti mi."""

    default_height = "auto"

    def __init__(self) -> None:
        super().__init__(padding=(0.5, 0, 0, 0))
        self._close: tuple[int, int] | None = None  # "⏎ kapat"ın x aralığı

    def measure(self, p, width: int) -> tuple[int, int]:
        return width, p.row

    def render(self, p) -> None:
        th = p.theme
        app = self.app
        r, c = self.region, self.content
        p.surface.fill(th.border, (r.x, r.y + (c.y - r.y) // 2, r.w, 1))
        outcome = app.outcome
        if outcome is None:
            if app.active_prompt is not None:
                left = "[accent]●[/] [dim]cevap bekleniyor[/]"
            else:
                left = f"[accent]{_frame()}[/] [dim]çalışıyor[/]"
            items = [("ctrl+p", "komutlar")]
        else:
            took = duration((app.ended_at or time.monotonic()) - app.started_at)
            left = {"done": f"[green]✓[/] bitti [faint]· {took}[/]",
                    "failed": "[red]✗[/] hata ile bitti",
                    "stopped": "[yellow]■[/] durduruldu"}[outcome]
            items = [("⏎", "kapat"), ("ctrl+p", "komutlar")]
        p.write(c.x, c.y, left)
        right = _keys(*items)
        x = c.right - p.text.width(right)
        p.write(x, c.y, right)
        self._close = (x, x + p.text.width(_keys(items[0]))) if outcome is not None else None

    def on_click(self, event: Click) -> None:
        if self._close is not None and self._close[0] <= event.x < self._close[1]:
            event.stop()
            self.app.exit()


class FlowApp(App):
    """Döküm penceresi: alt alta akan çıktı, sorular ve ilerlemeler; en altta durum satırı."""

    SIZE = (980, 660)
    PADDING = (0.75, 2.5)
    GAP = 0

    def __init__(self, backend: WindowBackend, *, title: str, theme: str | None = None, look: str | None = None,
                 density: str | None = None, **tokens) -> None:
        super().__init__(theme=theme or "okyanus", look=look or "terminal", density=density or "rahat",
                         title=title, **tokens)
        self.backend = backend
        self.transcript = Transcript()
        self.status_line = StatusLine()
        self.active_prompt: PromptEntry | None = None  # cevap bekleyen soru
        self.outcome: str | None = None         # script bitince: done · failed · stopped
        self.started_at = time.monotonic()
        self.ended_at: float | None = None
        self.label_chars = 0                    # özetlerde cevap sütunu, karakter
        self._lines = 0

    def compose(self):
        yield self.transcript
        yield self.status_line

    def on_mount(self) -> None:
        self.set_interval(0.1, self._watch)
        self.backend._started()

    def _watch(self) -> None:
        if self.outcome is None and not self.backend.owner.is_alive():
            self.backend._drain()  # script'in son işleri
            self.finish("done")
        elif self.outcome is None and self.active_prompt is None:
            self.status_line.refresh()  # dönen işaret

    def answer_x(self, p, x: int, label: str) -> int:
        """Özet satırında cevabın başladığı x: kısa etiketlerin cevapları hizalı bir sütun olur."""
        return x + max(self.label_chars * p.ch, p.text.width(label) + p.ch * 2)

    def note_label(self, label: str) -> None:
        width = display_width(plain_text(label)) + 2
        if self.label_chars < width <= LABEL_CAP:
            self.label_chars = width
            self.refresh()

    # ── script'ten gelen işler ───────────────────────────

    def _insert(self, widget: Widget) -> None:
        """Dökümün sonuna ekle; cevap bekleyen soru varsa onun üstüne (soru hep en altta kalsın)."""
        kids = self.transcript.children
        self.transcript.mount(widget, before=kids.index(self.active_prompt) if self.active_prompt in kids else None)

    def write(self, text: str, wrap: bool = True) -> None:
        kids = self.transcript.children
        at = kids.index(self.active_prompt) if self.active_prompt in kids else len(kids)
        block = kids[at - 1] if at and isinstance(kids[at - 1], OutputBlock) else None
        if block is None:
            block = OutputBlock()
            self._insert(block)
        before = len(block.lines)
        block.add(text, wrap)
        self._lines += len(block.lines) - before
        if self._lines > MAX_LINES:  # en eski satırları at
            for entry in list(self.transcript.children):
                if self._lines <= MAX_LINES:
                    break
                if isinstance(entry, OutputBlock):
                    self._lines -= entry.drop(self._lines - MAX_LINES)
                    if not entry.lines:
                        entry.remove()

    def add_rule(self, title: str) -> None:
        self._insert(RuleLine(title))

    def add_live(self, entry: LiveEntry) -> None:
        self._insert(entry)

    def add_prompt(self, widget: PromptEntry, future: Future) -> None:
        self.transcript.follow = True  # yukarı kaydırılmış olsa bile soru görünsün
        self.transcript.mount(widget)
        self.active_prompt = widget
        widget.listen(future)
        body = widget.body
        if body is not None:
            if len(self.children) > 1:  # üstte palet ya da diyalog açık: kapanınca odak soruya geçsin
                self._focus_stack[0] = body
            else:
                body.focus()

    def prompt_done(self, widget: PromptEntry) -> None:
        if self.active_prompt is widget:
            self.active_prompt = None
        self.note_label(widget.label)

    def fail(self, title: str, details: list[str]) -> None:
        """Script yakalanmayan bir hatayla bitti: hatayı dökümün sonuna yaz; pencere açık kalır."""
        block = OutputBlock()
        block.add(f"[red]✗ {escape(title)}[/]\n")
        block.add("".join(f"[faint]{escape(line)}[/]\n" for line in details))
        self.transcript.follow = True
        self._insert(block)
        self.finish("failed")

    def stop(self) -> None:
        """Script Ctrl+C ile durdu: pencere de kapanır."""
        self.outcome = self.outcome or "stopped"
        self.exit()

    def finish(self, outcome: str) -> None:
        """Script bitti: durum satırı sonucu gösterir; keep_open=False ise pencere kapanır (hata hariç)."""
        if self.outcome is not None:
            return
        self.outcome = outcome
        self.ended_at = time.monotonic()
        for entry in self.transcript.children:
            if isinstance(entry, LiveEntry) and entry.progress.running:
                entry.progress.finish("error" if outcome == "failed" else "stopped")
        if outcome == "done" and not self.backend.session.keep_open:
            self.exit()
        self.refresh(layout=True)

    # ── tuşlar ve kapanış ────────────────────────────────

    def on_key(self, event: Key) -> None:
        if self.outcome is not None and event.key in ("enter", "escape"):
            event.stop()
            self.exit()

    def on_drop(self, event: Drop) -> None:
        """Pencerenin herhangi bir yerine bırakılan dosya, cevap bekleyen yol sorusuna yazılır."""
        prompt = self.active_prompt
        if isinstance(prompt, PathPrompt) and not prompt.answered and event.paths:
            event.stop()
            prompt._set(str(event.paths[0]))
            prompt.input.focus()

    @action("Dökümü panoya kopyala", key="ctrl+shift+c", hint="kopyala")
    def copy_transcript(self) -> None:
        clipboard.put_text("\n".join(entry.plain() for entry in self.transcript.children))
        self.notify("döküm panoya kopyalandı", "ok")

    def _shutdown(self) -> None:
        self.backend._window_closed()
        super()._shutdown()


# ── arka uç ───────────────────────────────────────────────

class _WindowClosed(Exception):
    """Pencere kapandı; bekleyen soru KeyboardInterrupt'a çevrilir."""


class _WindowPrompt:
    """Script thread'indeki soru tutamağı."""

    def __init__(self, backend: WindowBackend, widget: PromptEntry) -> None:
        self.backend, self.widget = backend, widget
        self.future: Future = Future()
        self._send(backend.app.add_prompt, widget, self.future)

    def _send(self, fn: Callable, *args) -> None:
        future = self.future

        def run() -> None:
            try:
                fn(*args)
            except Exception as exc:  # termik'teki bir hata script'i sonsuza dek bekletmesin
                if not future.done():
                    future.set_exception(exc)
                raise

        self.backend._post(run)

    def wait(self) -> Any:
        return self.backend.wait(self.future)

    def reject(self, message: str) -> None:
        self.future = Future()
        self._send(self.widget.reject, message, self.future)

    def accept(self, summary: str) -> None:
        self.backend._post(self.widget.accept, summary)


class _LiveView:
    def __init__(self, backend: WindowBackend, entry: LiveEntry) -> None:
        self.backend, self.entry = backend, entry

    def finish(self) -> None:
        self.backend._post(self.entry.finish)


_PROMPTS: dict[str, Callable[..., PromptEntry]] = {
    "ask": AskPrompt,
    "path": PathPrompt,
    "confirm": ConfirmPrompt,
    "choose": lambda label, **spec: ChoosePrompt(label, multi=False, **spec),
    "many": lambda label, **spec: ChoosePrompt(label, multi=True, **spec),
    "form": FormPrompt,
}


class WindowBackend:
    """Pencereyi ayrı thread'de açar; script thread'inden gelen işleri ona taşır."""

    kind = "window"

    def __init__(self, session) -> None:
        self.session = session
        self.owner = threading.current_thread()  # script'in thread'i; bitince script bitmiş sayılır
        self.app = FlowApp(self, title=session.title, theme=session.theme, look=session.look,
                           density=session.density, **session.tokens)
        self._lock = threading.Lock()
        self._ops: list[tuple[Callable, tuple]] = []
        self._scheduled = False
        self._ready = threading.Event()
        self._up = False                   # pencere açıldı
        self._failure: BaseException | None = None
        self._closed = False
        self._closing = False              # kapatan script: ana thread'e kesme gönderilmesin
        self._waiting: Future | None = None
        # gerçek pencere kapanana kadar süreç açık kalsın; görünmez pencerede testler takılmasın
        self.thread = threading.Thread(target=self._run, name="termik-pencere", daemon=session.headless)
        self.thread.start()
        self._ready.wait()
        if self._failure is not None:
            self.thread.join()
            raise self._failure
        _ACTIVE.add(self)
        _install_hooks()

    # ── pencere thread'i ─────────────────────────────────

    def _run(self) -> None:
        try:
            asyncio.run(self.app._main(self.session.size, headless=self.session.headless))
        except BaseException as exc:
            if not self._up:  # açılamadı: çağıran terminale düşsün
                self._failure = exc
                try:
                    pygame.quit()
                except Exception:
                    pass
            else:
                traceback.print_exc()
        finally:
            self._window_closed()
            self._ready.set()

    def _started(self) -> None:
        self._up = True
        self._ready.set()

    def _drain(self) -> None:
        with self._lock:
            ops, self._ops = self._ops, []
            self._scheduled = False
        for fn, args in ops:
            self.app._call(fn, *args)

    def _window_closed(self) -> None:
        """Pencere kapandı: bekleyen soruyu ya da (kullanıcı kapattıysa) script'i kes."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            waiting, closing = self._waiting, self._closing
        _ACTIVE.discard(self)
        capture.uninstall(self.session)  # print ve input yeniden konsola
        if waiting is not None and not waiting.done():
            waiting.set_exception(_WindowClosed())
        elif (self._up and not closing and self.app.outcome is None
              and self.owner is threading.main_thread() and self.owner.is_alive()):
            _interrupt_main()

    # ── script thread'i ──────────────────────────────────

    def _post(self, fn: Callable, *args) -> bool:
        """fn(*args)'ı pencere thread'inde, gönderilme sırasıyla çalıştır. Pencere kapandıysa False."""
        with self._lock:
            if self._closed:
                return False
            self._ops.append((fn, args))
            if self._scheduled:
                return True
            self._scheduled = True
        try:
            self.app._loop.call_soon_threadsafe(self._drain)
        except RuntimeError:  # döngü tam o an kapandı
            return False
        return True

    def wait(self, future: Future) -> Any:
        """Cevabı bekle. Ctrl+C'ye açık kalmak için kısa aralıklarla bekler."""
        with self._lock:
            if self._closed:
                raise KeyboardInterrupt("pencere kapatıldı")
            self._waiting = future
        try:
            while True:
                try:
                    return future.result(timeout=0.25)
                except TimeoutError:
                    continue
        except _WindowClosed:
            raise KeyboardInterrupt("pencere kapatıldı") from None
        finally:
            with self._lock:
                self._waiting = None

    def write(self, text: str) -> None:
        self._post(self.app.write, text)

    def rule(self, title: str) -> None:
        self._post(self.app.add_rule, title)

    def table(self, lines: list[str]) -> None:
        self._post(self.app.write, "".join(line + "\n" for line in lines), False)

    def prompt(self, what: str, label: str, **spec) -> _WindowPrompt:
        return _WindowPrompt(self, _PROMPTS[what](label, **spec))

    def live(self, progress: Progress) -> _LiveView:
        entry = LiveEntry(progress)
        self._post(self.app.add_live, entry)
        return _LiveView(self, entry)

    def restyle(self, theme: str | None = None, **changes) -> None:
        self._post(functools.partial(self.app.set_theme, theme, **changes))

    def close(self) -> None:
        """Pencereyi kapat ve thread'inin bitmesini bekle. pygame süreç başına tek pencere tuttuğu
        için zaten kapanmış olsa da beklenir: yarım kalan pygame.quit() sonraki pencereyi öldürmesin."""
        with self._lock:
            closed = self._closed
            self._closing = True
        if not closed:
            self._post(self.app.exit)
        if threading.current_thread() is not self.thread:
            self.thread.join(timeout=10)

    def script_failed(self, exc_type, exc, tb) -> None:
        """Script yakalanmayan bir hatayla bitiyor (excepthook'tan çağrılır)."""
        if issubclass(exc_type, KeyboardInterrupt):  # konsolda Ctrl+C: pencere de kapansın
            with self._lock:
                self._closing = True
            self._post(self.app.stop)
            return
        details = "".join(traceback.format_exception(exc_type, exc, tb)).rstrip("\n").split("\n")
        title = traceback.format_exception_only(exc_type, exc)[-1].strip()
        self._post(self.app.fail, title, details)


# ── süreç düzeyi kancalar ─────────────────────────────────

_ACTIVE: weakref.WeakSet[WindowBackend] = weakref.WeakSet()
_hooks_installed = False


def _install_hooks() -> None:
    """Yakalanmayan hatalar açık pencerede de gösterilsin (pythonw'da konsol yok)."""
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True
    previous, previous_thread = sys.excepthook, threading.excepthook

    def excepthook(exc_type, exc, tb) -> None:
        try:
            with capture.muted():  # iz yalnızca konsola; pencere onu kendi biçiminde gösterir
                previous(exc_type, exc, tb)
        finally:
            for backend in list(_ACTIVE):
                if backend.owner is threading.main_thread():
                    backend.script_failed(exc_type, exc, tb)

    def thread_excepthook(args) -> None:
        try:
            with capture.muted():
                previous_thread(args)
        finally:
            for backend in list(_ACTIVE):
                if backend.owner is args.thread:
                    backend.script_failed(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
    atexit.register(_close_hidden)


def _close_hidden() -> None:
    """Süreç biterken açık kalan görünmez pencereleri kapat: daemon thread'deki SDL yarıda kesilmesin."""
    for backend in list(_ACTIVE):
        if backend.session.headless:
            backend.close()


def _interrupt_main() -> None:
    """Ana thread'e Ctrl+C gönder; time.sleep gibi bekleyişleri de keser."""
    if not callable(signal.getsignal(signal.SIGINT)):
        return  # SIGINT yok sayılıyor ya da varsayılan davranışta: script kendi haline kalır
    if sys.platform == "win32":
        signal.raise_signal(signal.SIGINT)
    else:
        signal.pthread_kill(threading.main_thread().ident, signal.SIGINT)
