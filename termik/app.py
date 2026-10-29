"""Uygulama ve pencereleri: asyncio olay döngüsü, odak, fare, zamanlayıcılar, işçiler, bildirimler.

    class Merhaba(App):
        def compose(self):
            yield Static("Merhaba [bold accent]dünya[/]!")

    Merhaba().run()

Olay döngüsü asyncio üzerinde döner: işleyiciler ve eylemler `async def` olabilir. Bloklayan
işler run_worker() ile ayrı thread'e gider. Ekran yalnızca bir şey değişince çizilir; boştayken
döngü yalnızca olayları yoklar.

Her işletim sistemi penceresi bir Window'dur: ekran yığını, odak, fare, ipucu ve bildirimler
pencereye aittir. App ana penceredir, ek pencereler open_window() ile açılır. Tema, olay döngüsü,
zamanlayıcılar ve işçiler bütün pencerelerde ortaktır.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Iterable

import pygame

from . import keys, settings, system
from .draw import Painter
from .events import (Blur, Click, Drop, Focus, Key, MouseDown, MouseEnter, MouseLeave, MouseMove,
                     MouseScroll, MouseUp, TextInput)
from .fonts import default_font_paths
from .dialog import Dialog, PromptDialog
from .icon import prompt_icon
from .palette import Command, CommandPalette
from .theme import DENSITIES, THEMES, Theme, mix, with_look
from .widget import Screen, Widget, action

_CURSORS = {"hand": pygame.SYSTEM_CURSOR_HAND, "ibeam": pygame.SYSTEM_CURSOR_IBEAM}
_TOAST = {"info": ("•", "blue"), "ok": ("✓", "green"), "warn": ("⚠", "yellow"), "err": ("✗", "red")}
_MOUSE = frozenset({pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL})
_INPUT = _MOUSE | {pygame.KEYDOWN, pygame.KEYUP, pygame.TEXTINPUT, pygame.TEXTEDITING}
_DROP = frozenset({pygame.DROPBEGIN, pygame.DROPFILE, pygame.DROPTEXT, pygame.DROPCOMPLETE})


class Timer:
    """set_interval / set_timer'ın döndürdüğü zamanlayıcı; stop() ile durur."""

    def __init__(self, interval: float, callback: Callable, repeat: bool, owner: Widget) -> None:
        self.interval = max(0.0, interval)
        self.callback = callback
        self.repeat = repeat
        self.owner = owner
        self.due = time.monotonic() + self.interval
        self.active = True

    def stop(self) -> None:
        self.active = False


class _MainScreen(Screen):
    """Pencerenin compose()'unu taşıyan ana ekran."""

    def __init__(self, owner: Window, **kwargs) -> None:
        super().__init__(**kwargs)
        self._owner = owner

    def compose(self):
        return self._owner.compose()


