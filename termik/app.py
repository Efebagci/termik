"""Uygulama: pencere, asyncio olay döngüsü, odak, fare, zamanlayıcılar, işçiler, bildirimler.

    class Merhaba(App):
        def compose(self):
            yield Static("Merhaba [bold accent]dünya[/]!")

    Merhaba().run()

Olay döngüsü asyncio üzerinde döner: işleyiciler ve eylemler `async def` olabilir. Bloklayan
işler run_worker() ile ayrı thread'e gider. Ekran yalnızca bir şey değişince çizilir; boştayken
döngü yalnızca olayları yoklar.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Callable, Iterable

import pygame

from . import keys
from .draw import Painter
from .events import (Blur, Click, Focus, Key, MouseDown, MouseEnter, MouseLeave, MouseMove,
                     MouseScroll, MouseUp, TextInput)
from .fonts import default_font_paths
from .dialog import Dialog, PromptDialog
from .palette import Command, CommandPalette
from .theme import DENSITIES, THEMES, Theme, mix, with_look
from .widget import Screen, Widget, action

_CURSORS = {"hand": pygame.SYSTEM_CURSOR_HAND, "ibeam": pygame.SYSTEM_CURSOR_IBEAM}
_TOAST = {"info": ("•", "blue"), "ok": ("✓", "green"), "warn": ("⚠", "yellow"), "err": ("✗", "red")}


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
    """Uygulamanın compose()'unu taşıyan ana ekran."""

    def __init__(self, owner: App, **kwargs) -> None:
        super().__init__(**kwargs)
        self._owner = owner

    def compose(self):
        return self._owner.compose()


