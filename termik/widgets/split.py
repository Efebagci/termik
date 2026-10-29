"""Bölünebilir kapsayıcı."""

from __future__ import annotations

from typing import Sequence

import pygame

from ..draw import Painter
from ..events import Click, Message, MouseDown, MouseMove
from ..layout import SizeSpec, distribute, parse_size
from ..theme import mix
from ..widget import Widget, action


class Split(Widget):
    """Bölünebilir kapsayıcı: çocuklar yan yana (direction="row", varsayılan) ya da alt alta
    ("column") dizilir, aralarındaki ayraç fareyle sürüklenir.

        with ui.Split(sizes=[32, "1fr"]):
            yield ui.Panel(ui.DirectoryTree("."), title="Dosyalar")
            yield ui.Panel(ui.Image("foto.png"), title="Önizleme")

    sizes verilmezse çocukların kendi boyutu (width=… ya da height=…) başlangıç olur. Sürükleyince
    oranlar korunur: pencere büyüyünce paneller birlikte büyür. Ayraca çift tık başlangıca döndürür;
    odak bir paneldeyken Alt+Shift+←/→ (alt alta ise ↑/↓) ayracı kaydırır. min_size her panelin en
    küçük boyutudur (karakter ya da satır). Değişince Split.Resized iletir; fractions okunup
    set_fractions() ile geri yüklenebilir (ör. bir ayar dosyasından).

    Ayraç temadaki split belirteciyle çizilir: line ince çizgi ve ⋮ tutamak, bar dolu sütun,
    hidden yalnızca fare gelince görünür.
    """

    default_height = "1fr"

    class Resized(Message):
        def __init__(self, split: Split, fractions: list[float]) -> None:
            super().__init__()
            self.split, self.fractions = split, fractions

    def __init__(self, *children: Widget, direction: str = "row", sizes: Sequence[SizeSpec] | None = None, min_size: float | None = None,
                 **kwargs) -> None:
        if direction not in ("row", "column"):
            raise ValueError("Split: direction 'row' ya da 'column' olmalı")
        kwargs.setdefault("gap", 1 if direction == "row" else 0.5)  # ayracın kalınlığı
        super().__init__(*children, **kwargs)
        self.direction = direction
        self._initial = [parse_size(s) for s in sizes] if sizes else None
        self.min_size = min_size if min_size is not None else (6 if direction == "row" else 3)
        self._fractions: list[float] | None = None
        self._sizes: list[int] = []
        self._seps: list[pygame.Rect] = []
        self._drag: int | None = None
        self._grab = 0  # sürüklemeye başlarken farenin ayraç içindeki yeri
        self._hover_sep: int | None = None

    @property
    def cursor(self) -> str | None:  # yalnızca ayracın üstünde (çocuklar ayraç dışını kaplar)
        return ("ew" if self.direction == "row" else "ns") if self.hovered else None

    # ── oranlar ──────────────────────────────────────────

    @property
    def fractions(self) -> list[float] | None:
        """Panellerin payları (toplamı 1); henüz yerleşmediyse None."""
        total = sum(self._sizes)
        return [s / total for s in self._sizes] if total else None

    def set_fractions(self, fractions: list[float] | None) -> None:
        """Payları ver (None başlangıç boyutlarına döndürür)."""
        if fractions is not None:
            total = sum(fractions)
            fractions = [f / total for f in fractions] if total > 0 else None
        self._fractions = fractions
        self.refresh(layout=True)

    def reset(self) -> None:
        self.set_fractions(None)

    # ── yerleşim ─────────────────────────────────────────

    def _kids(self) -> list[Widget]:
        return [c for c in self.children if c._display]

    def _plan(self, p, kids: list[Widget], main: int) -> list[int]:
        row = self.direction == "row"
        unit = p.ch if row else p.row
        if self._fractions is not None and len(self._fractions) == len(kids):
            sizes, acc, given = [], 0.0, 0
            for f in self._fractions:
                acc += f
                sizes.append(round(main * acc) - given)
                given += sizes[-1]
        else:
            axis = "w" if row else "h"
            specs = (self._initial if self._initial and len(self._initial) == len(kids)
                     else [c._spec(axis) for c in kids])
            box = self.content
            natural = [(c.natural_size(p, main)[0] if row else c.natural_size(p, box.w)[1]) if s.kind == "auto" else 0
                       for c, s in zip(kids, specs)]
            sizes = distribute(specs, natural, main, unit)
            if sum(sizes) != main:  # payı olan yoksa artanı (ya da taşanı) son panel alır
                sizes[-1] = max(0, sizes[-1] + main - sum(sizes))
        least = round(self.min_size * unit)
        for i in range(len(sizes)):  # en küçük boyut: eksiği en büyük panelden al
            if sizes[i] < least:
                j = max((k for k in range(len(sizes)) if k != i), key=lambda k: sizes[k], default=None)
                if j is None:
                    break
                need = min(least - sizes[i], max(0, sizes[j] - least))
                sizes[i] += need
                sizes[j] -= need
        return sizes

    def arrange(self, p: Painter) -> None:
        kids = self._kids()
        self._seps = []
        if not kids:
            self._sizes = []
            return
        row = self.direction == "row"
        box = self.content
        gap = self._gap_px(p)
        main = max(0, (box.w if row else box.h) - gap * (len(kids) - 1))
        self._sizes = self._plan(p, kids, main)
        pos = box.x if row else box.y
        for i, (child, size) in enumerate(zip(kids, self._sizes)):
            child._layout(p, pygame.Rect(pos, box.y, size, box.h) if row else pygame.Rect(box.x, pos, box.w, size))
            pos += size
            if i < len(kids) - 1:
                self._seps.append(pygame.Rect(pos, box.y, gap, box.h) if row else pygame.Rect(box.x, pos, box.w, gap))
                pos += gap

    def _move(self, i: int, boundary: int) -> None:
        """i'nci ayracı (i ve i+1'inci paneller arası) ana eksende boundary pikseline taşı."""
        if not 0 <= i < len(self._seps):
            return
        p = self.app.painter
        row = self.direction == "row"
        least = round(self.min_size * (p.ch if row else p.row))
        sizes = list(self._sizes)
        start = (self._seps[i].x if row else self._seps[i].y) - sizes[i]  # i'nci panelin başı
        pair = sizes[i] + sizes[i + 1]
        first = max(min(least, pair // 2), min(boundary - start, pair - min(least, pair // 2)))
        if first == sizes[i]:
            return
        sizes[i], sizes[i + 1] = first, pair - first
        total = sum(sizes)
        self._fractions = [s / total for s in sizes]
        self.refresh(layout=True)
        self.post_message(Split.Resized(self, list(self._fractions)))

    # ── fare ve tuşlar ───────────────────────────────────

    def _sep_at(self, pos) -> int | None:
        return next((i for i, r in enumerate(self._seps) if r.collidepoint(pos)), None)

    def on_mouse_down(self, event: MouseDown) -> None:
        i = self._sep_at(event.pos)
        self._drag = i if event.button == 1 else None
        if i is not None:
            event.stop()
            sep = self._seps[i]
            self._grab = event.x - sep.x if self.direction == "row" else event.y - sep.y
            self.refresh()

    def on_mouse_move(self, event: MouseMove) -> None:
        if event.button and self._drag is not None:
            self._move(self._drag, (event.x if self.direction == "row" else event.y) - self._grab)
            return
        i = self._sep_at(event.pos)
        if i != self._hover_sep:
            self._hover_sep = i
            self.refresh()

    def on_mouse_leave(self) -> None:
        self._hover_sep = None
        self.refresh()

    def on_click(self, event: Click) -> None:
        self._drag = None
        if event.count == 2 and self._sep_at(event.pos) is not None:
            event.stop()
            self.reset()
            self.post_message(Split.Resized(self, []))
        self.refresh()

    def _focused_sep(self) -> int | None:
        """Odaktaki panelin ayracı (son paneldeyse solundaki/üstündeki)."""
        focused = self.window.focused
        kids = self._kids()
        for i, kid in enumerate(kids):
            node = focused
            while node is not None and node is not kid:
                node = node.parent
            if node is kid:
                return min(i, len(self._seps) - 1) if self._seps else None
        return None

    def _nudge(self, units: int) -> None:
        i = self._focused_sep()
        if i is None:
            return
        p = self.app.painter
        row = self.direction == "row"
        sep = self._seps[i]
        self._move(i, (sep.x if row else sep.y) + units * (p.ch if row else p.row))

    @action("Ayracı sola/yukarı kaydır", key="alt+shift+left,alt+shift+up", show=False, palette=False)
    def shrink(self) -> None:
        self._nudge(-2 if self.direction == "row" else -1)

    @action("Ayracı sağa/aşağı kaydır", key="alt+shift+right,alt+shift+down", show=False, palette=False)
    def grow(self) -> None:
        self._nudge(2 if self.direction == "row" else 1)

    # ── çizim ─────────────────────────────────────────────

    def render(self, p: Painter) -> None:
        th = p.theme
        row = self.direction == "row"
        dragging = self._drag is not None and self.window._pressed is self
        for i, r in enumerate(self._seps):
            active = i == self._hover_sep or (dragging and i == self._drag)
            if th.split == "hidden" and not active:
                continue
            color = th.accent if active else th.border
            if th.split == "bar":
                p.surface.fill(mix(th.bg, color, 0.55 if active else 0.45), r)
                continue
            t = 2 if active else 1
            grip = "⋮" if row else "⋯"
            gw, gh = p.text.width(grip), p.text.height
            if row:
                x = r.centerx - t // 2
                top, bottom = r.centery - gh // 2 - 2, r.centery + gh // 2 + 2
                p.surface.fill(color, (x, r.y, t, max(0, top - r.y)))
                p.surface.fill(color, (x, bottom, t, max(0, r.bottom - bottom)))
                p.text.draw(p.surface, r.centerx - gw // 2, r.centery - gh // 2, grip, color=color)
            else:
                y = r.centery - t // 2
                left, right = r.centerx - gw // 2 - p.ch // 2, r.centerx + gw // 2 + p.ch // 2
                p.surface.fill(color, (r.x, y, max(0, left - r.x), t))
                p.surface.fill(color, (right, y, max(0, r.right - right), t))
                p.text.draw(p.surface, r.centerx - gw // 2, r.centery - gh // 2, grip, color=color)