class Window(Widget):
    """Bir işletim sistemi penceresi: kendi ekran yığını, odağı, faresi, ipucu ve bildirimleri vardır.

    App ana penceredir. Ek pencere için Window'dan türet, içini compose() ile kur:

        class Ayarlar(Window):
            TITLE = "Ayarlar"
            SIZE = (560, 380)

            def compose(self):
                yield Select(["okyanus", "orman"], id="tema")
                yield Button("Kapat", action="window.close")

        self.app.open_window(Ayarlar())                       # modal=True: kapanana kadar ötekiler bekler
        sonuç = await self.window.open_window_wait(Ayarlar())  # close(sonuç)'a verileni döndürür

    Bileşenler kendi pencerelerine self.window ile ulaşır: self.window.confirm(…), .notify(…),
    .ask_open(…). self.app her yerde uygulamadır, yani ana pencere.
    """

    TITLE = "termik"
    SIZE = (640, 440)    # pencere boyutu, ölçek 1.0'da piksel
    PADDING = (0.5, 2)   # ana ekranın kenar boşluğu: satır, karakter
    GAP = 0.5            # ana ekrandaki bileşenler arası boşluk, satır
    RESIZABLE = True
    ICON: str | Path | pygame.Surface | None = None  # None: temanın renginde komut istemi simgesi

    def __init__(self, *, title: str | None = None, size: tuple[int, int] | None = None,
                 icon: str | Path | pygame.Surface | None = None, id: str | None = None, classes: str = "") -> None:
        super().__init__(id=id, classes=classes)
        self._window = self
        self._title = title or self.TITLE
        self._size = size
        self._icon = icon if icon is not None else self.ICON
        self._native: pygame.Window | None = None  # açıkken işletim sistemi penceresi
        self._shown = False
        self._owner: Window | None = None  # bu pencereyi açan pencere
        self.modal = False
        self._blocked = False  # üstünde modal bir pencere (ya da işletim sisteminin diyaloğu) açık
        self._dialogs = 0      # açık yerel dosya diyaloğu sayısı
        self._close_callback: Callable | None = None
        self.focused: Widget | None = None
        self._focus_stack: list[Widget | None] = []
        self._hover: Widget | None = None
        self._pressed: Widget | None = None
        self._last_click: tuple[Widget, float, tuple[int, int]] | None = None  # çift tık için
        self._toasts: list[list] = []
        self._dirty = self._needs_layout = True
        self.frame_count = 0  # bu pencerede şimdiye kadar çizilen kare sayısı
        self._menubar = None  # ana ekrandaki MenuBar; Alt+harf ve F10 ona gider
        self._tip: tuple[str, tuple[int, int]] | None = None  # gösterilen ipucu ve fare konumu
        self._tip_timer: Timer | None = None
        self._tip_pos = (0, 0)
        self._drop: list | None = None  # DROPBEGIN ile DROPCOMPLETE arasında bırakılanlar

    # ── pencere ───────────────────────────────────────────

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        self._title = value
        if self._native is not None:
            self._native.title = value

    @property
    def native(self) -> pygame.Window | None:
        """Pencerenin pygame-ce karşılığı (açıkken): konum, boyut, always_on_top… için."""
        return self._native

    @property
    def is_open(self) -> bool:
        return self._native is not None

    @property
    def theme(self) -> Theme:
        return self.app.theme

    @property
    def painter(self) -> Painter | None:
        return self._app._painter if self._app is not None else None

    def set_icon(self, icon: str | Path | pygame.Surface | None) -> None:
        """Pencere simgesini değiştir: resim dosyası, pygame.Surface ya da None (temanın simgesi)."""
        self._icon = icon
        self._apply_icon()

    def _apply_icon(self) -> None:
        if self._native is None:
            return
        icon = self._icon
        try:
            if icon is None:
                theme = self.theme
                system.set_icon(self._native, lambda size: prompt_icon(theme, size))
                return
            image = icon if isinstance(icon, pygame.Surface) else pygame.image.load(str(icon))
            system.set_icon(self._native, lambda size: pygame.transform.smoothscale(image, (size, size)))
        except (pygame.error, OSError) as exc:
            self._app._report(exc)

    def open_window(self, window: Window, *, modal: bool = False, callback: Callable | None = None) -> Window:
        """Yeni bir pencere aç ve döndür; bu pencerenin ortasına yerleşir. modal=True ise o kapanana
        kadar bu pencere (ve ondan önce açılanlar) girdi almaz. close(sonuç) ile kapanınca
        callback(sonuç) çağrılır."""
        app = self.app
        if window._native is not None:
            raise RuntimeError(f"{window!r} zaten açık")
        if not app._running:
            raise RuntimeError("pencere açmak için uygulama çalışıyor olmalı")
        window._owner, window.modal, window._close_callback = self, modal, callback
        app._windows.append(window)
        window._create(app, window._size or window.SIZE, owner=self)
        app._focus_window = window
        app._sync_blocking()
        return window

    async def open_window_wait(self, window: Window, *, modal: bool = False) -> Any:
        """Pencereyi aç ve kapanmasını bekle; close(sonuç)'a verileni döndürür."""
        future = self.app._loop.create_future()
        self.open_window(window, modal=modal, callback=lambda result: future.done() or future.set_result(result))
        return await future

    def _create(self, app: App, size: tuple[int, int], owner: Window | None = None) -> None:
        """İşletim sistemi penceresini aç (ilk kare çizilene kadar gizli), ana ekranı kur ve bağla."""
        self._app = app
        pixels = (round(size[0] * app._scale), round(size[1] * app._scale))
        position = pygame.WINDOWPOS_CENTERED
        if owner is not None and owner._native is not None:  # açanın ortasına
            (ox, oy), (ow, oh) = owner._native.position, owner._native.size
            position = (ox + (ow - pixels[0]) // 2, oy + (oh - pixels[1]) // 2)
        flags = {} if app._headless else {"resizable": self.RESIZABLE, "hidden": True}
        self._native = pygame.Window(self._title, pixels, position, **flags)
        self._shown = False
        self._apply_icon()
        if self.modal and owner is not None and owner._native is not None:
            system.set_owner(self._native, owner._native)
        main = _MainScreen(self, padding=self.PADDING, gap=self.GAP)
        main.parent = self
        self.children = [main]
        self._mounted = True
        self._mount_tree(main)
        hook = getattr(self, "on_mount", None)
        if hook is not None:
            self._call(hook)
        self._layout_all()

    # ── dosya diyalogları ─────────────────────────────────

    async def ask_open(self, title: str = "Aç", *, filetypes=None, folder: str | Path | None = None,
                       multiple: bool = False) -> Path | list[Path] | None:
        """Açılacak dosyayı sor; vazgeçilirse None (multiple=True ise liste, vazgeçilirse boş).
        filetypes: [("Resimler", "*.png *.jpg"), ("Tümü", "*.*")]."""
        from .filedialog import ask
        return await ask(self, "open", title, filetypes=filetypes, folder=folder, multiple=multiple)

    async def ask_save(self, title: str = "Kaydet", *, filetypes=None, folder: str | Path | None = None,
                       name: str = "") -> Path | None:
        """Kaydedilecek yeri sor; dosya varsa üzerine yazmak için onay alınır."""
        from .filedialog import ask
        return await ask(self, "save", title, filetypes=filetypes, folder=folder, name=name)

    async def ask_folder(self, title: str = "Klasör seç", *, folder: str | Path | None = None) -> Path | None:
        """Bir klasör sor; vazgeçilirse None."""
        from .filedialog import ask
        return await ask(self, "folder", title, folder=folder)

    # ── ekranlar ──────────────────────────────────────────

    @property
    def screen(self) -> Screen:
        return self.children[-1]  # type: ignore[return-value]

    def push_screen(self, screen: Screen, callback: Callable | None = None) -> None:
        """Ekranı en üste koy; odak ona geçer. Ekran dismiss(sonuç) ile kapanınca callback(sonuç)
        çağrılır ve odak önceki yerine döner."""
        self._focus_stack.append(self.focused)
        self.set_focus(None)  # ekranın on_mount'u kendi odağını seçebilsin
        screen._dismiss_callback = callback
        screen.parent = self
        self.children.append(screen)
        self._mount_tree(screen)

    def pop_screen(self, result: Any = None) -> None:
        if len(self.children) <= 1:
            return
        screen = self.children.pop()
        callback, screen._dismiss_callback = screen._dismiss_callback, None
        self._unmount_tree(screen)
        screen.parent = None
        previous = self._focus_stack.pop() if self._focus_stack else None
        self.set_focus(previous if previous is not None and previous.is_mounted else None)
        if callback is not None:
            self._call(callback, result)

    async def push_screen_wait(self, screen: Screen) -> Any:
        """Ekranı aç ve kapanmasını bekle; dismiss(sonuç)'a verilen sonucu döndürür."""
        future = self.app._loop.create_future()
        self.push_screen(screen, lambda result: future.done() or future.set_result(result))
        return await future

    async def confirm(self, message: str, *, title: str = "Onay", yes: str = "Evet", no: str = "Vazgeç",
                      default: bool = True) -> bool:
        """Evet/hayır sorusu: `if await self.app.confirm("Silinsin mi?"): …`. Esc hayır sayılır."""
        dialog = Dialog(title, message, buttons=[(no, False), (yes, True)], default=1 if default else 0, cancel=False)
        return bool(await self.push_screen_wait(dialog))

    async def alert(self, message: str, *, title: str = "Bilgi", button: str = "Tamam") -> None:
        """Bilgi kutusu; kapatılınca döner."""
        await self.push_screen_wait(Dialog(title, message, buttons=[(button, None)]))

    async def prompt(self, message: str = "", *, title: str = "", value: str = "",
                     placeholder: str = "") -> str | None:
        """Tek satır yazı sor; Enter yazıyı, Esc None döndürür."""
        return await self.push_screen_wait(PromptDialog(title, message, value=value, placeholder=placeholder))

    def _mount_tree(self, root: Widget) -> None:
        """root ve altını bağla: compose'ları çalıştır, sonra on_mount'ları çocuklardan başlayarak çağır."""
        order: list[Widget] = []
        app = self._app

        def attach(widget: Widget) -> None:
            widget._app, widget._window = app, self
            widget._run_compose()
            for child in list(widget.children):
                attach(child)
            order.append(widget)

        attach(root)
        for widget in order:
            widget._mounted = True
            hook = getattr(widget, "on_mount", None)
            if hook is not None:
                widget._call(hook)
        self._invalidate(True)

    def _unmount_tree(self, root: Widget) -> None:
        for widget in list(root.walk()):
            for timer in widget._timers:
                timer.stop()
            widget._timers.clear()
            if widget._mounted:
                hook = getattr(widget, "on_unmount", None)
                if hook is not None:
                    widget._call(hook)
            widget._mounted = False
            if self.focused is widget:
                self.focused = None
            if self._hover is widget:
                self._hover = None
            if self._pressed is widget:
                self._pressed = None
            widget._app = widget._window = None
        self._invalidate(True)

    # ── odak ──────────────────────────────────────────────

    def focus_chain(self) -> list[Widget]:
        """Tab sırası: üstteki ekrandaki görünür, etkin, odaklanabilir bileşenler."""
        if not self.children:
            return []
        return [w for w in self.screen.walk(visible_only=True) if w.can_focus and not w.disabled]

    def set_focus(self, widget: Widget | None) -> None:
        if widget is self.focused:
            return
        old, self.focused = self.focused, widget
        if old is not None and old.is_mounted:
            old._handle_message(Blur())
        if widget is not None:
            widget._handle_message(Focus())
            for ancestor in widget.ancestors():  # kaydırılabilir atalar onu görünür alana getirsin
                ancestor._reveal(widget)
        self.refresh()

    def _move_focus(self, step: int) -> None:
        chain = self.focus_chain()
        if not chain:
            self.set_focus(None)
            return
        if self.focused in chain:
            i = chain.index(self.focused) + step
        else:
            i = 0 if step > 0 else -1
        self.set_focus(chain[i % len(chain)])

    def _focus_path(self) -> list[Widget]:
        """Odaktaki bileşenden pencereye kadar zincir (odak yoksa üstteki ekrandan)."""
        start = self.focused if self.focused is not None else (self.screen if self.children else self)
        return [start, *start.ancestors()]

    def active_bindings(self) -> list[tuple[str, str, Widget, str]]:
        """Şu an geçerli, gösterilecek kısayollar: [(tuş, kısa ad, sahibi, eylem adı)].

        Odaktaki bileşenden yukarı doğru toplanır; aynı tuş için en içteki kazanır.
        """
        seen: set[str] = set()
        out = []
        for node in self._focus_path():
            if node.disabled:
                continue
            for info in type(node)._actions.values():
                if not info.show or not info.keys or info.keys[0] in seen:
                    continue
                seen.update(info.keys)
                out.append((info.keys[0], info.hint or info.label, node, info.name))
        return out

    @action("Sonraki", key="tab", hint="sonraki", palette=False)
    def focus_next(self) -> None:
        self._move_focus(1)

    @action("Önceki", key="shift+tab", show=False, palette=False)
    def focus_previous(self) -> None:
        self._move_focus(-1)

    @action("Komut paleti", key="ctrl+p", hint="komutlar", priority=True, palette=False)
    def command_palette(self) -> None:
        """Paleti aç; açıksa kapat."""
        if isinstance(self.screen, CommandPalette):
            self.screen.dismiss()
        else:
            self.push_screen(CommandPalette(self._palette_commands()))

    def _palette_commands(self) -> list[Command]:
        """Odaktaki bileşenden yukarı @action'lar (aynı addan en içteki), sonra get_commands()."""
        commands, seen = [], set()
        for node in self._focus_path():
            if node.disabled:
                continue
            for info in type(node)._actions.values():
                if info.palette and info.name not in seen:
                    seen.add(info.name)
                    commands.append(Command(info.label, getattr(node, info.name), info.keys[0] if info.keys else None))
        commands.extend(self.get_commands())
        return commands

    def get_commands(self) -> Iterable[Command]:
        """Palete eklenecek komutlar; ek pencerede uygulamanınkiler (tema ve yoğunluk seçimi)."""
        if self._app is not None and self._app is not self:
            yield from self._app.get_commands()

    # ── kapanış ───────────────────────────────────────────

    @action("Pencereyi kapat", key="ctrl+w", hint="kapat")
    def request_close(self) -> None:
        """Kullanıcı kapatmak istedi (✕, Alt+F4, Ctrl+W): can_close() izin verirse pencere kapanır."""
        async def ask() -> None:
            allowed = self.can_close()
            if inspect.isawaitable(allowed):
                allowed = await allowed
            if allowed:
                self.close()

        self._call(ask)

    def can_close(self) -> bool:
        """Kullanıcı pencereyi kapatmak isteyince sorulur; False dönerse pencere açık kalır. async olabilir:

            async def can_close(self):
                return not self.changed or await self.confirm("Kaydedilmedi. Yine de kapatılsın mı?")
        """
        return True

    @action("Kapat", show=False, palette=False)
    def close(self, result: Any = None) -> None:
        """Pencereyi hemen kapat; open_window'a verilen callback (ya da open_window_wait) sonucu alır."""
        if self._app is not None and self._native is not None:
            self._app._close_window(self, result)

    @action("Çık", key="ctrl+q", hint="çık", priority=True)
    def quit(self) -> None:
        """Uygulamadan çık; ana pencerenin can_close()'u sorulur."""
        self.app.request_close()

    # ── menüler ve ipuçları ───────────────────────────────

    def open_menu(self, items: list, at, *, origin: Widget | None = None) -> None:
        """Yüzen menü aç: items MenuItem listesi (None ayraç), at bir nokta (x, y) ya da dikdörtgen.
        Seçilen öğe menü kapanınca çalışır; eylem adları origin'den (verilmezse odaktaki bileşenden)
        yukarı doğru aranır."""
        from .menu import MenuPopup, run_entry
        popup = MenuPopup(items, at, origin=origin or self.focused or self.screen)
        self.push_screen(popup, callback=lambda entry: run_entry(self, entry))

    def _menu_key(self, key: str) -> bool:
        """F10 ve Alt+harf menü çubuğunu, Shift+F10 ve Menü tuşu odaktakinin bağlam menüsünü açar."""
        if len(self.children) > 1:  # üstte palet, diyalog ya da açık bir menü var
            return False
        if key in ("shift+f10", "menu"):
            target = self.focused or self.screen
            return self._open_context(target, (target.region.x + self.painter.ch, target.region.y + self.painter.row),
                                      None)
        bar = self._menubar
        return bar is not None and bar.is_mounted and bar.display and bar.handle_key(key)

    def _open_context(self, start: Widget, at, event) -> bool:
        for widget in (start, *start.ancestors()):
            items = widget._call(widget.context_menu, event)
            if items:
                self.open_menu(items, at, origin=widget)
                return True
        return False

    def _schedule_tip(self, target: Widget | None, pos, dragging: bool) -> None:
        """Fare bir yerde durunca ipucunu göster: her hareket sayacı baştan başlatır."""
        if self._tip is not None and max(abs(pos[0] - self._tip_pos[0]), abs(pos[1] - self._tip_pos[1])) <= 4:
            return  # titreme ipucunu kapatmasın
        self._hide_tip()
        if dragging or target is None:
            return
        text = next((w.tooltip for w in (target, *target.ancestors()) if w.tooltip), None)
        if text:
            self._tip_pos = tuple(pos)
            self._tip_timer = self.set_timer(0.6, lambda: self._show_tip(text, tuple(pos)))

    def _show_tip(self, text: str, pos) -> None:
        self._tip_timer = None
        self._tip = (text, pos)
        self.refresh()

    def _hide_tip(self) -> None:
        if self._tip_timer is not None:
            self._tip_timer.stop()
            self._tip_timer = None
        if self._tip is not None:
            self._tip = None
            self.refresh()

    # ── girdi ─────────────────────────────────────────────

    def _key(self, key: str, char: str | None) -> None:
        self._hide_tip()
        event = Key(key, char)
        path = self._focus_path()
        for node in path:  # öncelikli eylemler (ör. ctrl+q) odak nerede olursa olsun önce
            info = node._binding(key, priority=True)
            if info is not None:
                node._call(getattr(node, info.name))
                return
        if self._menu_key(key):
            return
        typing = self.focused is not None and self.focused.accepts_text and event.is_printable
        for node in path:  # sonra odaktan yukarı: her düzeyde önce on_key, sonra eylemler
            node._handle_message(event)
            if event.stopped:
                return
            if not typing:
                info = node._binding(key, priority=False)
                if info is not None:
                    node._call(getattr(node, info.name))
                    return

    def _text(self, text: str) -> None:
        widget = self.focused
        if widget is not None and widget.accepts_text and not widget.disabled:
            widget._handle_message(TextInput(text))

    def _hit_test(self, pos) -> Widget | None:
        if not self.children:
            return None
        return self._hit(self.screen, pos, self.screen.region)

    def _hit(self, widget: Widget, pos, clip: pygame.Rect) -> Widget | None:
        if not widget.display or not clip.collidepoint(pos) or not widget.region.collidepoint(pos):
            return None
        inner = widget.child_clip().clip(clip)
        for child in reversed(widget.children):
            found = self._hit(child, pos, inner)
            if found is not None:
                return found
        return widget

    def _set_hover(self, target: Widget | None) -> None:
        if target is self._hover:
            return
        old, self._hover = self._hover, target
        if old is not None:
            old.hovered = False
            old._handle_message(MouseLeave())
        cursor = None
        if target is not None:
            target.hovered = True
            target._handle_message(MouseEnter())
            if not target.disabled:
                cursor = next((w.cursor for w in (target, *target.ancestors()) if w.cursor), None)
        try:
            pygame.mouse.set_cursor(_CURSORS.get(cursor, pygame.SYSTEM_CURSOR_ARROW))
        except pygame.error:
            pass
        self.refresh()

    def _mouse_move(self, pos, dragging: bool) -> None:
        target = self._hit_test(pos)
        self._set_hover(target)
        self._schedule_tip(target, pos, dragging)
        if dragging and self._pressed is not None:  # sürükleme basılan bileşene gider
            self._pressed._handle_message(MouseMove(*pos, 1))
        elif target is not None:
            target._handle_message(MouseMove(*pos))

    def _mouse_down(self, pos, button: int) -> None:
        self._hide_tip()
        target = self._hit_test(pos)
        self._pressed = target
        if target is None:
            return
        if button == 1:  # tıklanan yerdeki ilk odaklanabilir bileşen odağı alır
            focusable = next((w for w in (target, *target.ancestors()) if w.can_focus and not w.disabled), None)
            if focusable is not None:
                self.set_focus(focusable)
        event = target.post_message(MouseDown(*pos, button))
        if button == 3 and not event.stopped:  # sağ tık: ilk bağlam menüsü olan bileşenin menüsü
            self._open_context(target, pos, event)

    def _mouse_up(self, pos, button: int) -> None:
        target = self._hit_test(pos)
        pressed, self._pressed = self._pressed, None
        if target is not None:
            target.post_message(MouseUp(*pos, button))
        if pressed is not None and target is pressed and not pressed.disabled:
            now, last = time.monotonic(), self._last_click
            double = (last is not None and last[0] is pressed and now - last[1] < 0.4
                      and abs(pos[0] - last[2][0]) < 6 and abs(pos[1] - last[2][1]) < 6)
            self._last_click = None if double else (pressed, now, tuple(pos))
            pressed.post_message(Click(*pos, button, count=2 if double else 1))

    def _wheel(self, pos, dx: int, dy: int) -> None:
        self._hide_tip()
        target = self._hit_test(pos)
        if target is not None:
            target.post_message(MouseScroll(*pos, dx, dy))

    def _drop_event(self, ev) -> None:
        """Dosya yöneticisinden bırakılanlar: birlikte bırakılanlar tek bir Drop mesajında toplanır."""
        if ev.type == pygame.DROPBEGIN:
            self._drop = []
        elif ev.type == pygame.DROPCOMPLETE:
            items, self._drop = self._drop, None
            if items:
                self._dropped(items)
        else:
            item = Path(ev.file) if ev.type == pygame.DROPFILE else str(getattr(ev, "text", "") or "")
            if self._drop is None:
                self._dropped([item])
            else:
                self._drop.append(item)

    def _dropped(self, items: list, pos: tuple[int, int] | None = None) -> None:
        """Drop mesajını farenin altındaki bileşene gönder (SDL 2 bırakılan yeri bildirmez; fare sorulur)."""
        if pos is None:
            pos = (system.mouse_in(self._native) if self._native is not None else None) or pygame.mouse.get_pos()
        paths = [item for item in items if isinstance(item, Path)]
        text = "\n".join(item for item in items if isinstance(item, str) and item) or None
        if not paths and text is None:
            return
        target = self._hit_test(pos) or (self.screen if self.children else self)
        target.post_message(Drop(paths, text, *pos))
        self.refresh()

    # ── bildirimler ───────────────────────────────────────

    def notify(self, message: str, kind: str = "info", timeout: float = 3.0) -> None:
        """Sağ üstte kısa süreli bildirim. kind: info, ok, warn, err."""
        toast = [message, "err" if kind == "error" else kind]
        self._toasts.append(toast)

        def expire() -> None:
            self._toasts = [t for t in self._toasts if t is not toast]
            self.refresh()

        if self._app is not None and self._app._loop is not None:
            self.set_timer(timeout, expire)
        self.refresh()

    def _invalidate(self, layout: bool) -> None:
        self._dirty = True
        if layout:
            self._needs_layout = True

    # ── yerleşim ve çizim ─────────────────────────────────

    def _layout_all(self) -> None:
        p = self.painter
        surface = self._native.get_surface()
        p.surface = surface
        for screen in self.children:
            screen._layout(p, surface.get_rect())
        self._needs_layout = False
        self._dirty = True
        chain = self.focus_chain()
        if self.focused is not None and self.focused not in chain:
            self.set_focus(None)
        if self.focused is None and chain:
            self.set_focus(chain[0])
        # yerleşim değişince farenin altındaki bileşen de değişmiş olabilir
        if self._app._mouse_window is self and not self._blocked and pygame.mouse.get_focused():
            self._set_hover(self._hit_test(pygame.mouse.get_pos()))

    def _render(self) -> None:
        p = self.painter
        surface = self._native.get_surface()
        p.surface = surface
        full = surface.get_rect()
        surface.set_clip(None)
        surface.fill(p.theme.bg)
        for screen in self.children:
            if screen.modal and screen.veil:
                veil = pygame.Surface(full.size, pygame.SRCALPHA)
                veil.fill((*p.theme.bg, 175))
                surface.set_clip(None)
                surface.blit(veil, (0, 0))
            self._paint(screen, full)
        surface.set_clip(None)
        if self._tip is not None:
            self._paint_tip(p, *self._tip)
        self._paint_toasts(p)
        self._native.flip()
        if not self._shown:  # ilk kare hazır: boş beyaz pencere görünmesin diye şimdi göster
            self._shown = True
            self._native.show()
        self._dirty = False
        self.frame_count += 1

    def _paint(self, widget: Widget, clip: pygame.Rect) -> None:
        if not widget.display or widget.region.w <= 0 or widget.region.h <= 0:
            return
        area = widget.region.clip(clip)
        if area.w <= 0 or area.h <= 0:
            return
        self.painter.surface.set_clip(area)
        try:
            widget.render(self.painter)
        except Exception as exc:
            self._app._report(exc)
        inner = widget.child_clip().clip(clip)
        for child in widget.children:
            self._paint(child, inner)

    def _paint_tip(self, p: Painter, text: str, pos) -> None:
        """İpucu baloncuğu: farenin sağ altında (yer yoksa üstünde), pencereden taşmadan."""
        th = p.theme
        f = p.small
        lines = f.wrap(text, p.ch * 44)
        w = max(f.width(line) for line in lines) + p.ch * 2
        h = len(lines) * f.height + p.row // 2
        width, height = p.surface.get_size()
        x = max(4, min(pos[0] + p.ch, width - w - 4))
        y = pos[1] + p.row
        if y + h > height - 4:
            y = max(4, pos[1] - h - p.row // 2)
        rect = pygame.Rect(x, y, w, h)
        p.round_rect(rect, mix(th.bg, th.raised, 0.8), radius=min(th.radius, 4))
        p.outline(rect, th.border, radius=min(th.radius, 4))
        for i, line in enumerate(lines):
            f.draw(p.surface, x + p.ch, y + p.row // 4 + i * f.height, line, color=th.text)

    def _paint_toasts(self, p: Painter) -> None:
        th = p.theme
        width = p.surface.get_width()
        px, py = p.pad
        y = round(p.row * 0.6)
        bar = self._menubar
        if bar is not None and bar.is_mounted:  # menü çubuğunun üstüne binmesin
            y = max(y, bar.region.bottom + p.row // 3)
        for message, kind in self._toasts[-4:]:
            icon, color = _TOAST.get(kind, _TOAST["info"])
            spans = p.text.elide(f"[{color}]{icon}[/] {message}", width // 2)
            w, h = p.text.width(spans) + px * 2, p.row + py
            rect = pygame.Rect(width - w - p.ch * 2, y, w, h)
            p.shadow(rect)
            p.round_rect(rect, mix(th.bg, th.raised, 0.7))
            p.outline(rect, th.color(color) or th.accent)
            p.write(rect.x + px, rect.y + (h - p.row) // 2, spans)
            y += h + p.row // 3


class App(Window):
    """Uygulamanın kökü ve ana penceresi. compose() ile arayüzü kur, run() ile çalıştır."""

    SIZE = (1200, 760)

    def __init__(self, *, theme: str | None = None, look: str | None = None, density: str | None = None,
                 title: str | None = None, icon: str | Path | pygame.Surface | None = None,
                 dialogs: str | None = None, **tokens) -> None:
        """theme, look, density, dialogs ve biçim belirteçleri verilmezse kullanıcının tercihleri (ayar
        dosyası, TERMIK_* ortam değişkenleri) geçerli olur; onlar da yoksa okyanus · terminal · rahat
        ve işletim sisteminin dosya diyalogları."""
        super().__init__(title=title, icon=icon)
        settings.check_names(theme=theme, look=look, density=density, dialogs=dialogs)
        prefs = settings.preferences()
        self._theme_name = theme or prefs.get("theme", "okyanus")
        self._look = look or prefs.get("look", "terminal")
        self._density = density or prefs.get("density", "rahat")
        self._tokens = {**prefs["tokens"], **tokens}
        self.dialogs = dialogs or prefs.get("dialogs", "native")  # dosya diyalogları: native · builtin
        self._painter: Painter | None = None
        self._app = self
        self._loop: asyncio.AbstractEventLoop | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._all_timers: list[Timer] = []
        self._tasks: set[asyncio.Future] = set()
        self._errors: list[BaseException] = []
        self._reported: set[tuple] = set()
        self._running = False
        self._headless = False
        self._result: Any = None
        self._scale = 1.0
        self._active_until = 0.0
        self._windows: list[Window] = []           # açık pencereler, açılış sırasıyla (ilki ana pencere)
        self._focus_window: Window | None = None   # klavye odağındaki pencere
        self._mouse_window: Window | None = None   # farenin üstünde olduğu pencere

    # ── tema ──────────────────────────────────────────────

    def _make_theme(self) -> Theme:
        return with_look(THEMES[self._theme_name], self._look, density=self._density,
                         **self._tokens).scaled(self._scale)

    @property
    def theme(self) -> Theme:
        return self._painter.theme if self._painter is not None else self._make_theme()

    @property
    def look(self) -> str:
        return self._look

    @property
    def density(self) -> str:
        return self._density

    def set_theme(self, name: str | None = None, *, look: str | None = None, density: str | None = None,
                  **tokens) -> None:
        """Renk temasını, görünümü, yoğunluğu ya da tek tek biçim belirteçlerini değiştir; bütün
        pencerelere (ve temaya uyan pencere simgelerine) yansır."""
        settings.check_names(theme=name, look=look, density=density)
        if name is not None:
            self._theme_name = name
        if look is not None:
            self._look = look
        if density is not None:
            self._density = density
        self._tokens.update(tokens)
        if self._painter is not None:
            self._painter.set_theme(self._make_theme())
            for window in self._windows:
                window._invalidate(True)
                if window._icon is None:
                    window._apply_icon()

    def get_commands(self) -> Iterable[Command]:
        """Palete eklenecek komutlar. Varsayılan: tema ve yoğunluk seçimi; ezilip genişletilebilir."""
        for name in THEMES:
            if name != self.theme.name:
                yield Command(f"Tema: {name}", functools.partial(self.set_theme, name))
        for name in DENSITIES:
            if name != self.density:
                yield Command(f"Yoğunluk: {name}", functools.partial(self.set_theme, density=name))

    # ── pencereler ───────────────────────────────────────

    @property
    def windows(self) -> list[Window]:
        """Açık pencereler, açılış sırasıyla; ilki ana pencere (uygulamanın kendisi)."""
        return list(self._windows)

    @property
    def active_window(self) -> Window:
        """Klavye odağındaki pencere (bilinmiyorsa ana pencere)."""
        window = self._focus_window
        return window if window is not None and window._native is not None else self

    @action("Kapat", show=False, palette=False)
    def request_close(self) -> None:
        """Ana pencerede Ctrl+W yok (Ctrl+Q çıkar); ✕ ve Alt+F4 can_close()'u sorup uygulamayı kapatır."""
        super().request_close()

    def close(self, result: Any = None) -> None:
        """Ana pencere kapanınca uygulama da kapanır."""
        self.exit(result)

    def exit(self, result: Any = None) -> None:
        """Uygulamayı kapat; run() bu sonucu döndürür."""
        self._result = result
        self._running = False

    def _close_window(self, window: Window, result: Any, *, refocus: bool = True) -> None:
        self._windows.remove(window)
        self._sync_blocking()  # sahibi önce yeniden etkinleşsin; yoksa Windows odağı başka uygulamaya verir
        for screen in reversed(list(window.children)):
            window._unmount_tree(screen)
        hook = getattr(window, "on_unmount", None)
        if hook is not None:
            window._call(hook)
        for timer in window._timers:
            timer.stop()
        window._timers.clear()
        window._mounted = False
        window.children = []
        native, window._native = window._native, None
        system.forget(native)
        native.destroy()
        owner = window._owner if window._owner is not None and window._owner._native is not None else self
        if self._focus_window is window:
            self._focus_window = owner
            if refocus and owner._native is not None:
                owner._native.focus()
        if self._mouse_window is window:
            self._mouse_window = None
        callback, window._close_callback = window._close_callback, None
        window._app = None
        if callback is not None:
            owner._call(callback, result)

    def _blocking(self, window: Window) -> bool:
        """Pencere girdi alamaz mı: ondan sonra açılmış modal bir pencere ya da açık bir yerel diyalog var."""
        if window._dialogs:
            return True
        i = self._windows.index(window)
        return any(w.modal for w in self._windows[i + 1:])

    def _sync_blocking(self) -> None:
        for window in self._windows:
            blocked = self._blocking(window)
            if blocked == window._blocked:
                continue
            window._blocked = blocked
            if not window._dialogs:  # yerel diyalog sahibini kendisi kilitler
                system.set_enabled(window._native, not blocked)
            if blocked:
                window._set_hover(None)
                window._hide_tip()
                window._pressed = None

    def _raise_modal(self) -> None:
        """Kilitli bir pencereye tıklandı: üstteki modal pencereyi öne getir."""
        top = next((w for w in reversed(self._windows) if w.modal), None)
        if top is not None and top._native is not None:
            top._native.focus()
            try:
                top._native.flash(pygame.FLASH_BRIEFLY)
            except (pygame.error, AttributeError):
                pass

    def _event_window(self, ev) -> Window | None:
        """Olayın ait olduğu pencere; olay pencere bildirmiyorsa farenin ya da klavyenin olduğu."""
        native = getattr(ev, "window", None)
        if native is not None:
            return next((w for w in self._windows if w._native is native), None)
        if hasattr(ev, "window") and ev.type not in _INPUT and ev.type not in _DROP:
            return None  # pencere olayı ama penceresi artık yok
        if ev.type in _MOUSE:
            return self._mouse_window or self.active_window
        return self.active_window

    # ── girdi ─────────────────────────────────────────────

    def _process_events(self) -> None:
        for ev in pygame.event.get():
            self._active_until = time.monotonic() + 0.5
            t = ev.type
            if t == pygame.QUIT:
                self.request_close()
                continue
            window = self._event_window(ev)
            if window is None:  # kapanmış bir pencereden kalan olay
                continue
            if t == pygame.WINDOWCLOSE:
                if window._blocked:
                    self._raise_modal()
                else:
                    window.request_close()
            elif t == pygame.WINDOWFOCUSGAINED:
                self._focus_window = window
            elif t == pygame.WINDOWENTER:
                self._mouse_window = window
            elif t == pygame.WINDOWLEAVE:
                if self._mouse_window is window:
                    self._mouse_window = None
                window._set_hover(None)
                window._hide_tip()
            elif t in (pygame.WINDOWRESIZED, pygame.WINDOWSIZECHANGED):
                window._invalidate(True)
            elif t == pygame.WINDOWEXPOSED:
                window._invalidate(False)
            elif t in _DROP:
                if not window._blocked:
                    window._drop_event(ev)
            elif t in _INPUT and window._blocked:
                if t == pygame.MOUSEBUTTONDOWN:
                    self._raise_modal()
            elif t == pygame.KEYDOWN:
                window._key(keys.from_event(ev), ev.unicode or None)
            elif t == pygame.TEXTINPUT:
                window._text(ev.text)
            elif t == pygame.MOUSEMOTION:
                self._mouse_window = window
                window._mouse_move(ev.pos, bool(ev.buttons[0]))
            elif t == pygame.MOUSEBUTTONDOWN and ev.button in (1, 2, 3):
                window._mouse_down(ev.pos, ev.button)
            elif t == pygame.MOUSEBUTTONUP and ev.button in (1, 2, 3):
                window._mouse_up(ev.pos, ev.button)
            elif t == pygame.MOUSEWHEEL:
                window._wheel(pygame.mouse.get_pos(), ev.x, ev.y)

    # ── zamanlayıcılar, görevler, işçiler ─────────────────

    def _add_timer(self, seconds: float, callback: Callable, repeat: bool, owner: Widget) -> Timer:
        timer = Timer(seconds, callback, repeat, owner)
        self._all_timers.append(timer)
        owner._timers.append(timer)
        return timer

    def _run_timers(self) -> None:
        now = time.monotonic()
        for timer in list(self._all_timers):
            if not timer.active:
                self._all_timers.remove(timer)
                continue
            if now < timer.due:
                continue
            if timer.repeat:
                timer.due += timer.interval
                if timer.due <= now:  # geride kaldıysa telafi etmeye çalışma
                    timer.due = now + timer.interval
            else:
                timer.active = False
            timer.owner._call(timer.callback)

    def run_worker(self, fn: Callable, *args, **kwargs) -> asyncio.Future:
        """Coroutine fonksiyonunu görev olarak, sıradan fonksiyonu ayrı thread'de çalıştır.

        Dönen nesne await edilebilir. Hata olursa ekranda bildirim de gösterilir.
        """
        if inspect.iscoroutinefunction(fn):
            future = self._loop.create_task(fn(*args, **kwargs))
        else:
            future = self._loop.run_in_executor(self._executor, functools.partial(fn, *args, **kwargs))
        self._track(future)
        return future

    def call_from_thread(self, fn: Callable, *args) -> None:
        """Başka bir thread'den arayüzü güncellemek için: fn ana döngüde çağrılır."""
        self._loop.call_soon_threadsafe(self._call, fn, *args)

    def _spawn(self, awaitable) -> None:
        self._track(asyncio.ensure_future(awaitable))

    def _track(self, future: asyncio.Future) -> None:
        self._tasks.add(future)
        future.add_done_callback(self._task_done)

    def _task_done(self, future: asyncio.Future) -> None:
        self._tasks.discard(future)
        if not future.cancelled() and future.exception() is not None:
            self._report(future.exception())
        for window in self._windows:  # işler genelde durumu değiştirir
            window.refresh()

    def _report(self, exc: BaseException) -> None:
        """İşleyicideki hatayı göster: konsola iz, kullanıcının baktığı pencerede bildirim. Aynı hata bir kez."""
        key = (type(exc), str(exc))
        if key in self._reported:
            return
        self._reported.add(key)
        self._errors.append(exc)
        traceback.print_exception(exc)
        self.active_window.notify(f"{type(exc).__name__}: {exc}", "err", timeout=6)

    # ── döngü ─────────────────────────────────────────────

    def run(self, *, size: tuple[int, int] | None = None) -> Any:
        """Pencereyi aç ve kapanana kadar çalıştır; exit()'e verilen sonucu döndürür."""
        return asyncio.run(self._main(size))

    async def _main(self, size: tuple[int, int] | None, headless: bool = False) -> Any:
        self._startup(size, headless=headless)
        try:
            while self._running:
                self._tick()
                await asyncio.sleep(self._sleep_time())
        finally:
            self._shutdown()
        return self._result

    @asynccontextmanager
    async def run_test(self, size: tuple[int, int] = (1100, 700)):
        """Pencere açmadan (SDL'in sahte sürücüsüyle) başlat; uygulamayı süren bir Pilot verir."""
        self._startup(size, headless=True)
        try:
            self._tick()
            yield Pilot(self)
        finally:
            self._shutdown()

    def _startup(self, size: tuple[int, int] | None, headless: bool) -> None:
        self._loop = asyncio.get_running_loop()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="termik")
        self._headless = headless
        if headless:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
        else:  # ölçekli ekranlarda Windows pencereyi bulanık büyütmesin
            os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")
        os.environ.setdefault("SDL_QUIT_ON_LAST_WINDOW_CLOSE", "0")  # kapatmayı can_close() karara bağlasın
        pygame.init()
        self._scale = 1.0 if headless else system.dpi_scale()
        pygame.key.set_repeat(400, 35)
        self._painter = Painter(pygame.Surface((1, 1)), self._make_theme(), default_font_paths())
        self._windows = [self]
        self._focus_window = self
        self._running = True
        self._create(self, size or self.SIZE)

    def _shutdown(self) -> None:
        self._running = False
        for task in list(self._tasks):
            task.cancel()
        for window in reversed(self._windows[1:]):
            self._close_window(window, None, refocus=False)
        for screen in list(self.children):
            self._unmount_tree(screen)
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
        if self._native is not None:
            system.forget(self._native)
            self._native = None
        pygame.quit()

    def _tick(self) -> None:
        self._process_events()
        self._run_timers()
        for window in list(self._windows):
            if window._needs_layout:
                window._layout_all()
            if window._dirty:
                window._render()

    def _sleep_time(self) -> float:
        """Girdiden hemen sonra sık (60 Hz), boşta seyrek (30 Hz) yokla; zamanlayıcıyı kaçırma."""
        now = time.monotonic()
        wait = 1 / 60 if now < self._active_until else 1 / 30
        due = min((t.due for t in self._all_timers if t.active), default=now + wait)
        return max(0.001, min(wait, due - now))


class Pilot:
    """Testler için: uygulamayı pencere açmadan sürer.

        async with app.run_test() as pilot:
            await pilot.press("tab", "enter")
            await pilot.type("merhaba")
            await pilot.click("#tamam")

    Tuşlar klavye odağındaki pencereye (app.active_window) gider; tıklamalar hedef bileşenin
    penceresine. Seçiciler önce etkin pencerede, sonra ötekilerde aranır.
    """

    def __init__(self, app: App) -> None:
        self.app = app

    async def pause(self, seconds: float = 0.0) -> None:
        """Olay döngüsünü en az `seconds` saniye döndür: zamanlayıcılar, görevler, çizim."""
        end = time.monotonic() + seconds
        while True:
            self.app._tick()
            await asyncio.sleep(0.005)
            if time.monotonic() >= end:
                break
        self.app._tick()

    async def wait_until(self, predicate: Callable[[], bool], timeout: float = 5.0) -> None:
        end = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > end:
                raise TimeoutError("koşul zamanında sağlanmadı")
            self.app._tick()
            await asyncio.sleep(0.01)
        self.app._tick()

    async def press(self, *names: str) -> None:
        """Tuşlara bas: "tab", "shift+tab", "ctrl+q", "a"… Harfler yazı olarak da gider."""
        for name in names:
            window = self.app.active_window
            key = keys.normalize(name)
            char = " " if key == "space" else (key if len(key) == 1 else None)
            window._key(key, char)
            if char is not None:
                window._text(char)
            await self.pause()

    async def type(self, text: str) -> None:
        for ch in text:
            window = self.app.active_window
            low = ch.lower()
            window._key("space" if ch == " " else (low if len(low) == 1 else ch), ch)
            window._text(ch)
            await self.pause()

    def _target(self, target) -> Widget:
        if not isinstance(target, (str, type)):
            return target
        active = self.app.active_window
        for window in (active, *(w for w in self.app.windows if w is not active)):
            try:
                return window.query_one(target)
            except LookupError:
                continue
        raise LookupError(f"bulunamadı: {target!r}")

    @staticmethod
    def _point(widget: Widget, offset: tuple[int, int] | None) -> tuple[int, int]:
        return (widget.region.x + offset[0], widget.region.y + offset[1]) if offset else widget.region.center

    async def click(self, target, *, offset: tuple[int, int] | None = None, button: int = 1) -> None:
        widget = self._target(target)
        window, pos = widget.window, self._point(widget, offset)
        window._mouse_move(pos, False)
        window._mouse_down(pos, button)
        window._mouse_up(pos, button)
        await self.pause()

    async def hover(self, target, *, offset: tuple[int, int] | None = None) -> None:
        widget = self._target(target)
        widget.window._mouse_move(self._point(widget, offset), False)
        await self.pause()

    async def scroll(self, target, dy: int) -> None:
        widget = self._target(target)
        widget.window._wheel(widget.region.center, 0, dy)
        await self.pause()

    async def drop(self, target, *items: str | Path, offset: tuple[int, int] | None = None) -> None:
        """Bileşenin üstüne dosya yöneticisinden bırakılmış gibi Path'ler (dosyalar) ya da str'ler (yazı) bırak."""
        widget = self._target(target)
        widget.window._dropped(list(items), self._point(widget, offset))
        await self.pause()

    def snapshot(self, path: str, window: Window | None = None) -> None:
        """Pencereyi (verilmezse ana pencereyi) PNG olarak kaydet."""
        window = window or self.app
        window._render()
        pygame.image.save(window._native.get_surface(), path)