class App(Widget):
    """Uygulamanın kökü. compose() ile arayüzü kur, run() ile çalıştır."""

    TITLE = "termik"
    SIZE = (1200, 760)   # pencere boyutu, ölçek 1.0'da piksel
    PADDING = (0.5, 2)   # ana ekranın kenar boşluğu: satır, karakter
    GAP = 0.5            # ana ekrandaki bileşenler arası boşluk, satır

    def __init__(self, *, theme: str = "okyanus", look: str = "terminal", density: str = "rahat",
                 title: str | None = None, **tokens) -> None:
        super().__init__()
        self.title = title or self.TITLE
        self._theme_name, self._look, self._density = theme, look, density
        self._tokens = dict(tokens)
        self.painter: Painter | None = None
        self.focused: Widget | None = None
        self._app = self
        self._loop: asyncio.AbstractEventLoop | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._all_timers: list[Timer] = []
        self._tasks: set[asyncio.Future] = set()
        self._toasts: list[list] = []
        self._errors: list[BaseException] = []
        self._reported: set[tuple] = set()
        self._hover: Widget | None = None
        self._pressed: Widget | None = None
        self._last_click: tuple[Widget, float, tuple[int, int]] | None = None  # çift tık için
        self._focus_stack: list[Widget | None] = []
        self.frame_count = 0  # şimdiye kadar çizilen kare sayısı
        self._dirty = self._needs_layout = True
        self._running = False
        self._result: Any = None
        self._scale = 1.0
        self._active_until = 0.0

    # ── tema ──────────────────────────────────────────────

    def _make_theme(self) -> Theme:
        return with_look(THEMES[self._theme_name], self._look, density=self._density,
                         **self._tokens).scaled(self._scale)

    @property
    def theme(self) -> Theme:
        return self.painter.theme if self.painter is not None else self._make_theme()

    @property
    def density(self) -> str:
        return self._density

    def set_theme(self, name: str | None = None, *, density: str | None = None, **tokens) -> None:
        """Renk temasını, yoğunluğu ya da tek tek biçim belirteçlerini değiştir."""
        if name is not None:
            self._theme_name = name
        if density is not None:
            self._density = density
        self._tokens.update(tokens)
        if self.painter is not None:
            self.painter.set_theme(self._make_theme())
            self.refresh(layout=True)

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
        future = self._loop.create_future()
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

        def attach(widget: Widget) -> None:
            widget._app = self
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
            widget._app = None
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
        """Odaktaki bileşenden uygulamaya kadar zincir (odak yoksa üstteki ekrandan)."""
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
        """Palete eklenecek komutlar. Varsayılan: tema ve yoğunluk seçimi; ezilip genişletilebilir."""
        for name in THEMES:
            if name != self.theme.name:
                yield Command(f"Tema: {name}", functools.partial(self.set_theme, name))
        for name in DENSITIES:
            if name != self.density:
                yield Command(f"Yoğunluk: {name}", functools.partial(self.set_theme, density=name))

    @action("Çık", key="ctrl+q", hint="çık", priority=True)
    def quit(self) -> None:
        self.exit()

    def exit(self, result: Any = None) -> None:
        """Uygulamayı kapat; run() bu sonucu döndürür."""
        self._result = result
        self._running = False

    # ── girdi ─────────────────────────────────────────────

    def _process_events(self) -> None:
        for ev in pygame.event.get():
            self._active_until = time.monotonic() + 0.5
            t = ev.type
            if t == pygame.QUIT:
                self.exit()
            elif t == pygame.KEYDOWN:
                self._key(keys.from_event(ev), ev.unicode or None)
            elif t == pygame.TEXTINPUT:
                self._text(ev.text)
            elif t == pygame.MOUSEMOTION:
                self._mouse_move(ev.pos, bool(ev.buttons[0]))
            elif t == pygame.MOUSEBUTTONDOWN and ev.button in (1, 2, 3):
                self._mouse_down(ev.pos, ev.button)
            elif t == pygame.MOUSEBUTTONUP and ev.button in (1, 2, 3):
                self._mouse_up(ev.pos, ev.button)
            elif t == pygame.MOUSEWHEEL:
                self._wheel(pygame.mouse.get_pos(), ev.x, ev.y)
            elif t == pygame.WINDOWLEAVE:
                self._set_hover(None)
            elif t in (pygame.VIDEORESIZE, pygame.WINDOWRESIZED, pygame.WINDOWSIZECHANGED):
                self._invalidate(True)
            elif t == pygame.WINDOWEXPOSED:
                self._invalidate(False)

    def _key(self, key: str, char: str | None) -> None:
        event = Key(key, char)
        path = self._focus_path()
        for node in path:  # öncelikli eylemler (ör. ctrl+q) odak nerede olursa olsun önce
            info = node._binding(key, priority=True)
            if info is not None:
                node._call(getattr(node, info.name))
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
        if dragging and self._pressed is not None:  # sürükleme basılan bileşene gider
            self._pressed._handle_message(MouseMove(*pos, 1))
        elif target is not None:
            target._handle_message(MouseMove(*pos))

    def _mouse_down(self, pos, button: int) -> None:
        target = self._hit_test(pos)
        self._pressed = target
        if target is None:
            return
        if button == 1:  # tıklanan yerdeki ilk odaklanabilir bileşen odağı alır
            focusable = next((w for w in (target, *target.ancestors()) if w.can_focus and not w.disabled), None)
            if focusable is not None:
                self.set_focus(focusable)
        target.post_message(MouseDown(*pos, button))

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
        target = self._hit_test(pos)
        if target is not None:
            target.post_message(MouseScroll(*pos, dx, dy))

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
        self.refresh()  # işler genelde durumu değiştirir

    def _report(self, exc: BaseException) -> None:
        """İşleyicideki hatayı göster: konsola iz, ekrana bildirim. Aynı hata bir kez."""
        key = (type(exc), str(exc))
        if key in self._reported:
            return
        self._reported.add(key)
        self._errors.append(exc)
        traceback.print_exception(exc)
        self.notify(f"{type(exc).__name__}: {exc}", "err", timeout=6)

    def notify(self, message: str, kind: str = "info", timeout: float = 3.0) -> None:
        """Sağ üstte kısa süreli bildirim. kind: info, ok, warn, err."""
        toast = [message, "err" if kind == "error" else kind]
        self._toasts.append(toast)

        def expire() -> None:
            self._toasts = [t for t in self._toasts if t is not toast]
            self.refresh()

        if self._loop is not None:
            self.set_timer(timeout, expire)
        self.refresh()

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
        if headless:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
        else:  # ölçekli ekranlarda Windows pencereyi bulanık büyütmesin
            os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")
        pygame.init()
        self._scale = 1.0 if headless else _dpi_scale()
        w, h = size or self.SIZE
        surface = pygame.display.set_mode((round(w * self._scale), round(h * self._scale)),
                                          0 if headless else pygame.RESIZABLE)
        pygame.display.set_caption(self.title)
        pygame.key.set_repeat(400, 35)
        self.painter = Painter(surface, self._make_theme(), default_font_paths())
        main = _MainScreen(self, padding=self.PADDING, gap=self.GAP)
        main.parent = self
        self.children = [main]
        self._mounted = True
        self._mount_tree(main)
        hook = getattr(self, "on_mount", None)
        if hook is not None:
            self._call(hook)
        self._running = True
        self._layout_all()

    def _shutdown(self) -> None:
        self._running = False
        for task in list(self._tasks):
            task.cancel()
        for screen in list(self.children):
            self._unmount_tree(screen)
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
        pygame.quit()

    def _tick(self) -> None:
        self._process_events()
        self._run_timers()
        if self._needs_layout:
            self._layout_all()
        if self._dirty:
            self._render()

    def _sleep_time(self) -> float:
        """Girdiden hemen sonra sık (60 Hz), boşta seyrek (30 Hz) yokla; zamanlayıcıyı kaçırma."""
        now = time.monotonic()
        wait = 1 / 60 if now < self._active_until else 1 / 30
        due = min((t.due for t in self._all_timers if t.active), default=now + wait)
        return max(0.001, min(wait, due - now))

    def _invalidate(self, layout: bool) -> None:
        self._dirty = True
        if layout:
            self._needs_layout = True

    # ── yerleşim ve çizim ─────────────────────────────────

    def _layout_all(self) -> None:
        surface = pygame.display.get_surface()
        self.painter.surface = surface
        for screen in self.children:
            screen._layout(self.painter, surface.get_rect())
        self._needs_layout = False
        self._dirty = True
        chain = self.focus_chain()
        if self.focused is not None and self.focused not in chain:
            self.set_focus(None)
        if self.focused is None and chain:
            self.set_focus(chain[0])
        # yerleşim değişince farenin altındaki bileşen de değişmiş olabilir
        if pygame.mouse.get_focused():
            self._set_hover(self._hit_test(pygame.mouse.get_pos()))

    def _render(self) -> None:
        p = self.painter
        surface = pygame.display.get_surface()
        p.surface = surface
        full = surface.get_rect()
        surface.set_clip(None)
        surface.fill(p.theme.bg)
        for screen in self.children:
            if screen.modal:
                veil = pygame.Surface(full.size, pygame.SRCALPHA)
                veil.fill((*p.theme.bg, 175))
                surface.set_clip(None)
                surface.blit(veil, (0, 0))
            self._paint(screen, full)
        surface.set_clip(None)
        self._paint_toasts(p)
        pygame.display.flip()
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
            self._report(exc)
        inner = widget.child_clip().clip(clip)
        for child in widget.children:
            self._paint(child, inner)

    def _paint_toasts(self, p: Painter) -> None:
        th = p.theme
        width = p.surface.get_width()
        px, py = p.pad
        y = round(p.row * 0.6)
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


