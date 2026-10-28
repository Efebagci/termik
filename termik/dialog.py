"""Modal diyaloglar: onay, bilgi, yazı sorma.

Çoğu zaman App'in yardımcılarıyla kullanılır:

    if await self.app.confirm("Yedekleme iptal edilsin mi?"):
        ...
    ad = await self.app.prompt("Yeni ad", value="rapor.md")
"""

from __future__ import annotations

import functools
from typing import Any, Iterable

import pygame

from .events import Click
from .widget import Row, Screen, Spacer, Widget, action
from .widgets import Button, Input, Panel, Static


class Dialog(Screen):
    """Ortada yüzen modal kutu: başlık, içerik, butonlar.

    Bir butona basmak sonucunu, Esc `cancel` değerini döndürerek diyaloğu kapatır:

        ok = await app.push_screen_wait(Dialog("Silinsin mi?", "3 dosya silinecek.",
                                               buttons=[("Vazgeç", False), ("Sil", True)]))

    body bir markup yazı ya da bileşen olabilir (uzun içerik için ScrollView). `default` sıradaki
    buton öne çıkar ve odağı alır; Enter onu basar. Kutunun dışına tıklamak diyaloğu kapatmaz.
    """

    modal = True

    def __init__(self, title: str = "", body: str | Widget = "", *,
                 buttons: Iterable[tuple[str, Any]] = (("Tamam", True),), default: int = -1,
                 cancel: Any = None, width: float = 56, **kwargs) -> None:
        super().__init__(**kwargs)
        self.title = title
        self.body = body
        self.buttons = list(buttons)
        self.default = default % len(self.buttons) if self.buttons else 0
        self.cancel = cancel
        self.width = width
        self.box: Panel | None = None
        self._default_button: Button | None = None

    def compose_body(self):
        """Butonların üstündeki içerik; alt sınıflar ezebilir."""
        if isinstance(self.body, Widget):
            yield self.body
        elif self.body:
            yield Static(self.body)

    def compose(self):
        with Panel(title=self.title or None, floating=True, gap=1) as box:
            self.box = box
            yield from self.compose_body()
            with Row(gap=2):
                yield Spacer()
                for i, (label, result) in enumerate(self.buttons):
                    button = Button(label, variant="primary" if i == self.default else "default",
                                    on_press=functools.partial(self.choose, result))
                    if i == self.default:
                        self._default_button = button
                    yield button

    def on_mount(self) -> None:
        if self._default_button is not None:
            self._default_button.focus()

    def arrange(self, p) -> None:
        r = self.region
        w = min(r.w - p.ch * 6, round(p.ch * self.width))
        h = min(self.box.natural_size(p, w)[1], r.h - p.row * 2)
        y = r.y + max(p.row, (r.h - h) * 2 // 5)  # ortanın biraz üstü
        self.box._layout(p, pygame.Rect(r.x + (r.w - w) // 2, y, w, h))

    def render(self, p) -> None:
        p.shadow(self.box.frame)

    def choose(self, result: Any) -> None:
        """Bir butona basıldı: diyaloğu bu sonuçla kapat."""
        self.dismiss(result)

    def on_click(self, event: Click) -> None:
        event.stop()  # kutunun dışına tıklamak bir şey yapmaz

    @action("Kapat", key="escape", hint="kapat", palette=False)
    def close(self) -> None:
        self.dismiss(self.cancel)


class PromptDialog(Dialog):
    """Tek satırlık yazı soran diyalog: Enter ya da Tamam yazıyı, Esc ya da Vazgeç None döndürür."""

    def __init__(self, title: str = "", message: str = "", *, value: str = "", placeholder: str = "",
                 ok: str = "Tamam", cancel_label: str = "Vazgeç", **kwargs) -> None:
        super().__init__(title, message, buttons=[(cancel_label, False), (ok, True)], default=1, cancel=None,
                         **kwargs)
        self.input = Input(value, placeholder=placeholder)

    def compose_body(self):
        if self.body:
            yield Static(self.body)
        yield self.input

    def on_mount(self) -> None:
        self.input.focus()

    def choose(self, result: Any) -> None:
        self.dismiss(self.input.value if result is True else None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.choose(True)
