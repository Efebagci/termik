"""Çok satırlı yazı alanı."""

from __future__ import annotations

import time
from typing import Callable

from .. import clipboard, keys
from ..draw import Painter
from ..events import Click, Drop, Key, Message, MouseDown, MouseMove, MouseScroll, TextInput
from ..text import Style
from ..theme import mix
from ..widget import Widget

_PLAIN = Style()
_NO_WRAP = 10**9
Location = tuple[int, int]  # (satır, sütun)


def _is_word(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


class TextArea(Widget):
    """Çok satırlı yazı alanı: blok imleç, seçim, pano, geri al/yinele, satır kaydırma.

    Tuşlar: oklar (ctrl ile kelime), home/end, ctrl+home/end, PgUp/PgDn, shift ile seçim,
    ctrl+a, ctrl+c/x/v, ctrl+z / ctrl+y, backspace/delete (ctrl ile kelime), Enter (satırın
    girintisini korur). Tab varsayılan olarak odağı taşır; tab_behavior="indent" ile girinti
    ekler, shift+tab girintiyi siler. submit_key verilirse (ör. "ctrl+enter") o tuş
    TextArea.Submitted iletir; submit_key="enter" ise yeni satır shift+enter ile açılır.

    rows görünür satır sayısıdır; max_rows verilirse alan yazdıkça max_rows'a kadar uzar.
    wrap=False uzun satırları kaydırmaz, yatay kayar. line_numbers=True solda satır numarası gösterir.
    """

    default_height = "auto"
    can_focus = True
    accepts_text = True
    cursor = "ibeam"
    bind_value = "text"

    class Changed(Message):
        def __init__(self, text_area: TextArea, text: str) -> None:
            super().__init__()
            self.text_area, self.text = text_area, text

    class Submitted(Message):
        def __init__(self, text_area: TextArea, text: str) -> None:
            super().__init__()
            self.text_area, self.text = text_area, text

    def __init__(self, text: str = "", *, placeholder: str = "", line_numbers: bool = False, wrap: bool = True,
                 rows: int = 5, max_rows: int | None = None, tab_size: int = 4, tab_behavior: str = "focus",
                 submit_key: str | None = None, read_only: bool = False, on_change: Callable | None = None,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.lines: list[str] = text.split("\n")
        self.placeholder, self.line_numbers, self.wrap = placeholder, line_numbers, wrap
        self.rows, self.max_rows, self.tab_size, self.tab_behavior = rows, max_rows, tab_size, tab_behavior
        self.submit_key = keys.normalize(submit_key) if submit_key else None
        self.read_only, self.on_change = read_only, on_change
        self.cursor_location: Location = (0, 0)
        self._anchor: Location | None = None   # seçimin sabit ucu
        self._goal_x: int | None = None        # ↑/↓'da korunan yatay konum
        self._top = 0                          # en üstte görünen görsel satır
        self._scroll_x = 0                     # kaydırma kapalıyken yatay kayma, piksel
        self._follow = True                    # sonraki çizimde imleci görünür alana getir
        self._undo: list[tuple[list[str], Location]] = []
        self._redo: list[tuple[list[str], Location]] = []
        self._last_edit = ("", 0.0)            # (tür, zaman): ardışık harfler tek geri alma adımı
        self._edited_at = 0.0
        self._blink = None
        self._version = 0
        self._segs: tuple | None = None        # (anahtar, parçalar, satırın ilk parçası)
        self._char_w: dict[str, int] = {}
        self._geom = (0, 1, 1)                 # son çizimde (yazı x, yazı genişliği, görünen satır)

    # ── metin ─────────────────────────────────────────────

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @text.setter
    def text(self, value: str) -> None:
        self.lines = value.split("\n")
        self.cursor_location = (len(self.lines) - 1, len(self.lines[-1]))
        self._anchor = None
        self._undo.clear()
        self._redo.clear()
        self._changed()

    def _changed(self) -> None:
        self._version += 1
        self._follow = True
        self._edited_at = time.monotonic()
        if self.is_mounted:
            self.post_message(TextArea.Changed(self, self.text))
            if self.on_change is not None:
                self._call(self.on_change, self.text)
        self._sync_bind()
        self.refresh(layout=self.max_rows is not None)

    @property
    def end(self) -> Location:
        return len(self.lines) - 1, len(self.lines[-1])

    def _clamp(self, loc: Location) -> Location:
        r = max(0, min(len(self.lines) - 1, loc[0]))
        return r, max(0, min(len(self.lines[r]), loc[1]))

    @property
    def selection(self) -> tuple[Location, Location] | None:
        if self._anchor is None or self._anchor == self.cursor_location:
            return None
        a, b = sorted((self._anchor, self.cursor_location))
        return a, b

    @property
    def selected_text(self) -> str:
        sel = self.selection
        if sel is None:
            return ""
        (r0, c0), (r1, c1) = sel
        if r0 == r1:
            return self.lines[r0][c0:c1]
        return "\n".join([self.lines[r0][c0:], *self.lines[r0 + 1:r1], self.lines[r1][:c1]])

    # ── düzenleme ─────────────────────────────────────────

    def _snapshot(self, kind: str) -> None:
        """Geri alma noktası; arka arkaya yazılan harfler ve silmeler tek adımda birleşir."""
        now = time.monotonic()
        last_kind, last_time = self._last_edit
        if not (kind == last_kind and kind in ("type", "delete") and now - last_time < 1.0):
            self._undo.append((list(self.lines), self.cursor_location))
            del self._undo[:-200]
        self._redo.clear()
        self._last_edit = (kind, now)

    def replace(self, start: Location, end: Location, text: str, *, kind: str = "edit") -> None:
        """start ile end arasındaki yazıyı text ile değiştir (geri alınabilir)."""
        if self.read_only:
            return
        (r0, c0), (r1, c1) = sorted((self._clamp(start), self._clamp(end)))
        self._snapshot(kind)
        head, tail = self.lines[r0][:c0], self.lines[r1][c1:]
        parts = text.split("\n")
        if len(parts) == 1:
            new, cursor = [head + parts[0] + tail], (r0, c0 + len(parts[0]))
        else:
            new = [head + parts[0], *parts[1:-1], parts[-1] + tail]
            cursor = (r0 + len(parts) - 1, len(parts[-1]))
        self.lines[r0:r1 + 1] = new
        self.cursor_location, self._anchor, self._goal_x = cursor, None, None
        self._changed()

    def insert(self, text: str, *, kind: str = "edit") -> None:
        """İmlecin yerine (seçim varsa onun yerine) yazı ekle."""
        start, end = self.selection or (self.cursor_location, self.cursor_location)
        self.replace(start, end, text, kind=kind)

    def undo(self) -> None:
        if self._undo and not self.read_only:
            self._redo.append((list(self.lines), self.cursor_location))
            self.lines, self.cursor_location = self._undo.pop()
            self._anchor, self._last_edit = None, ("", 0.0)
            self._changed()

    def redo(self) -> None:
        if self._redo and not self.read_only:
            self._undo.append((list(self.lines), self.cursor_location))
            self.lines, self.cursor_location = self._redo.pop()
            self._anchor, self._last_edit = None, ("", 0.0)
            self._changed()

    def _indent_lines(self, dedent: bool) -> None:
        """Seçili satırlara (seçim yoksa imlecin satırına) girinti ekle ya da sil."""
        sel = self.selection or (self.cursor_location, self.cursor_location)
        r0, r1 = sel[0][0], sel[1][0]
        self._snapshot("indent")
        pad = " " * self.tab_size
        for r in range(r0, r1 + 1):
            line = self.lines[r]
            if dedent:
                self.lines[r] = line[min(len(line) - len(line.lstrip(" ")), self.tab_size):]
            else:
                self.lines[r] = pad + line
        r, c = self.cursor_location
        self.cursor_location = self._clamp((r, c - self.tab_size if dedent else c + self.tab_size))
        if self._anchor is not None:
            ar, ac = self._anchor
            self._anchor = self._clamp((ar, ac - self.tab_size if dedent else ac + self.tab_size))
        self._changed()

    # ── imleç hareketi ────────────────────────────────────

    def _move(self, loc: Location, select: bool, *, keep_goal: bool = False) -> None:
        if select and self._anchor is None:
            self._anchor = self.cursor_location
        elif not select:
            self._anchor = None
        self.cursor_location = self._clamp(loc)
        if not keep_goal:
            self._goal_x = None
        self._follow = True
        self._edited_at = time.monotonic()
        self.refresh()

    def _left(self, loc: Location) -> Location:
        r, c = loc
        return (r, c - 1) if c else ((r - 1, len(self.lines[r - 1])) if r else loc)

    def _right(self, loc: Location) -> Location:
        r, c = loc
        return (r, c + 1) if c < len(self.lines[r]) else ((r + 1, 0) if r + 1 < len(self.lines) else loc)

    def _word_left(self, loc: Location) -> Location:
        r, c = loc
        if c == 0:
            return self._left(loc)
        line = self.lines[r]
        while c > 0 and not _is_word(line[c - 1]):
            c -= 1
        while c > 0 and _is_word(line[c - 1]):
            c -= 1
        return r, c

    def _word_right(self, loc: Location) -> Location:
        r, c = loc
        line = self.lines[r]
        if c == len(line):
            return self._right(loc)
        while c < len(line) and not _is_word(line[c]):
            c += 1
        while c < len(line) and _is_word(line[c]):
            c += 1
        return r, c

    # ── görsel satırlar ───────────────────────────────────

    def _cw(self, p, ch: str) -> int:
        w = self._char_w.get(ch)
        if w is None:
            w = self._char_w[ch] = p.text.width([(ch, _PLAIN)])
        return w

    def _width_of(self, p, line: str, start: int, end: int) -> int:
        return sum(self._cw(p, ch) for ch in line[start:end])

    def _segments(self, p, width: int) -> tuple[list[tuple[int, int, int]], list[int]]:
        """Görsel satırlar [(satır, başlangıç, bitiş)] ve her mantıksal satırın ilk parçasının sırası."""
        key = (width if self.wrap else _NO_WRAP, self._version)
        if self._segs is not None and self._segs[0] == key:
            return self._segs[1], self._segs[2]
        segs: list[tuple[int, int, int]] = []
        first: list[int] = []
        for r, line in enumerate(self.lines):
            first.append(len(segs))
            if not self.wrap or not line:
                segs.append((r, 0, len(line)))
                continue
            start = 0
            while start < len(line):
                used, end = 0, start
                while end < len(line):
                    w = self._cw(p, line[end])
                    if used + w > width and end > start:
                        break
                    used += w
                    end += 1
                if end < len(line):  # kelimeyi bölme: son boşluktan sonra kır
                    space = line.rfind(" ", start, end)
                    if space > start:
                        end = space + 1
                segs.append((r, start, end))
                start = end
        self._segs = (key, segs, first)
        return segs, first

    def _seg_index(self, segs, first, loc: Location) -> int:
        r, c = loc
        last = first[r + 1] - 1 if r + 1 < len(first) else len(segs) - 1
        for i in range(first[r], last + 1):
            if c < segs[i][2] or i == last:
                return i
        return last

    def _col_at(self, p, seg: tuple[int, int, int], x: int, is_last: bool) -> int:
        r, s, e = seg
        line, acc = self.lines[r], 0
        for i in range(s, e):
            w = self._cw(p, line[i])
            if x < acc + w / 2:
                return i
            acc += w
        return e if is_last else max(s, e - 1)  # kaydırılan parçanın sonu: kırılan boşluğun önü

    def _visual_width(self) -> int:
        return self._geom[1] if self.wrap else _NO_WRAP

    def _vertical(self, p, step: int) -> Location:
        segs, first = self._segments(p, self._visual_width())
        i = self._seg_index(segs, first, self.cursor_location)
        r, s, _ = segs[i]
        x = self._goal_x if self._goal_x is not None else self._width_of(p, self.lines[r], s, self.cursor_location[1])
        self._goal_x = x
        j = i + step
        if j < 0:
            return 0, 0
        if j >= len(segs):
            return self.end
        target = segs[j]
        is_last = j + 1 == len(segs) or segs[j + 1][0] != target[0]
        return target[0], self._col_at(p, target, x, is_last)

    # ── olaylar ───────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        key = event.key
        p = self.app.painter
        shift = "shift+" in key
        base = key.replace("shift+", "")
        loc, sel = self.cursor_location, self.selection
        visible = self._geom[2]
        if self.submit_key and key == self.submit_key:
            self.post_message(TextArea.Submitted(self, self.text))
        elif base == "left":
            self._move(sel[0] if sel and not shift else self._left(loc), shift)
        elif base == "right":
            self._move(sel[1] if sel and not shift else self._right(loc), shift)
        elif base == "ctrl+left":
            self._move(self._word_left(loc), shift)
        elif base == "ctrl+right":
            self._move(self._word_right(loc), shift)
        elif base in ("up", "down", "pageup", "pagedown"):
            step = {"up": -1, "down": 1, "pageup": 1 - visible, "pagedown": visible - 1}[base]
            self._move(self._vertical(p, step), shift, keep_goal=True)
        elif base == "home":
            self._move((loc[0], 0), shift)
        elif base == "end":
            self._move((loc[0], len(self.lines[loc[0]])), shift)
        elif base == "ctrl+home":
            self._move((0, 0), shift)
        elif base == "ctrl+end":
            self._move(self.end, shift)
        elif key == "ctrl+a":
            self._anchor = (0, 0)
            self._move(self.end, True)
        elif key in ("ctrl+c", "ctrl+x"):
            if sel:
                clipboard.put_text(self.selected_text)
                if key == "ctrl+x":
                    self.replace(*sel, "", kind="cut")
        elif key == "ctrl+v":
            text = clipboard.get_text().replace("\r\n", "\n").replace("\r", "\n")
            if text:
                self.insert(text, kind="paste")
        elif key == "ctrl+z":
            self.undo()
        elif key in ("ctrl+y", "ctrl+shift+z"):
            self.redo()
        elif key in ("backspace", "ctrl+backspace", "delete", "ctrl+delete"):
            if sel:
                self.replace(*sel, "", kind="delete")
            elif key == "backspace" and loc != (0, 0):
                self.replace(self._left(loc), loc, "", kind="delete")
            elif key == "ctrl+backspace":
                self.replace(self._word_left(loc), loc, "")
            elif key == "delete" and loc != self.end:
                self.replace(loc, self._right(loc), "", kind="delete")
            elif key == "ctrl+delete":
                self.replace(loc, self._word_right(loc), "")
        elif base == "enter":  # submit_key "enter" iken shift+enter yeni satır açar
            line = self.lines[loc[0]]
            indent = line[: len(line) - len(line.lstrip(" \t"))][: loc[1]]
            self.insert("\n" + indent, kind="newline")
        elif key == "tab" and self.tab_behavior == "indent":
            if sel and sel[0][0] != sel[1][0]:
                self._indent_lines(dedent=False)
            else:
                self.insert(" " * (self.tab_size - loc[1] % self.tab_size), kind="type")
        elif key == "shift+tab" and self.tab_behavior == "indent":
            self._indent_lines(dedent=True)
        elif not event.is_printable:  # bilinmeyen tuş yukarı kabarcıklansın (tab, esc, f-tuşları…)
            return
        event.stop()

    def on_text_input(self, event: TextInput) -> None:
        if not self.read_only:
            self.insert(event.text, kind="type")

    def on_focus(self) -> None:
        self._edited_at = time.monotonic()
        self._blink = self.set_interval(0.53, self.refresh)

    def on_blur(self) -> None:
        if self._blink is not None:
            self._blink.stop()
            self._blink = None

    def _loc_at(self, x: int, y: int) -> Location:
        p = self.app.painter
        text_x, _, _ = self._geom
        segs, _ = self._segments(p, self._visual_width())
        i = min(len(segs) - 1, self._top + max(0, (y - self.content.y) // p.row))
        is_last = i + 1 == len(segs) or segs[i + 1][0] != segs[i][0]
        return segs[i][0], self._col_at(p, segs[i], x - text_x + self._scroll_x, is_last)

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button == 1:
            event.stop()
            loc = self._loc_at(event.x, event.y)
            self._move(loc, select=False)
            self._anchor = loc  # sürüklenirse seçim buradan başlar

    def on_mouse_move(self, event: MouseMove) -> None:
        if event.button and self._anchor is not None:  # sürükleyerek seçim
            self.cursor_location = self._loc_at(event.x, event.y)
            self._follow = True
            self.refresh()

    def on_drop(self, event: Drop) -> None:
        """Bırakılan yazı ya da yollar (her biri ayrı satırda) bırakılan yere eklenir."""
        text = "\n".join(str(p) for p in event.paths) if event.paths else event.text or ""
        if self.disabled or self.read_only or not text:
            return
        event.stop()
        self.focus()
        self._move(self._loc_at(event.x, event.y), select=False)
        self.insert(text)

    def on_click(self, event: Click) -> None:
        if event.count == 2:  # çift tık: kelimeyi seç
            r, c = self.cursor_location
            line = self.lines[r]
            a = b = c
            while a > 0 and _is_word(line[a - 1]):
                a -= 1
            while b < len(line) and _is_word(line[b]):
                b += 1
            if a < b:
                self._anchor, self.cursor_location = (r, a), (r, b)
                self.refresh()

    def on_mouse_scroll(self, event: MouseScroll) -> None:
        event.stop()
        self._top = max(0, self._top - event.dy * 3)
        self.refresh()

    # ── yerleşim ve çizim ─────────────────────────────────

    def _gutter(self, p) -> int:
        return p.text.width(str(len(self.lines))) + p.ch * 2 if self.line_numbers else 0

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        rows = self.rows
        if self.max_rows is not None:  # render'daki yazı genişliğiyle aynı hesap
            segs, _ = self._segments(p, max(p.ch, width - self._gutter(p) - p.ch // 2 - p.ch * 2))
            rows = max(self.rows, min(self.max_rows, len(segs)))
        return p.ch * 24, rows * p.row

    def _caret_on(self) -> bool:
        idle = time.monotonic() - self._edited_at
        return idle < 0.6 or (idle % 1.06) < 0.53

    def render(self, p: Painter) -> None:
        th = p.theme
        c = self.content
        focused = self.has_focus
        text_x = c.x + self._gutter(p) + p.ch // 2
        width = max(p.ch, c.right - text_x - p.ch * 2)  # imlece ve kaydırma çubuğuna yer
        visible = max(1, c.h // p.row)
        self._geom = (text_x, width, visible)
        segs, first = self._segments(p, self._visual_width())
        cur = self._seg_index(segs, first, self.cursor_location)
        row, col = self.cursor_location
        if self._follow:
            if cur < self._top:
                self._top = cur
            elif cur >= self._top + visible:
                self._top = cur - visible + 1
            if not self.wrap:  # yatay kaydırma: imleç görünür kalsın
                caret = self._width_of(p, self.lines[row], 0, col)
                if caret - self._scroll_x > width:
                    self._scroll_x = caret - width
                elif caret < self._scroll_x:
                    self._scroll_x = caret
            self._follow = False
        self._top = max(0, min(self._top, len(segs) - visible))
        sel = self.selection
        top = (p.row - p.text.height) // 2
        empty = len(self.lines) == 1 and not self.lines[0]
        with p.clip((c.x, c.y, c.w - 3, c.h)):
            for k in range(min(visible, len(segs) - self._top)):
                i = self._top + k
                r, s, e = segs[i]
                y = c.y + k * p.row
                line = self.lines[r]
                if focused and r == row:  # imlecin satırı hafifçe vurgulu
                    p.surface.fill(mix(p.panel_bg, th.raised, 0.4), (c.x, y, c.w - 3, p.row))
                if self.line_numbers and i == first[r]:
                    p.write(text_x - p.ch, y, [(str(r + 1), _PLAIN)], color=th.text if focused and r == row else th.faint,
                            right=True)
                x0 = text_x - self._scroll_x
                with p.clip((text_x, y, c.right - 3 - text_x, p.row)):
                    if sel is not None:
                        (r0, c0), (r1, c1) = sel
                        if r0 <= r <= r1:
                            a = max(s, c0) if r == r0 else s
                            b = min(e, c1) if r == r1 else e
                            xa = x0 + self._width_of(p, line, s, a)
                            xb = x0 + self._width_of(p, line, s, b) + (p.ch // 2 if r < r1 and b == len(line) else 0)
                            if xb > xa:
                                p.surface.fill(mix(th.bg, th.accent, 0.35), (xa, y + top, xb - xa, p.text.height))
                    p.write(x0, y, [(line[s:e], _PLAIN)])
                    if focused and i == cur and self._caret_on():  # blok imleç; altındaki harf ters renkte
                        cx = x0 + self._width_of(p, line, s, col)
                        under = line[col:col + 1] if col < e else ""
                        p.surface.fill(th.accent, (cx, y + top, self._cw(p, under) if under else p.ch, p.text.height))
                        if under:
                            p.write(cx, y, [(under, _PLAIN)], color=th.bg)
            if empty and self.placeholder:
                p.write(text_x + (p.ch if focused else 0), c.y, [(self.placeholder, _PLAIN)], color=th.faint)
        p.scrollbar(c.right - 2, c.y, visible * p.row, len(segs), visible, self._top, active=focused)
