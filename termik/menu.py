"""Menüler: menü çubuğu, açılır menü ve bağlam (sağ tık) menüsü.

    yield ui.MenuBar(
        ui.Menu("&Dosya", [ui.MenuItem("Kaydet", "save"), None, ui.MenuItem("Çık", "app.quit")]),
        ui.Menu("&Görünüm", [ui.MenuItem("Temayı değiştir", "next_theme")]),
    )

Öğeler bir eylem adıyla (@action) ya da fonksiyonla verilir; eylemin kısayolu menüde kendiliğinden
yazar, bulunamayan eylem soluk ve seçilemez görünür. None ayraçtır. "&" sonraki harfi kısayol yapar
(yoksa ilk harf): Alt+D Dosya menüsünü açar, menü açıkken harf öğeyi seçer. F10 ilk menüyü açar;
açıkken ←/→ komşu menüye geçer, fare başka bir başlığın üstüne gelince o açılır.

Bir bileşenin context_menu() metodu öğe döndürürse sağ tık (ya da Shift+F10, Menü tuşu) o menüyü
açar; app.open_menu(öğeler, (x, y)) istenen yerde açar.
"""

from __future__ import annotations

from typing import Callable

import pygame

from . import keys
from .events import Click, Key, MouseMove
from .fuzzy import fold
from .markup import escape
from .popup import Popup
from .theme import mix
from .widget import Widget


class MenuItem:
    """Menüdeki bir öğe. action bir eylem adı ("save", "app.quit") ya da çağrılabilir; eylem adının
    kısayolu kendiliğinden bulunur, key= ile ezilir. checked True ya da False ise solunda ✓ yeri açılır."""

    def __init__(self, label: str, action: str | Callable | None = None, *, key: str | None = None,
                 disabled: bool = False, checked: bool | None = None) -> None:
        self.label, self.action, self.key = label, action, key
        self.disabled, self.checked = disabled, checked

    def __repr__(self) -> str:
        return f"<MenuItem {self.label!r}>"


class Menu:
    """Menü çubuğundaki bir başlık ve öğeleri; "&Dosya" D harfini Alt+D kısayolu yapar."""

    def __init__(self, label: str, items: list[MenuItem | None]) -> None:
        self.label, self.items = label, list(items)


def hotkey(label: str) -> tuple[str, int]:
    """'&Dosya' → ('Dosya', 0): görünen yazı ve kısayol harfinin yeri ("&" yoksa ilk harf)."""
    i = label.find("&")
    if 0 <= i < len(label) - 1:
        return label[:i] + label[i + 1:], i
    return label, next((n for n, ch in enumerate(label) if ch.isalnum()), -1)


def _mark(text: str, at: int, tag: str) -> str:
    """Kısayol harfini vurgulu markup'a çevir: ('Dosya', 0, 'accent') → '[accent]D[/]osya'."""
    if at < 0 or not tag:
        return escape(text)
    return escape(text[:at]) + f"[{tag}]{escape(text[at])}[/]" + escape(text[at + 1:])


def resolve(item: MenuItem, origin: Widget) -> tuple[Callable | None, str | None]:
    """Öğenin çalıştıracağı fonksiyon (yoksa None) ve gösterilecek kısayol. Eylem adları origin'den
    yukarı doğru, "app." önekliler doğrudan uygulamada aranır."""
    if item.disabled or item.action is None:
        return None, item.key
    if callable(item.action):
        return item.action, item.key
    scope, _, name = item.action.rpartition(".")
    for node in ([origin.app] if scope == "app" else [origin, *origin.ancestors()]):
        info = type(node)._actions.get(name)
        if info is not None and not node.disabled:
            return getattr(node, name), item.key or (info.keys[0] if info.keys else None)
    return None, item.key


def run_entry(app, entry) -> None:
    """Menüden seçilen öğeyi çalıştır; menü kapandıktan sonra, odak eski yerindeyken çağrılır."""
    if isinstance(entry, tuple) and len(entry) == 3 and entry[1] is not None:
        app._call(entry[1])


