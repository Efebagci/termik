"""Mesajlar ve girdi olayları.

Mesajlar gönderen bileşenden başlayıp ebeveynlere doğru kabarcıklanır (bubble). Bir bileşen
mesajı `on_<ad>` metoduyla yakalar: Button.Pressed → on_button_pressed, Key → on_key,
MouseScroll → on_mouse_scroll. İşleyici `async def` olabilir; o zaman görev olarak çalışır.
event.stop() kabarcıklanmayı durdurur.
"""

from __future__ import annotations

import re


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class Message:
    """Bileşenler arası mesajların temeli."""

    bubble = True
    handler_name = "on_message"

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # Button.Pressed → on_button_pressed; üst düzey Key → on_key
        parts = [p for p in cls.__qualname__.split(".") if p != "<locals>"]
        cls.handler_name = "on_" + "_".join(_snake(p) for p in parts[-2:])

    def __init__(self) -> None:
        self.sender = None  # mesajı gönderen bileşen
        self._stopped = False

    def stop(self) -> None:
        """Kabarcıklanmayı durdur: üstteki bileşenler bu mesajı görmez."""
        self._stopped = True

    @property
    def stopped(self) -> bool:
        return self._stopped


class Event(Message):
    """Kullanıcı girdisinden doğan olayların temeli."""


class Key(Event):
    """Bir tuşa basıldı. key: "ctrl+s", "enter", "a"…; char: tuşun yazdığı karakter (varsa)."""

    def __init__(self, key: str, char: str | None = None) -> None:
        super().__init__()
        self.key = key
        self.char = char

    @property
    def is_printable(self) -> bool:
        """Yazı alanına harf olarak gidecek bir tuş mu (kısayol değil)."""
        return bool(self.char) and self.char.isprintable() and not self.key.startswith(("ctrl+", "alt+", "meta+"))


class TextInput(Event):
    """Klavyeden gelen yazı (Türkçe karakterler ve IME dahil); yalnızca odaktaki bileşene gider."""

    bubble = False

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class MouseEvent(Event):
    def __init__(self, x: int, y: int, button: int = 0) -> None:
        super().__init__()
        self.x, self.y, self.button = x, y, button

    @property
    def pos(self) -> tuple[int, int]:
        return self.x, self.y


class MouseDown(MouseEvent):
    """Fare tuşuna basıldı."""


class MouseUp(MouseEvent):
    """Fare tuşu bırakıldı."""


class Click(MouseEvent):
    """Fare tuşu basılıp aynı bileşenin üstünde bırakıldı. count=2 çift tık demektir."""

    def __init__(self, x: int, y: int, button: int = 0, count: int = 1) -> None:
        super().__init__(x, y, button)
        self.count = count


class MouseMove(MouseEvent):
    """Fare hareket etti. Sürüklerken (button > 0) basılan bileşene gider."""

    bubble = False


class MouseScroll(MouseEvent):
    """Tekerlek döndü: dy > 0 yukarı, dy < 0 aşağı."""

    def __init__(self, x: int, y: int, dx: int, dy: int) -> None:
        super().__init__(x, y)
        self.dx, self.dy = dx, dy


class Drop(Event):
    """Pencereye dosya ya da yazı bırakıldı (dosya yöneticisinden sürükle-bırak). Farenin altındaki
    bileşenden başlayıp yukarı iletilir. paths: bırakılan dosya ve klasörler (pathlib.Path),
    text: bırakılan yazı (yoksa None). Input ve TextArea yolu imleç yerine yazar."""

    def __init__(self, paths: list, text: str | None, x: int, y: int) -> None:
        super().__init__()
        self.paths = list(paths)
        self.text = text
        self.x, self.y = x, y

    @property
    def pos(self) -> tuple[int, int]:
        return self.x, self.y

    def as_text(self) -> str:
        """Yazı alanına girecek hali: tek yol olduğu gibi, birden çoğu tırnaklı ve boşlukla ayrık
        (terminale dosya bırakmak gibi); yazı bırakıldıysa yazının kendisi."""
        if not self.paths:
            return self.text or ""
        if len(self.paths) == 1:
            return str(self.paths[0])
        return " ".join(f'"{p}"' if " " in str(p) else str(p) for p in self.paths)


class MouseEnter(Event):
    """Fare bileşenin üstüne geldi."""

    bubble = False


class MouseLeave(Event):
    """Fare bileşenin üstünden ayrıldı."""

    bubble = False


class Focus(Event):
    """Bileşen odağı aldı."""

    bubble = False


class Blur(Event):
    """Bileşen odağı kaybetti."""

    bubble = False
