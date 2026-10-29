"""Varsayılan pencere simgesi: koyu zeminde temanın vurgu renginde ❯, yanında imleç bloğu.

Uygulama kendi simgesini verebilir (App(icon="simge.png") ya da sınıfta ICON = …); verilmezse bu
simge çizilir ve tema değişince rengi de değişir.
"""

from __future__ import annotations

import pygame

from .theme import Theme, mix

SS = 4  # kenarlar yumuşak olsun diye 4 kat büyük çizilip küçültülür


def prompt_icon(theme: Theme, size: int) -> pygame.Surface:
    """size×size simge. Küçük boyutlarda da okunsun diye çizgiler kalın tutulur."""
    big = size * SS
    u = big / 100
    img = pygame.Surface((big, big), pygame.SRCALPHA)
    bg = mix(theme.bg, (0, 0, 0), 0.25)
    radius = round(22 * u)
    img.fill((*bg, 0))  # saydam ama aynı renkte zemin: küçültürken köşeler kararmasın
    pygame.draw.rect(img, (*bg, 255), (0, 0, big, big), border_radius=radius)
    pygame.draw.rect(img, (*mix(bg, theme.accent, 0.35), 255), (0, 0, big, big),
                     width=max(SS, round(3.5 * u)), border_radius=radius)
    x0, x1, top, bottom, thick = 15, 41, 26, 74, 15  # ❯: kalın köşeli ok
    chevron = [(x0, top), (x0 + thick, top), (x1 + thick, 50), (x0 + thick, bottom), (x0, bottom), (x1, 50)]
    pygame.draw.polygon(img, theme.accent, [(x * u, y * u) for x, y in chevron])
    pygame.draw.rect(img, theme.text, (round(64 * u), round(31 * u), round(19 * u), round(38 * u)))  # imleç
    return pygame.transform.smoothscale(img, (size, size))