class Pilot:
    """Testler için: uygulamayı pencere açmadan sürer.

        async with app.run_test() as pilot:
            await pilot.press("tab", "enter")
            await pilot.type("merhaba")
            await pilot.click("#tamam")
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
            key = keys.normalize(name)
            char = " " if key == "space" else (key if len(key) == 1 else None)
            self.app._key(key, char)
            if char is not None:
                self.app._text(char)
            await self.pause()

    async def type(self, text: str) -> None:
        for ch in text:
            low = ch.lower()
            self.app._key("space" if ch == " " else (low if len(low) == 1 else ch), ch)
            self.app._text(ch)
            await self.pause()

    def _target(self, target) -> Widget:
        return self.app.query_one(target) if isinstance(target, (str, type)) else target

    async def click(self, target, *, offset: tuple[int, int] | None = None, button: int = 1) -> None:
        widget = self._target(target)
        pos = (widget.region.x + offset[0], widget.region.y + offset[1]) if offset else widget.region.center
        self.app._mouse_move(pos, False)
        self.app._mouse_down(pos, button)
        self.app._mouse_up(pos, button)
        await self.pause()

    async def hover(self, target, *, offset: tuple[int, int] | None = None) -> None:
        widget = self._target(target)
        pos = (widget.region.x + offset[0], widget.region.y + offset[1]) if offset else widget.region.center
        self.app._mouse_move(pos, False)
        await self.pause()

    async def scroll(self, target, dy: int) -> None:
        self.app._wheel(self._target(target).region.center, 0, dy)
        await self.pause()

    def snapshot(self, path: str) -> None:
        """Ekranı PNG olarak kaydet."""
        self.app._render()
        pygame.image.save(self.app.painter.surface, path)


def _dpi_scale() -> float:
    """Windows ekran ölçeği (%125 → 1.25); pygame.init()'ten sonra çağrılmalı."""
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes
        return ctypes.windll.user32.GetDpiForSystem() / 96
    except (AttributeError, OSError):
        return 1.0