class _MenuList(Widget):
    """Menü öğeleri: ↑/↓ gezer (soluk öğeleri atlar), ⏎ ya da kısayol harfi seçer, fare üstüne gelince
    imleç onu izler."""

    default_width = "auto"
    default_height = "auto"
    can_focus = True
    cursor = "hand"

    def __init__(self, items: list[MenuItem | None], origin: Widget) -> None:
        super().__init__()
        self.entries = [None if item is None else (item, *resolve(item, origin)) for item in items]
        self.current = next((i for i in range(len(self.entries)) if self._enabled(i)), -1)
        self._tops: list[int] = []

    def _enabled(self, i: int) -> bool:
        entry = self.entries[i]
        return entry is not None and entry[1] is not None

    def _popup(self) -> MenuPopup:
        return next(a for a in self.ancestors() if isinstance(a, MenuPopup))

    def move(self, step: int) -> None:
        if self.current < 0:
            return
        i = self.current
        for _ in range(len(self.entries)):
            i = (i + step) % len(self.entries)
            if self._enabled(i):
                self.current = i
                break
        self.refresh()

    def choose(self, i: int | None = None) -> None:
        i = self.current if i is None else i
        if 0 <= i < len(self.entries) and self._enabled(i):
            self._popup().dismiss(self.entries[i])

    # ── yerleşim ve çizim ────────────────────────────────

    def _checks(self) -> bool:
        return any(entry is not None and entry[0].checked is not None for entry in self.entries)

    def measure(self, p, width: int) -> tuple[int, int]:
        labels = max((p.text.width(escape(hotkey(e[0].label)[0])) for e in self.entries if e), default=0)
        shortcuts = max((p.small.width(keys.display(e[2])) for e in self.entries if e and e[2]), default=0)
        lead = p.ch * (3 if self._checks() else 1)
        w = lead + labels + (p.ch * 4 + shortcuts if shortcuts else p.ch * 2)
        return max(w, p.ch * 16), sum(p.row // 2 if e is None else p.row for e in self.entries)

    def render(self, p) -> None:
        th = p.theme
        c = self.content
        checks = self._checks()
        y = c.y
        self._tops = []
        for i, entry in enumerate(self.entries):
            self._tops.append(y)
            if entry is None:  # ayraç
                p.surface.fill(th.border, (c.x + p.ch // 2, y + p.row // 4, c.w - p.ch, 1))
                y += p.row // 2
                continue
            item, fn, key = entry
            enabled = fn is not None
            fg = p.selection((c.x, y, c.w, p.row), focused=self.has_focus) if i == self.current and enabled else None
            x = c.x + p.ch // 2
            if checks:
                if item.checked:
                    p.write(x, y, "✓", color=fg or th.green)
                x += p.ch * 2
            text, at = hotkey(item.label)
            p.write(x, y, _mark(text, at, ("u" if fg else "accent") if enabled else ""),
                    color=fg or (th.text if enabled else th.faint))
            if key:
                p.write(c.right - p.ch // 2, y, keys.display(key), color=fg or th.faint, font=p.small, right=True)
            y += p.row

    # ── klavye ve fare ───────────────────────────────────

    def on_key(self, event: Key) -> None:
        key = event.key
        bar = self._popup().bar
        if key in ("up", "down"):
            self.move(-1 if key == "up" else 1)
        elif key in ("home", "end"):
            order = range(len(self.entries)) if key == "home" else range(len(self.entries) - 1, -1, -1)
            self.current = next((i for i in order if self._enabled(i)), self.current)
            self.refresh()
        elif key in ("enter", "space"):
            self.choose()
        elif key in ("left", "right") and bar is not None:
            self._popup().dismiss(("switch", -1 if key == "left" else 1))
        elif event.char and not key.startswith(("ctrl+", "alt+", "altgr+", "meta+")):
            letter = fold(event.char)
            for i, entry in enumerate(self.entries):
                if self._enabled(i):
                    text, at = hotkey(entry[0].label)
                    if at >= 0 and fold(text[at]) == letter:
                        self.choose(i)
                        break
            else:
                return
        else:
            return
        event.stop()

    def _index_at(self, y: int) -> int | None:
        row = self.app.painter.row
        for i, top in enumerate(self._tops):
            if top <= y < top + (row // 2 if self.entries[i] is None else row):
                return i
        return None

    def on_mouse_move(self, event: MouseMove) -> None:
        i = self._index_at(event.y)
        if i is not None and self._enabled(i) and i != self.current:
            self.current = i
            self.refresh()

    def on_click(self, event: Click) -> None:
        i = self._index_at(event.y)
        if i is not None and self._enabled(i):
            event.stop()
            self.choose(i)


class MenuPopup(Popup):
    """Açılır menü. Seçilen öğe (öğe, fonksiyon, kısayol) olarak, menü çubuğundan açıldıysa komşu menüye
    geçiş ("switch", ±1) ya da ("open", sıra) olarak döner; Esc ve dışarı tık None döndürür."""

    def __init__(self, items: list[MenuItem | None], at, *, origin: Widget, bar: MenuBar | None = None,
                 index: int | None = None) -> None:
        super().__init__(at)
        self.list = _MenuList(items, origin)
        self.bar, self.index = bar, index

    def compose_body(self):
        yield self.list

    def on_mount(self) -> None:
        self.list.focus()

    def _title_at(self, pos) -> int | None:
        return self.bar.title_at(pos) if self.bar is not None else None

    def on_mouse_move(self, event: MouseMove) -> None:
        i = self._title_at(event.pos)  # fare menü çubuğunda başka bir başlığa geçti: o açılsın
        if i is not None and i != self.index:
            self.dismiss(("open", i))

    def outside(self, event) -> None:
        i = self._title_at(event.pos)
        self.dismiss(("open", i) if i is not None and i != self.index else None)


class MenuBar(Widget):
    """Pencerenin üstündeki menü çubuğu: Alt+kısayol harfi ya da F10 ile klavyeden, tıkla fareyle açılır."""

    default_height = "auto"

    def __init__(self, *menus: Menu, **kwargs) -> None:
        super().__init__(**kwargs)
        self.menus = list(menus)
        self._rects: list[pygame.Rect] = []
        self._open: int | None = None
        self._hover: int | None = None

    def on_mount(self) -> None:
        self.app._menubar = self

    def on_unmount(self) -> None:
        if self.app._menubar is self:
            self.app._menubar = None

    def measure(self, p, width: int) -> tuple[int, int]:
        return width, p.row

    def render(self, p) -> None:
        th = p.theme
        r = self.region
        p.round_rect(r, mix(th.bg, th.raised, 0.6), radius=0)
        x = r.x + p.ch // 2
        self._rects = []
        for i, menu in enumerate(self.menus):
            text, at = hotkey(menu.label)
            rect = pygame.Rect(x, r.y, p.text.width(escape(text)) + p.ch * 2, r.h)
            fg = None
            if i == self._open:
                fg = p.selection(rect)
            elif i == self._hover:
                p.hover(rect)
            p.write(x + p.ch, r.y + (r.h - p.row) // 2, _mark(text, at, "u" if fg else "accent"),
                    color=fg or th.text)
            self._rects.append(rect)
            x = rect.right

    def title_at(self, pos) -> int | None:
        return next((i for i, rect in enumerate(self._rects) if rect.collidepoint(pos)), None)

    def open(self, index: int) -> None:
        """index'inci menüyü aç; eylemler açılmadan önce odakta olan bileşenden yukarı aranır."""
        if not self.menus:
            return
        index %= len(self.menus)
        app = self.app
        anchor = self._rects[index] if index < len(self._rects) else self.region
        self._open = index
        app.push_screen(MenuPopup(self.menus[index].items, anchor, origin=app.focused or app.screen, bar=self,
                                  index=index), callback=self._closed)
        self.refresh()

    def _closed(self, result) -> None:
        index, self._open = self._open, None
        self.refresh()
        if isinstance(result, tuple) and result and result[0] == "switch":
            self.open(index + result[1])
        elif isinstance(result, tuple) and result and result[0] == "open":
            self.open(result[1])
        else:
            run_entry(self.app, result)

    def handle_key(self, key: str) -> bool:
        """Uygulamanın ilettiği tuş: F10 ilk menüyü, Alt+kısayol harfi o menüyü açar."""
        if key == "f10":
            self.open(0)
            return True
        if key.startswith("alt+") and len(key) == 5:
            letter = fold(key[-1])
            for i, menu in enumerate(self.menus):
                text, at = hotkey(menu.label)
                if at >= 0 and fold(text[at]) == letter:
                    self.open(i)
                    return True
        return False

    def on_click(self, event: Click) -> None:
        i = self.title_at(event.pos)
        if i is not None:
            event.stop()
            self.open(i)

    def on_mouse_move(self, event: MouseMove) -> None:
        i = self.title_at(event.pos)
        if i != self._hover:
            self._hover = i
            self.refresh()

    def on_mouse_leave(self) -> None:
        self._hover = None
        self.refresh()
