"""Etiketli form."""

from __future__ import annotations

import pygame

from ..draw import Painter
from ..layout import distribute
from ..widget import Widget


class Form(Widget):
    """Etiketli alanlar: içindeki her bileşen label= alır, Form etiketleri hizalı bir sütunda çizer.

        with ui.Form():
            yield ui.Input(label="Kaynak", bind="kaynak")
            yield ui.Slider(6, max=9, label="Düzey")
            yield ui.Select(["Elle", "Her gün"], label="Zamanlama")
            with ui.Row(label="Seçenekler", gap=2):
                yield ui.Checkbox("Sıkıştır", True)
                yield ui.Checkbox("Şifrele")

    Etiketler temadaki form_label belirtecine göre solda (en uzun etikete göre hizalı) ya da alanın
    üstünde durur; label_width= sol sütunun genişliğini karakter cinsinden sabitler. Etiketsiz
    bileşenler (not, ilerleme çubuğu, buton satırı) bütün genişliği kaplar. Odaktaki alanın etiketi
    parlak yazılır. Kendi yazısı label olan bileşenler (Button, Checkbox) için bir Row'a label verilir.
    """

    def __init__(self, *children: Widget, label_width: float | None = None, **kwargs) -> None:
        kwargs.setdefault("gap", 0.25)
        super().__init__(*children, **kwargs)
        self.label_width = label_width
        self._labels: list[tuple[Widget, int, int, int]] = []  # (alan, x, y, en çok genişlik)

    def _add_child(self, child: Widget, index: int | None = None) -> None:
        super()._add_child(child, index)
        child._in_form = True  # Input ve RadioSet kendi etiketini çizmesin

    def _kids(self) -> list[Widget]:
        return [c for c in self.children if c._display]

    @staticmethod
    def _top(p) -> bool:
        return p.theme.form_label == "top"

    def _label_px(self, p, kids: list[Widget], width: int) -> int:
        """Sol etiket sütununun genişliği (üstte kipinde 0); en fazla genişliğin beşte ikisi."""
        labels = [k.field_label for k in kids if k.field_label]
        if not labels or self._top(p):
            return 0
        if self.label_width is not None:
            return round(self.label_width * p.ch)
        return min(max(p.text.width(label) for label in labels) + p.ch * 2, width * 2 // 5)

    @staticmethod
    def _place(child: Widget, lw: int, width: int) -> tuple[int, int]:
        """Alanın sola uzaklığı ve kullanabileceği genişlik."""
        return (lw, max(0, width - lw)) if child.field_label and lw else (0, width)

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        kids = self._kids()
        if not kids:
            return 0, 0
        lw, top = self._label_px(p, kids, width), self._top(p)
        w = h = 0
        for c in kids:
            off, avail = self._place(c, lw, width)
            cw = self._child_width(c, p, avail)
            natural = min(avail, c.natural_size(p, avail)[0]) if c._spec("w").kind in ("fr", "auto") else cw
            w = max(w, off + natural)
            h += self._child_height(c, p, cw, 0) + (p.row if top and c.field_label else 0)
        return w, h + self._gap_px(p) * (len(kids) - 1)

    def arrange(self, p: Painter) -> None:
        kids = self._kids()
        self._labels = []
        if not kids:
            return
        box = self.content
        gap, top = self._gap_px(p), self._top(p)
        lw = self._label_px(p, kids, box.w)
        extra = [p.row if top and c.field_label else 0 for c in kids]  # üstte kipinde etiket satırı
        main = max(0, box.h - gap * (len(kids) - 1) - sum(extra))
        places = [self._place(c, lw, box.w) for c in kids]
        widths = [self._child_width(c, p, avail) for c, (_, avail) in zip(kids, places)]
        specs = [c._spec("h") for c in kids]
        natural = [c.natural_size(p, w)[1] if s.kind == "auto" else 0 for c, s, w in zip(kids, specs, widths)]
        y = box.y
        for c, (off, _), w, size, e in zip(kids, places, widths, distribute(specs, natural, main, p.row), extra):
            if c.field_label:
                self._labels.append((c, box.x, y, lw - p.ch if lw else box.w))
            y += e
            size = c._limit_size(p, "h", size, main)
            c._layout(p, pygame.Rect(box.x + off, y, w, size))
            y += size + gap

    def render(self, p: Painter) -> None:
        th = p.theme
        for child, x, y, room in self._labels:
            color = th.faint if child.disabled else th.text if child.focus_within else th.dim
            p.write(x, y, p.text.elide(child.field_label, room), color=color)
