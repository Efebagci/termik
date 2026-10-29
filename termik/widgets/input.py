"""Tek satırlık yazı alanı."""

from __future__ import annotations

import time
from typing import Callable

from .. import clipboard
from ..events import Drop, Key, Message, MouseDown, MouseMove, TextInput
from ..reactive import reactive
from ..text import Style
from ..theme import mix
from ..widget import Widget

_PLAIN = Style()


def _is_word(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


class Input(Widget):
    """Tek satırlık yazı alanı: blok imleç, seçim, pano, kelime kelime gezinme.

    label= verilirse üstünde etiket ve solunda odak çubuğu olan iki satırlık bir alan olur.
    Her değişiklikte Input.Changed, Enter'da Input.Submitted mesajı yukarı iletilir.

    Tuşlar: ←/→ (ctrl ile kelime), home/end, shift ile seçim, ctrl+a, ctrl+c/x/v,
    backspace/delete (ctrl ile kelime), enter. Dosya yöneticisinden bırakılan yol bırakılan yere
    yazılır; drop_replaces = True ise (yol alanları için) yazının yerine geçer.
    """

    drop_replaces = False
    default_height = "auto"
    can_focus = True
    accepts_text = True
    cursor = "ibeam"
    value = reactive("")

    class Changed(Message):
        def __init__(self, input: Input, value: str) -> None:
            super().__init__()
            self.input, self.value = input, value

    class Submitted(Message):
        def __init__(self, input: Input, value: str) -> None:
            super().__init__()
            self.input, self.value = input, value

    def __init__(self, value: str = "", *, label: str | None = None, placeholder: str = "",
                 prompt: str = "❯", password: bool = False, max_length: int = 0,
                 on_submit: Callable | None = None, on_change: Callable | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label, self.placeholder, self.prompt = label, placeholder, prompt
        self.password, self.max_length = password, max_length
        self.on_submit, self.on_change = on_submit, on_change
        self.value = value
        self.cursor_position = len(value)
        self._anchor: int | None = None  # seçimin sabit ucu
        self._scroll = 0                 # yatay kaydırma, piksel
        self._edited_at = 0.0
        self._blink = None
        self._text_x = 0                 # son çizimde yazının başladığı x (fare için)

    # ── seçim ve düzenleme ────────────────────────────────

    @property
    def selection(self) -> tuple[int, int] | None:
        if self._anchor is None or self._anchor == self.cursor_position:
            return None
        return min(self._anchor, self.cursor_position), max(self._anchor, self.cursor_position)

    @property
    def selected_text(self) -> str:
        sel = self.selection
        return self.value[sel[0]:sel[1]] if sel else ""

    def _touch(self) -> None:
        self._edited_at = time.monotonic()
        self.refresh()

    def _move(self, pos: int, select: bool) -> None:
        if select and self._anchor is None:
            self._anchor = self.cursor_position
        elif not select:
            self._anchor = None
        self.cursor_position = max(0, min(len(self.value), pos))
        self._touch()

    def _replace(self, start: int, end: int, text: str) -> None:
        value = self.value[:start] + text + self.value[end:]
        if self.max_length and len(value) > self.max_length:
            return
        self.cursor_position = start + len(text)
        self._anchor = None
        self.value = value
        self._touch()

    def insert(self, text: str) -> None:
        """İmlecin yerine (seçim varsa onun yerine) yazı ekle."""
        start, end = self.selection or (self.cursor_position, self.cursor_position)
        self._replace(start, end, text)

    def _word_left(self, pos: int) -> int:
        v = self.value
        while pos > 0 and not _is_word(v[pos - 1]):
            pos -= 1
        while pos > 0 and _is_word(v[pos - 1]):
            pos -= 1
        return pos

    def _word_right(self, pos: int) -> int:
        v = self.value
        while pos < len(v) and not _is_word(v[pos]):
            pos += 1
        while pos < len(v) and _is_word(v[pos]):
            pos += 1
        return pos

    def watch_value(self, value: str) -> None:
        self.cursor_position = min(self.cursor_position, len(value))
        self.post_message(Input.Changed(self, value))
        if self.on_change is not None:
            self._call(self.on_change, value)

    # ── olaylar ───────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        key = event.key
        shift = "shift+" in key
        base = key.replace("shift+", "")
        pos, sel = self.cursor_position, self.selection
        if base == "left":
            self._move(sel[0] if sel and not shift else pos - 1, shift)
        elif base == "right":
            self._move(sel[1] if sel and not shift else pos + 1, shift)
        elif base == "ctrl+left":
            self._move(self._word_left(pos), shift)
        elif base == "ctrl+right":
            self._move(self._word_right(pos), shift)
        elif base == "home":
            self._move(0, shift)
        elif base == "end":
            self._move(len(self.value), shift)
        elif key in ("backspace", "ctrl+backspace", "delete", "ctrl+delete"):
            if sel:
                self._replace(*sel, "")
            elif key == "backspace" and pos:
                self._replace(pos - 1, pos, "")
            elif key == "ctrl+backspace":
                self._replace(self._word_left(pos), pos, "")
            elif key == "delete":
                self._replace(pos, pos + 1, "")
            elif key == "ctrl+delete":
                self._replace(pos, self._word_right(pos), "")
        elif key == "ctrl+a":
            self._anchor, self.cursor_position = 0, len(self.value)
            self._touch()
        elif key in ("ctrl+c", "ctrl+x"):
            if sel and not self.password:
                clipboard.put_text(self.selected_text)
                if key == "ctrl+x":
                    self._replace(*sel, "")
        elif key == "ctrl+v":
            text = clipboard.get_text().replace("\r", "").split("\n")[0]
            if text:
                self.insert(text)
        elif key == "enter":
            self.post_message(Input.Submitted(self, self.value))
            if self.on_submit is not None:
                self._call(self.on_submit, self.value)
        elif not event.is_printable:  # harfler on_text_input ile gelir; kısayol sayılmasınlar
            return
        event.stop()

    def on_text_input(self, event: TextInput) -> None:
        self.insert(event.text)

    def on_focus(self) -> None:
        self._edited_at = time.monotonic()
        self._blink = self.set_interval(0.53, self.refresh)

    def on_blur(self) -> None:
        if self._blink is not None:
            self._blink.stop()
            self._blink = None
        self._anchor = None

    def _index_at(self, p, x: int) -> int:
        """x koordinatına en yakın karakter sınırı."""
        shown = self._shown()
        target = x - self._text_x + self._scroll
        best, best_d = 0, abs(target)
        for i in range(1, len(shown) + 1):
            d = abs(target - p.text.width([(shown[:i], _PLAIN)]))
            if d < best_d:
                best, best_d = i, d
        return best

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button == 1:
            self._move(self._index_at(self.app.painter, event.x), select=False)
            self._anchor = self.cursor_position  # sürüklenirse seçim buradan başlar
            event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        if event.button and self._anchor is not None:  # sürükleyerek seçim
            self.cursor_position = self._index_at(self.app.painter, event.x)
            self._touch()

    def on_drop(self, event: Drop) -> None:
        """Dosya yöneticisinden bırakılan yol (ya da yazı) bırakılan yere yazılır."""
        text = " ".join(event.as_text().splitlines())
        if self.disabled or not text:
            return
        event.stop()
        self.focus()
        if self.drop_replaces:
            self.value = text
            self.cursor_position = len(text)
            self._anchor = None
            return
        self._move(self._index_at(self.app.painter, event.x), select=False)
        self.insert(text)

    # ── çizim ─────────────────────────────────────────────

    def _shown(self) -> str:
        return "•" * len(self.value) if self.password else self.value

    def _caret_on(self) -> bool:
        idle = time.monotonic() - self._edited_at
        return idle < 0.6 or (idle % 1.06) < 0.53

    def measure(self, p, width: int) -> tuple[int, int]:
        return p.ch * 24, p.row * (2 if self.label else 1)

    def render(self, p) -> None:
        th = p.theme
        c = self.content
        focused = self.has_focus
        x, y = c.x, c.y
        if self.label:  # etiket + solda odak çubuğu
            p.surface.fill(th.accent if focused else th.border, (x, y + 3, 2, p.row * 2 - 6))
            x += p.ch + p.ch // 2
            p.write(x, y, self.label, color=th.text if focused else th.dim)
            y += p.row
        if self.prompt:
            x += p.write(x, y, [(self.prompt + " ", Style(bold=True))], color=th.accent if focused else th.faint)
        self._text_x = x
        shown = self._shown()
        room = max(p.ch, c.right - x - p.ch)
        caret = p.text.width([(shown[: self.cursor_position], _PLAIN)])
        # imleç görünür kalsın diye yatay kaydır
        if caret - self._scroll > room:
            self._scroll = caret - room
        elif caret < self._scroll:
            self._scroll = caret
        top = y + (p.row - p.text.height) // 2
        with p.clip((x, y, room + p.ch, p.row)):
            sel = self.selection
            if sel and focused:
                x0 = x + p.text.width([(shown[: sel[0]], _PLAIN)]) - self._scroll
                x1 = x + p.text.width([(shown[: sel[1]], _PLAIN)]) - self._scroll
                p.surface.fill(mix(th.bg, th.accent, 0.35), (x0, top, x1 - x0, p.text.height))
            if shown:
                p.write(x - self._scroll, y, [(shown, _PLAIN)])
            elif self.placeholder:
                p.write(x + (p.ch if focused else 0), y, [(self.placeholder, _PLAIN)], color=th.faint)
            if focused and self._caret_on():  # blok imleç; altındaki harf ters renkte
                cx = x + caret - self._scroll
                under = shown[self.cursor_position: self.cursor_position + 1]
                p.surface.fill(th.accent, (cx, top, p.text.width([(under, _PLAIN)]) if under else p.ch, p.text.height))
                if under:
                    p.write(cx, y, [(under, _PLAIN)], color=th.bg)
