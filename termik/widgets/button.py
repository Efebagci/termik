"""Buton."""

from __future__ import annotations

from typing import Callable

from ..events import Click, Message
from ..reactive import reactive
from ..widget import Widget, action


class Button(Widget):
    """Tıklanınca ya da odaktayken Enter/Space ile basılan buton.

    action= verilirse basılınca o eylem ebeveynlerde aranıp çalıştırılır ("app.quit" gibi
    önekli adlar doğrudan uygulamada); on_press= verilirse o fonksiyon çağrılır. Her durumda
    Button.Pressed mesajı yukarı iletilir. variant="primary" Enter'ın varsayılanı gibi öne çıkar.
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

    def __init__(self, label: str, *, action: str | None = None, variant: str = "default",
                 on_press: Callable | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.action = action
        self.variant = variant
        self.on_press = on_press

    @property
    def primary(self) -> bool:
        return self.variant == "primary"

    def measure(self, p, width: int) -> tuple[int, int]:
        return p.button_size(self.label, self.primary)

    def render(self, p) -> None:
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
        if self.action and not self.run_action(self.action):
            self.app.notify(f"eylem bulunamadı: {self.action}", "err")

    def on_click(self, event: Click) -> None:
        event.stop()
        self.press()

    @action("Bas", key="enter,space", show=False, palette=False)
    def activate(self) -> None:
        self.press()
