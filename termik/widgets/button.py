"""Buton."""

from __future__ import annotations

from typing import Callable

from ..draw import Painter
from ..events import Click, Message
from ..reactive import reactive
from ..markup import plain_text
from ..widget import Screen, Widget, action


class Button(Widget):
    """Tıklanınca ya da odaktayken Enter/Space ile basılan buton.

    İkinci argüman ne yapılacağıdır: bir fonksiyon (`Button("Kaydet", self.kaydet)`) ya da eylem adı
    (`Button("Çık", "app.quit")`; ad ebeveynlerde, "app." / "window." önekliler uygulamada ya da
    pencerede aranır). on_press= verilirse o da çağrılır (butonu alır). Her durumda Button.Pressed
    mesajı yukarı iletilir. key= butona kısayol verir: ekranın neresinde olunursa olsun o tuş butona
    basar ve kısayol satırında görünür. variant="primary" Enter'ın varsayılanı gibi öne çıkar.
    """

    default_width = "auto"
    default_height = "auto"
    can_focus = True
    cursor = "hand"
    label = reactive("", layout=True)

    class Pressed(Message):
        def __init__(self, button: Button) -> None:
            super().__init__()
            self.button = button

    def __init__(self, label: str, action: str | Callable | None = None, *, variant: str = "default",
                 on_press: Callable | None = None, key: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.action = action
        self.variant = variant
        self.on_press = on_press
        self.key = key
        self._shortcut_on: Widget | None = None  # kısayolun bağlandığı ekran

    def on_mount(self) -> None:
        if self.key:  # kısayol ekrana bağlanır: ekran üstteyken odak nerede olursa olsun çalışır
            screen = next((a for a in self.ancestors() if isinstance(a, Screen)), None)
            if screen is not None:
                screen.add_action(f"_button_{id(self)}", self.press, plain_text(self.label), key=self.key)
                self._shortcut_on = screen

    def on_unmount(self) -> None:
        screen, self._shortcut_on = self._shortcut_on, None
        if screen is not None:
            screen.remove_action(f"_button_{id(self)}")

    @property
    def primary(self) -> bool:
        return self.variant == "primary"

    def measure(self, p: Painter, width: int) -> tuple[int, int]:
        return p.button_size(self.label, self.primary)

    def render(self, p: Painter) -> None:
        h = p.button_size(self.label, self.primary)[1]
        c = self.content
        p.button(c.x, c.y + max(0, (c.h - h) // 2), self.label, primary=self.primary,
                 hot=not self.disabled and (self.hovered or self.has_focus))

    def press(self) -> None:
        if self.disabled:
            return
        self.post_message(Button.Pressed(self))
        if self.on_press is not None:
            self._call(self.on_press, self)
        if callable(self.action):
            self._call(self.action)
        elif self.action and not self.run_action(self.action):
            self.window.notify(f"eylem bulunamadı: {self.action}", "err")

    def on_click(self, event: Click) -> None:
        event.stop()
        self.press()

    @action("Bas", key="enter,space", show=False, palette=False)
    def activate(self) -> None:
        self.press()
