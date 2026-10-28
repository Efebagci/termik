"""Küçük yardımcılar."""

from __future__ import annotations

import inspect
from functools import lru_cache
from typing import Any, Callable

_MANY = 99  # *args alan ya da imzası okunamayan çağrılabilirler


@lru_cache(maxsize=None)
def _positional(func: Callable) -> int:
    try:
        params = list(inspect.signature(func).parameters.values())
    except (TypeError, ValueError):
        return _MANY
    if any(p.kind == p.VAR_POSITIONAL for p in params):
        return _MANY
    return sum(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in params)


def arity(fn: Callable) -> int:
    """Çağrılabilirin aldığı konumsal argüman sayısı; bağlı metotta self sayılmaz."""
    func = getattr(fn, "__func__", fn)
    try:
        n = _positional(func)
    except TypeError:  # hashlenemeyen çağrılabilir
        n = _MANY
    return n - 1 if func is not fn and n != _MANY else n


def call_flexible(fn: Callable, *args: Any) -> Any:
    """fn'i kabul ettiği kadar argümanla çağır: on_click(self) de on_click(self, event) de olur."""
    return fn(*args[: arity(fn)])
