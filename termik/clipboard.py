"""Pano: sistem panosu, kullanılamazsa (ör. pencere açmadan çalışırken) uygulama içi yedek."""

from __future__ import annotations

import pygame

_fallback = ""


def get_text() -> str:
    try:
        return pygame.scrap.get_text() or _fallback
    except (pygame.error, AttributeError):
        return _fallback


def put_text(text: str) -> None:
    global _fallback
    _fallback = text
    try:
        pygame.scrap.put_text(text)
    except (pygame.error, AttributeError):
        pass
