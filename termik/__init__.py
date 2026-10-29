"""termik — CLI estetiğinde, GUI rahatlığında Python arayüz kütüphanesi.

İki katmanı var. Akış API'si script'ler için, input()/print() kadar kısa:

    import termik

    ad = termik.ask("Adın?")
    termik.print(f"Merhaba [bold]{ad}[/]!")

Bileşen katmanı çok panelli uygulamalar için:

    import termik as ui

    class Merhaba(ui.App):
        def compose(self):
            with ui.Panel(title="Selam"):
                yield ui.Static("Merhaba [bold accent]dünya[/]!")
                yield ui.Button("Kapat", action="app.quit", variant="primary")

    Merhaba().run()
"""

import os

# pygame-ce içe aktarılırken basılan karşılama satırını sustur
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

__version__ = "0.9.0"

from . import settings  # noqa: E402
from .flow import (Field, Password, ask, ask_path, choose, choose_many, confirm, error, form,  # noqa: E402,A004
                   info, ok, print, progress, restyle, rule, setup, show, spinner, table, track, warn)
from .markup import escape, plain_text  # noqa: E402
from .theme import DENSITIES, LOOKS, THEMES, Theme, with_look  # noqa: E402

try:  # bileşen katmanı pygame-ce ister; yoksa akış API'si terminalde çalışmayı sürdürür
    import pygame as _pygame  # noqa: F401
except ImportError as _exc:
    _missing = _exc
else:
    _missing = None
    from .app import App, Pilot, Timer, Window  # noqa: E402
    from .dialog import Dialog, PromptDialog  # noqa: E402
    from .events import (Blur, Click, Drop, Focus, Key, Message, MouseDown, MouseEnter,  # noqa: E402
                         MouseLeave, MouseMove, MouseScroll, MouseUp, TextInput)
    from .menu import Menu, MenuBar, MenuItem  # noqa: E402
    from .palette import Command, CommandPalette  # noqa: E402
    from .popup import Popup  # noqa: E402
    from .reactive import reactive  # noqa: E402
    from .widget import Column, Row, Screen, Spacer, Widget, action  # noqa: E402
    from .widgets import (Button, Canvas, Checkbox, DirectoryTree, Form, Header, Image, Input, KeyBar,  # noqa: E402
                          Label, Log, OptionList, Panel, ProgressBar, RadioSet, ScrollView, Select, Slider,
                          Sparkline, Spinbox, Split, Static, StatusBar, Tab, Table, Tabs, TextArea, Tree, TreeNode)


def __getattr__(name: str):
    if _missing is not None and (name[:1].isupper() or name in ("action", "reactive", "clipboard")):
        raise ImportError(f"termik.{name} pygame-ce ister: pip install pygame-ce") from _missing
    raise AttributeError(f"module 'termik' has no attribute {name!r}")
