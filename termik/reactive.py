"""Reaktif öznitelikler: değer değişince bileşen kendiliğinden yeniden çizilir.

    class Backup(Widget):
        progress = reactive(0.0)

        def watch_progress(self, old, new):  # isteğe bağlı; (new) ya da hiç argüman da olur
            ...

Değer gerçekten değiştiyse önce watch_<ad> çağrılır (async olabilir), sonra bileşen yenilenir.
layout=True boyutu etkileyen değerler içindir: yerleşim de baştan hesaplanır. Bileşen henüz
bir uygulamaya bağlanmadıysa değer sessizce atanır, izleyici çağrılmaz.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

from ._util import arity

T = TypeVar("T")
_UNSET = object()


class reactive(Generic[T]):
    def __init__(self, default: T | Callable[[], T], *, layout: bool = False, repaint: bool = True,
                 always_update: bool = False) -> None:
        self.default = default  # çağrılabilirse (ör. list) her nesne için ayrı değer üretir
        self.layout = layout
        self.repaint = repaint
        self.always_update = always_update
        self.name = ""
        self.attr = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self.attr = f"_reactive_{name}"

    def __get__(self, obj: Any, objtype: type | None = None):
        if obj is None:
            return self
        value = obj.__dict__.get(self.attr, _UNSET)
        if value is _UNSET:
            value = self.default() if callable(self.default) else self.default
            obj.__dict__[self.attr] = value
        return value

    def __set__(self, obj: Any, value: T) -> None:
        old = self.__get__(obj)
        if old == value and not self.always_update:
            return
        obj.__dict__[self.attr] = value
        binders = obj.__dict__.get("_binders")
        if binders and self.name in binders:  # bind= ile bağlı alanlar da güncellensin
            for widget in list(binders[self.name]):
                widget._bind_pull(value)
        if not getattr(obj, "_mounted", False):
            return
        watcher = getattr(obj, f"watch_{self.name}", None)
        if watcher is not None:
            n = arity(watcher)
            obj._call(watcher, *((old, value) if n >= 2 else (value,) if n == 1 else ()))
        if self.layout or self.repaint:
            obj.refresh(layout=self.layout)
