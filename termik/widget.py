"""Bileşen ağacı: Widget temel sınıfı, compose, sorgular, mesajlar, eylemler ve yerleşim.

Her bileşen bir dikdörtgen kaplar (region) ve çocuklarını içerik alanında (content) dizer.
Varsayılan dizim alt alta; Row yan yana dizer. Boyutlar CLI birimleriyle verilir: width=30
otuz karakter, height=5 beş satır demektir; ayrıca "12px", "40%", "2fr" ve "auto".

    class Form(Widget):
        def compose(self):
            yield Input(label="Ad")
            with Row():
                yield Spacer()
                yield Button("Kaydet", action="save", variant="primary")
"""

from __future__ import annotations

import inspect
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator, TypeVar

import pygame

from . import keys
from ._util import call_flexible
from .events import Message
from .layout import AUTO, FILL, Size, distribute, parse_padding, parse_size, resolve

if TYPE_CHECKING:
    from .app import App, Timer, Window
    from .draw import Painter

W = TypeVar("W", bound="Widget")

# compose() çalışırken açık kapsayıcıların yığını; `with Row():` kendini buraya ekler
_compose_stack: ContextVar[list | None] = ContextVar("termik_compose", default=None)


class ActionInfo:
    """@action ile işaretlenmiş bir metodun bilgileri."""

    __slots__ = ("name", "label", "keys", "hint", "show", "palette", "priority")

    def __init__(self, name: str, label: str, keys_: tuple[str, ...], hint: str | None,
                 show: bool, palette: bool, priority: bool) -> None:
        self.name, self.label, self.keys, self.hint = name, label, keys_, hint
        self.show, self.palette, self.priority = show, palette, priority


def action(label: str, key: str | Iterable[str] | None = None, *, hint: str | None = None,
           show: bool = True, palette: bool = True, priority: bool = False):
    """Metodu komut yap: tuşa bağlanır, kısayol satırında görünür, butona action= ile verilir.

        @action("Yedeklemeyi başlat", key="f5", hint="başlat")
        async def start(self): ...

    key virgülle ayrılmış birden çok tuş olabilir ("escape,q"). hint kısayol satırındaki kısa
    addır (yoksa label kullanılır). priority=True eylemler odaktaki bileşenden önce denenir.
    """
    raw = key.split(",") if isinstance(key, str) else list(key or ())
    bound = tuple(keys.normalize(k) for k in raw if k.strip())

    def decorate(fn):
        fn._termik_action = ActionInfo(fn.__name__, label, bound, hint, show, palette, priority)
        return fn

    return decorate


def _matches(widget: Widget, selector) -> bool:
    if selector is None:
        return True
    if isinstance(selector, type):
        return isinstance(widget, selector)
    if selector.startswith("#"):
        return widget.id == selector[1:]
    if selector.startswith("."):
        return selector[1:] in widget.classes
    return any(cls.__name__ == selector for cls in type(widget).__mro__)


class Widget:
    """Bütün bileşenlerin temeli."""

    default_width: str | float | None = "1fr"
    default_height: str | float | None = None  # None: büyüyen çocuk varsa 1fr, yoksa auto
    direction = "column"                      # çocukların dizimi: column ya da row
    can_focus = False
    accepts_text = False       # odaktayken harf tuşları kısayol değil yazı sayılır
    cursor: str | None = None  # üstüne gelince fare imleci: "hand" ya da "ibeam"

    _actions: dict[str, ActionInfo] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # önce sınıfın kendi eylemleri, sonra kalıtılanlar: kısayol satırında kendi işleri önde
        merged: dict[str, ActionInfo] = {}
        for name, value in cls.__dict__.items():
            info = getattr(value, "_termik_action", None)
            if info is not None:
                merged[name] = info
        for base in cls.__mro__[1:]:
            for name, info in base.__dict__.get("_actions", {}).items():
                merged.setdefault(name, info)
        cls._actions = merged

    def __init__(self, *children: Widget, id: str | None = None, classes: str = "",
                 width=None, height=None, min_width=None, max_width=None, min_height=None, max_height=None,
                 padding=0, gap=0, disabled: bool = False, display: bool = True, tooltip: str | None = None) -> None:
        self.id = id
        self.classes = set(classes.split())
        self.tooltip = tooltip  # fare üstünde durunca gösterilen ipucu (markup)
        self.parent: Widget | None = None
        self.children: list[Widget] = []
        self.region = pygame.Rect(0, 0, 0, 0)   # kapladığı alan, ekran pikseli
        self.content = pygame.Rect(0, 0, 0, 0)  # iç boşluk (ve çerçeve) düşülmüş alan
        self.hovered = False
        self._width, self._height = parse_size(width), parse_size(height)
        self._limits = {"w": (parse_size(min_width), parse_size(max_width)),
                        "h": (parse_size(min_height), parse_size(max_height))}
        self._padding = parse_padding(padding)
        self._gap = parse_size(gap)
        self._disabled = disabled
        self._display = display
        self._app: App | None = None
        self._window: Window | None = None
        self._mounted = False
        self._composed = False
        self._timers: list[Timer] = []
        for child in children:
            self._add_child(child)

    def __repr__(self) -> str:
        return f"<{type(self).__name__}{f' #{self.id}' if self.id else ''}>"

    # ── ağaç ──────────────────────────────────────────────

    @property
    def app(self) -> App:
        if self._app is None:
            raise RuntimeError(f"{self!r} henüz bir uygulamaya bağlı değil")
        return self._app

    @property
    def window(self) -> Window:
        """Bileşenin bulunduğu pencere (ana pencerede uygulamanın kendisi)."""
        if self._window is None:
            raise RuntimeError(f"{self!r} henüz bir pencereye bağlı değil")
        return self._window

    @property
    def is_mounted(self) -> bool:
        return self._mounted

    def ancestors(self) -> Iterator[Widget]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def walk(self, *, visible_only: bool = False) -> Iterator[Widget]:
        """Bu bileşen ve bütün torunları, çizim sırasıyla."""
        if visible_only and not self._display:
            return
        yield self
        for child in self.children:
            yield from child.walk(visible_only=visible_only)

    def compose(self) -> Iterable[Widget]:
        """Alt bileşenleri üret. `with Row():` gibi bloklar iç içe kapsayıcı açar."""
        return ()

    def __enter__(self: W) -> W:
        stack = _compose_stack.get()
        if stack is not None:
            stack[-1]._add_child(self)
            stack.append(self)
        return self

    def __exit__(self, *exc) -> bool:
        stack = _compose_stack.get()
        if stack and stack[-1] is self:
            stack.pop()
        return False

    def _run_compose(self) -> None:
        if self._composed:
            return
        self._composed = True
        stack: list[Widget] = [self]
        token = _compose_stack.set(stack)
        try:
            for child in self.compose() or ():
                stack[-1]._add_child(child)
        finally:
            _compose_stack.reset(token)

    def _add_child(self, child: Widget, index: int | None = None) -> None:
        if not isinstance(child, Widget):
            raise TypeError(f"bileşen bekleniyordu, {type(child).__name__} geldi")
        if child.parent is not None:
            child.parent.children.remove(child)
        child.parent = self
        if index is None:
            self.children.append(child)
        else:
            self.children.insert(index, child)
        if self._mounted:
            self.window._mount_tree(child)

    def mount(self, *widgets: Widget, before: int | None = None) -> None:
        """Çalışırken bileşen ekle (before: araya gireceği sıra)."""
        for i, widget in enumerate(widgets):
            self._add_child(widget, None if before is None else before + i)

    def remove(self) -> None:
        """Bu bileşeni ağaçtan çıkar."""
        parent = self.parent
        if parent is None:
            return
        window = self._window
        parent.children.remove(self)
        self.parent = None
        if window is not None:
            window._unmount_tree(self)

    def remove_children(self) -> None:
        for child in list(self.children):
            child.remove()

    def query(self, selector: str | type | None = None) -> list[Widget]:
        """'#kimlik', '.sınıf', 'SınıfAdı' ya da türle torunları bul."""
        return [w for w in self.walk() if w is not self and _matches(w, selector)]

    def query_one(self, selector: str | type, expect_type: type[W] | None = None) -> W:
        for widget in self.walk():
            if widget is not self and _matches(widget, selector):
                if expect_type is not None and not isinstance(widget, expect_type):
                    raise TypeError(f"{selector!r} bir {expect_type.__name__} değil: {widget!r}")
                return widget  # type: ignore[return-value]
        raise LookupError(f"bulunamadı: {selector!r}")

    # ── durum ─────────────────────────────────────────────

    @property
    def disabled(self) -> bool:
        return self._disabled

    @disabled.setter
    def disabled(self, value: bool) -> None:
        if value != self._disabled:
            self._disabled = value
            if value and self.has_focus:
                self.window._move_focus(1)
            self.refresh()

    @property
    def display(self) -> bool:
        return self._display

    @display.setter
    def display(self, value: bool) -> None:
        if value != self._display:
            self._display = value
            self.refresh(layout=True)

    @property
    def has_focus(self) -> bool:
        return self._window is not None and self._window.focused is self

    @property
    def focus_within(self) -> bool:
        """Odak bu bileşende ya da torunlarından birinde mi."""
        node = self._window.focused if self._window is not None else None
        while node is not None:
            if node is self:
                return True
            node = node.parent
        return False

    def focus(self) -> None:
        if self._window is not None:
            self._window.set_focus(self)

    def refresh(self, *, layout: bool = False) -> None:
        """Yeniden çizilmesini iste; boyutu da değiştiyse layout=True."""
        if self._window is not None:
            self._window._invalidate(layout)

    # ── mesajlar ve eylemler ──────────────────────────────

    def post_message(self, message: Message) -> Message:
        """Mesajı bu bileşenden başlayıp ebeveynlere doğru ilet."""
        if message.sender is None:
            message.sender = self
        node: Widget | None = self
        while node is not None:
            node._handle_message(message)
            if message.stopped or not message.bubble:
                break
            node = node.parent
        return message

    def _handle_message(self, message: Message) -> None:
        handler = getattr(self, message.handler_name, None)
        if handler is not None:
            self._call(handler, message)

    def _call(self, fn: Callable, *args) -> Any:
        """İşleyiciyi çağır. Coroutine dönerse görev olarak başlat; hatayı uygulamaya bildir."""
        app = self._app
        try:
            result = call_flexible(fn, *args)
        except Exception as exc:
            if app is None:
                raise
            app._report(exc)
            return None
        if inspect.isawaitable(result):
            if app is not None and app._loop is not None:
                app._spawn(result)
            elif inspect.iscoroutine(result):
                result.close()
        return result

    def _binding(self, key: str, priority: bool) -> ActionInfo | None:
        if self._disabled:
            return None
        for info in type(self)._actions.values():
            if info.priority == priority and key in info.keys:
                return info
        return None

    def run_action(self, name: str) -> bool:
        """`name` eylemini bu bileşenden başlayıp yukarı doğru arayıp çalıştır.

        "app." önekli adlar uygulamada, "window." önekliler bileşenin penceresinde aranır.
        Bulunamazsa False döner.
        """
        scope, _, short = name.rpartition(".")
        for node in self._action_nodes(scope):
            if short in type(node)._actions and not node._disabled:
                node._call(getattr(node, short))
                return True
        return False

    def _action_nodes(self, scope: str) -> list[Widget]:
        """Eylem adının arandığı bileşenler: önek yoksa bu bileşenden pencereye kadar (ek pencerede en
        sonda uygulama), "app." ise uygulama, "window." ise bileşenin penceresi."""
        if scope == "app":
            return [self.app]
        if scope == "window":
            return [self.window]
        nodes = [self, *self.ancestors()]
        if self._window is not None and self._window is not self._app:
            nodes.append(self._app)
        return nodes

    # ── zamanlayıcılar ve işçiler ─────────────────────────

    def set_interval(self, seconds: float, callback: Callable) -> Timer:
        """callback'i her `seconds` saniyede bir çağır; bileşen kaldırılınca kendiliğinden durur."""
        return self.app._add_timer(seconds, callback, repeat=True, owner=self)

    def set_timer(self, seconds: float, callback: Callable) -> Timer:
        """callback'i bir kez, `seconds` saniye sonra çağır."""
        return self.app._add_timer(seconds, callback, repeat=False, owner=self)

    def run_worker(self, fn: Callable, *args, **kwargs):
        """Bloklayan fonksiyonu ayrı thread'de, coroutine fonksiyonunu görev olarak çalıştır.

        Dönen nesne await edilebilir: `sonuç = await self.run_worker(tara, klasör)`.
        """
        return self.app.run_worker(fn, *args, **kwargs)

    def call_later(self, fn: Callable, *args) -> None:
        """fn'i olay döngüsünün bir sonraki turunda çağır."""
        self.app._loop.call_soon(self._call, fn, *args)

    # ── yerleşim ──────────────────────────────────────────

    def chrome(self, p: Painter) -> tuple[int, int, int, int]:
        """İçerikle dış kenar arasındaki kalınlık (üst, sağ, alt, sol), piksel."""
        t, r, b, l = self._padding
        return round(t * p.row), round(r * p.ch), round(b * p.row), round(l * p.ch)

    def _spec(self, axis: str) -> Size:
        explicit = self._width if axis == "w" else self._height
        if explicit is not None:
            return explicit
        default = self.default_width if axis == "w" else self.default_height
        if default is not None:
            return parse_size(default)
        grows = any(c._spec(axis).kind == "fr" for c in self.children if c._display)
        return FILL if grows else AUTO

    def _gap_px(self, p: Painter) -> int:
        return resolve(self._gap, p.ch if self.direction == "row" else p.row, 0)

    def _limit_size(self, p: Painter, axis: str, size: int, available: int) -> int:
        low, high = self._limits[axis]
        unit = p.ch if axis == "w" else p.row
        if low is not None:
            size = max(size, resolve(low, unit, available))
        if high is not None:
            size = min(size, resolve(high, unit, available))
        return size

    def _child_width(self, child: Widget, p: Painter, available: int) -> int:
        """Sütundaki bir çocuğun genişliği."""
        s = child._spec("w")
        if s.kind == "fr":
            return available
        if s.kind == "auto":
            return min(available, child.natural_size(p, available)[0])
        return min(available, resolve(s, p.ch, available))

    def _child_height(self, child: Widget, p: Painter, width: int, available: int) -> int:
        """Genişliği bilinen bir çocuğun doğal ya da sabit yüksekliği."""
        s = child._spec("h")
        if s.kind in ("auto", "fr"):
            return child.natural_size(p, width)[1]
        return resolve(s, p.row, available)

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        """İçeriğin doğal boyutu (iç boşluk hariç), verilen genişlikte. Yaprak bileşenler ezer."""
        kids = [c for c in self.children if c._display]
        if not kids:
            return 0, 0
        gap = self._gap_px(p) * (len(kids) - 1)
        if self.direction == "row":
            specs = [c._spec("w") for c in kids]
            available = max(0, width - gap)
            natural = [c.natural_size(p, available)[0] if s.kind == "auto" else 0 for c, s in zip(kids, specs)]
            widths = distribute(specs, natural, available, p.ch)
            used = sum(min(wi, c.natural_size(p, wi)[0]) if s.kind == "fr" else wi
                       for c, s, wi in zip(kids, specs, widths))
            return used + gap, max(self._child_height(c, p, wi, 0) for c, wi in zip(kids, widths))
        natural_w = max(min(width, c.natural_size(p, width)[0]) if c._spec("w").kind in ("fr", "auto")
                        else self._child_width(c, p, width) for c in kids)
        height = sum(self._child_height(c, p, self._child_width(c, p, width), 0) for c in kids)
        return natural_w, height + gap

    def natural_size(self, p: Painter, width: int) -> tuple[int, int]:
        """Dış boyut: içerik + iç boşluk (+ çerçeve), verilen genişlikte."""
        t, r, b, l = self.chrome(p)
        w, h = self.measure(p, max(0, width - l - r))
        return w + l + r, h + t + b

    def arrange(self, p: Painter) -> None:
        """Çocukları içerik alanına diz: sabitler ve auto önce, kalan alan fr payları oranında."""
        kids = [c for c in self.children if c._display]
        if not kids:
            return
        box = self.content
        gap = self._gap_px(p)
        row = self.direction == "row"
        axis = "w" if row else "h"
        main = max(0, (box.w if row else box.h) - gap * (len(kids) - 1))
        cross = box.h if row else box.w
        specs = [c._spec(axis) for c in kids]
        natural = []
        for c, s in zip(kids, specs):
            if s.kind != "auto":
                natural.append(0)
            elif row:
                natural.append(c.natural_size(p, main)[0])
            else:
                natural.append(c.natural_size(p, self._child_width(c, p, cross))[1])
        pos = box.x if row else box.y
        for c, size in zip(kids, distribute(specs, natural, main, p.ch if row else p.row)):
            size = c._limit_size(p, axis, size, main)
            if row:
                tall = cross if c._spec("h").kind == "fr" else min(cross, self._child_height(c, p, size, cross))
                rect = pygame.Rect(pos, box.y, size, tall)
            else:
                rect = pygame.Rect(box.x, pos, self._child_width(c, p, cross), size)
            c._layout(p, rect)
            pos += size + gap

    def _layout(self, p: Painter, region: pygame.Rect) -> None:
        self.region = pygame.Rect(region)
        t, r, b, l = self.chrome(p)
        self.content = pygame.Rect(region.x + l, region.y + t, max(0, region.w - l - r), max(0, region.h - t - b))
        self.arrange(p)

    def child_clip(self) -> pygame.Rect:
        """Çocukların çiziminin kırpıldığı alan."""
        return self.region

    def _reveal(self, widget: Widget) -> None:
        """Torunlardan biri odak alınca çağrılır; kaydırılabilir kapsayıcılar onu görünür alana getirir."""

    def context_menu(self, event=None) -> list | None:
        """Sağ tıkta (ya da Shift+F10) açılacak menünün öğeleri; None ise ata bileşenlere bakılır.

            def context_menu(self, event):
                return [MenuItem("Kopyala", self.copy), None, MenuItem("Sil", "delete")]

        event fareyle açılınca MouseDown, klavyeyle açılınca None'dır.
        """
        return None

    # ── çizim ─────────────────────────────────────────────

    def render(self, p: Painter) -> None:
        """Kendini çiz; çocuklar ardından çizilir. Çizim bileşenin alanına kırpılır."""


class Column(Widget):
    """Çocukları alt alta dizer."""


class Row(Widget):
    """Çocukları yan yana dizer."""

    direction = "row"


class Spacer(Widget):
    """Boş alan: bulunduğu kapsayıcının ana ekseninde kalan yeri doldurur."""

    def _spec(self, axis: str) -> Size:
        explicit = self._width if axis == "w" else self._height
        if explicit is not None:
            return explicit
        along = "w" if self.parent is not None and self.parent.direction == "row" else "h"
        return FILL if axis == along else AUTO


class Screen(Widget):
    """Pencereyi kaplayan kök. Modal ekran alttakinin üstüne çizilir ve bütün girdiyi alır."""

    modal = False
    veil = True  # modal ekranın altındakileri karart (açılır listeler ve menüler karartmaz)
    default_width = default_height = "1fr"
    _dismiss_callback: Callable | None = None  # push_screen(callback=…): kapanınca sonuçla çağrılır

    def dismiss(self, result: Any = None) -> None:
        """Bu ekranı kapat; sonucu push_screen'e verilen callback (ya da push_screen_wait) alır."""
        if self.is_mounted and self.window.screen is self:
            self.window.pop_screen(result)
