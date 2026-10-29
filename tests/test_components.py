"""Yüzen kutular, menüler, açılır seçim, sekmeler, kaydırıcı ve ipucu testleri; pencere açmadan
Pilot ile sürülür.

    python tests/test_components.py
"""

from __future__ import annotations

import asyncio
import sys
import time
import traceback
from pathlib import Path

import _ortam  # noqa: E402,F401  (kullanıcının tercihlerinden yalıt)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import termik as ui  # noqa: E402
from termik.menu import MenuPopup  # noqa: E402
from termik.theme import CHOICES  # noqa: E402
from termik.widgets.select import _SelectPopup  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def offset(widget: ui.Widget, rect) -> tuple[int, int]:
    """rect'in ortası, bileşenin sol üstüne göre (Pilot.click için)."""
    return rect.centerx - widget.region.x, rect.centery - widget.region.y


# ── açılır seçim ve yüzen kutu ────────────────────────────

class SelectApp(ui.App):
    def __init__(self) -> None:
        super().__init__()
        self.changes: list = []
        self.pressed = 0

    def compose(self):
        with ui.Row():
            yield ui.Select(["Tam", "Artımlı", "Diferansiyel"], index=1, id="mod")
            yield ui.Spacer()
            yield ui.Button("Bas", id="bas", on_press=lambda _b: setattr(self, "pressed", self.pressed + 1))

    def on_select_changed(self, event: ui.Select.Changed) -> None:
        self.changes.append((event.index, event.value))


def test_select_cycle_open_and_filter():
    async def main():
        app = SelectApp()
        async with app.run_test() as pilot:
            sel = app.query_one("#mod", ui.Select)
            width = sel.region.w
            assert app.focused is sel and sel.value == "Artımlı"
            await pilot.press("right")  # listeyi açmadan sonraki
            assert sel.value == "Diferansiyel"
            await pilot.press("enter")
            popup = app.screen
            assert isinstance(popup, _SelectPopup) and popup.box.region.top >= sel.region.bottom  # altında açıldı
            assert app.focused is popup.list and popup.list.value == "Diferansiyel"
            await pilot.type("tam")
            await pilot.press("enter")
            assert sel.value == "Tam" and app.focused is sel and len(app.children) == 1
            assert sel.region.w == width  # değer değişince genişlik oynamaz
            await pilot.press("enter", "escape")  # vazgeçmek değeri değiştirmez
            assert sel.value == "Tam" and app.changes == [(2, "Diferansiyel"), (0, "Tam")]
            assert not app._errors
    run(main())


def test_popup_swallows_outside_click():
    async def main():
        app = SelectApp()
        async with app.run_test() as pilot:
            await pilot.click("#mod")
            assert isinstance(app.screen, _SelectPopup)
            await pilot.click(app.query_one("#bas"))  # dışarı tık listeyi kapatır, butona geçmez
            assert len(app.children) == 1 and app.pressed == 0 and app.focused is app.query_one("#mod")
            await pilot.click(app.query_one("#bas"))
            assert app.pressed == 1
    run(main())


# ── sekmeler ──────────────────────────────────────────────

def test_tabs_keys_mouse_and_reveal():
    class TabsApp(ui.App):
        def __init__(self) -> None:
            super().__init__()
            self.changes: list[str] = []

        def compose(self):
            with ui.Tabs(id="tabs"):
                with ui.Tab("Genel"):
                    yield ui.Input(id="ad")
                with ui.Tab("Gelişmiş"):
                    yield ui.Checkbox("Ayrıntılı günlük", id="detay")
                with ui.Tab("Hakkında"):
                    yield ui.Static("termik")

        def on_tabs_changed(self, event: ui.Tabs.Changed) -> None:
            self.changes.append(event.title)

    async def main():
        app = TabsApp()
        async with app.run_test() as pilot:
            tabs = app.query_one("#tabs", ui.Tabs)
            detay = app.query_one("#detay")
            assert app.focused is tabs and [t.display for t in tabs.tabs] == [True, False, False]
            await pilot.press("right")  # başlık odaktayken ←/→
            assert tabs.active == 1 and [t.display for t in tabs.tabs] == [False, True, False]
            await pilot.press("tab")  # Tab gizli sekmelere girmez
            assert app.focused is detay
            await pilot.press("ctrl+tab")  # odak gizlenen sekmede kalmaz, başlığa gelir
            assert tabs.active == 2 and app.focused is tabs
            await pilot.click(tabs, offset=offset(tabs, tabs._rects[0]))
            assert tabs.active == 0
            detay.focus()  # gizli sekmedeki bileşene odak: sekme açılır
            await pilot.pause()
            assert tabs.active == 1 and app.focused is detay
            assert app.changes == ["Gelişmiş", "Hakkında", "Genel", "Gelişmiş"] and not app._errors
    run(main())


# ── kaydırıcı ─────────────────────────────────────────────

def test_slider_keys_mouse_and_snapping():
    class SliderApp(ui.App):
        def __init__(self) -> None:
            super().__init__()
            self.values: list = []

        def compose(self):
            yield ui.Slider(60, min=0, max=100, step=5, id="ses")
            yield ui.Slider(0.5, min=0, max=1, step=0.1, id="oran")

        def on_slider_changed(self, event: ui.Slider.Changed) -> None:
            self.values.append((event.slider.id, event.value))

    async def main():
        app = SliderApp()
        async with app.run_test() as pilot:
            ses, oran = app.query_one("#ses", ui.Slider), app.query_one("#oran", ui.Slider)
            assert ses.value == 60 and isinstance(ses.value, int)
            await pilot.press("right")
            assert ses.value == 65
            await pilot.press("pageup")
            assert ses.value == 75
            await pilot.press("end", "right")  # sınırda kalır
            assert ses.value == 100
            await pilot.press("home")
            assert ses.value == 0
            x0, w = ses._track
            y = ses.region.centery
            await pilot.click(ses, offset=(x0 + w // 2 - ses.region.x, y - ses.region.y))
            assert ses.value == 50
            app._mouse_down((x0 + w // 4, y), 1)  # sürükle
            app._mouse_move((x0 + w + 40, y), True)
            app._mouse_up((x0 + w + 40, y), 1)
            await pilot.pause()
            assert ses.value == 100
            await pilot.scroll(ses, -1)
            assert ses.value == 95
            oran.set(0.73)
            assert oran.value == 0.7 and oran.format.format(oran.value) == "0.7"
            assert app.values[:3] == [("ses", 65), ("ses", 75), ("ses", 100)] and not app._errors
    run(main())


# ── menüler ───────────────────────────────────────────────

def test_menubar_keyboard_and_mouse():
    class MenuApp(ui.App):
        def __init__(self) -> None:
            super().__init__()
            self.log: list[str] = []

        def compose(self):
            yield ui.MenuBar(
                ui.Menu("&Dosya", [ui.MenuItem("Kaydet", "save"), ui.MenuItem("Yok", "olmayan_eylem"), None,
                                   ui.MenuItem("&Çık", "app.quit")]),
                ui.Menu("&Görünüm", [ui.MenuItem("Tema", lambda: self.log.append("tema"), checked=True)]),
            )
            yield ui.Input(id="ad")

        @ui.action("Kaydet", key="ctrl+s")
        def save(self) -> None:
            self.log.append("kaydet")

    async def main():
        app = MenuApp()
        async with app.run_test() as pilot:
            ad = app.query_one("#ad")
            assert app.focused is ad
            await pilot.press("alt+d")
            popup = app.screen
            assert isinstance(popup, MenuPopup) and popup.index == 0
            lst = popup.list
            assert [e and e[2] for e in lst.entries] == ["ctrl+s", None, None, "ctrl+q"]  # kısayollar eylemlerden
            await pilot.press("down")  # bulunamayan eylem soluk: atlanır
            assert lst.current == 3
            await pilot.press("right")  # komşu menü
            assert isinstance(app.screen, MenuPopup) and app.screen.index == 1
            await pilot.press("enter")
            assert app.log == ["tema"] and app.focused is ad and len(app.children) == 1
            await pilot.press("f10", "enter")  # ilk menünün ilk öğesi
            assert app.log == ["tema", "kaydet"]
            await pilot.press("alt+d", "escape")
            assert app.focused is ad and len(app.children) == 1
            bar = app.query_one(ui.MenuBar)
            await pilot.click(bar, offset=offset(bar, bar._rects[0]))
            assert isinstance(app.screen, MenuPopup) and app.screen.index == 0
            app._mouse_move(bar._rects[1].center, False)  # açıkken başka başlığa gelmek o menüyü açar
            await pilot.pause()
            assert app.screen.index == 1
            await pilot.click(app.screen, offset=(app.screen.region.w - 5, app.screen.region.h - 5))
            assert len(app.children) == 1
            await pilot.press("alt+d", "ç")  # menüde kısayol harfi (Türkçe gevşek): Çık
            assert not app._running and not app._errors
    run(main())


def test_context_menu_mouse_and_keyboard():
    class Liste(ui.Static):
        can_focus = True

        def __init__(self, log: list) -> None:
            super().__init__("sağ tıkla", id="liste")
            self.log = log

        def context_menu(self, event):
            self.log.append(("açıldı", event is not None))
            return [ui.MenuItem("Kopyala", lambda: self.log.append("kopyala")), None, ui.MenuItem("Kaydet", "save")]

    class ContextApp(ui.App):
        def __init__(self) -> None:
            super().__init__()
            self.log: list = []

        def compose(self):
            yield Liste(self.log)
            yield ui.Input(id="ad")

        @ui.action("Kaydet", key="ctrl+s")
        def save(self) -> None:
            self.log.append("kaydet")

    async def main():
        app = ContextApp()
        async with app.run_test() as pilot:
            liste = app.query_one("#liste")
            await pilot.click(liste, offset=(30, 5), button=3)
            popup = app.screen
            assert isinstance(popup, MenuPopup) and abs(popup.box.region.x - (liste.region.x + 30)) <= 2
            await pilot.press("enter")
            assert app.log == [("açıldı", True), "kopyala"]
            app.query_one("#ad").focus()
            await pilot.press("shift+f10")  # odaktakinin ve atalarının menüsü yok
            assert len(app.children) == 1
            liste.focus()
            await pilot.press("shift+f10", "down", "enter")  # ayraç atlanır
            assert app.log[-2:] == [("açıldı", False), "kaydet"] and not app._errors
    run(main())


# ── ipucu ve biçimler ─────────────────────────────────────

def test_tooltip_after_hover():
    class TipApp(ui.App):
        def compose(self):
            yield ui.Button("Başlat", id="b", tooltip="Yedeklemeyi [bold]başlatır[/]")
            yield ui.Static("ipucu yok", id="s")

    async def main():
        app = TipApp()
        async with app.run_test() as pilot:
            await pilot.hover("#b")
            assert app._tip is None
            await pilot.pause(0.7)
            assert app._tip is not None and app._tip[0] == "Yedeklemeyi [bold]başlatır[/]"
            app._render()
            await pilot.hover("#s")  # fare kımıldadı: gizlenir; ipucu olmayan yerde açılmaz
            await pilot.pause(0.7)
            assert app._tip is None
            await pilot.hover("#b")
            await pilot.pause(0.7)
            assert app._tip is not None
            await pilot.press("escape")  # tuşa basmak da gizler
            assert app._tip is None and not app._errors
    run(main())


def test_all_component_styles_render():
    class StylesApp(ui.App):
        def compose(self):
            yield ui.MenuBar(ui.Menu("&Dosya", [ui.MenuItem("Kaydet", key="ctrl+s", checked=False)]))
            with ui.Tabs():
                with ui.Tab("Bir"):
                    yield ui.Select(["a", "bb", "ccc"])
                    yield ui.Slider(30)
                with ui.Tab("[bold]İki[/]"):
                    yield ui.Static("iki")

    async def main():
        app = StylesApp()
        async with app.run_test() as pilot:
            for look in ("terminal", "modern"):
                for tabs in CHOICES["tabs"]:
                    for slider, select in zip(CHOICES["slider"], CHOICES["select"]):
                        app.set_theme(look=look, tabs=tabs, slider=slider, select=select)
                        await pilot.pause()
                        app._render()
            await pilot.press("alt+d")
            app._render()
            assert not app._errors
    run(main())


def test_demo_menu_context_menu_and_tabs():
    import os

    from termik.demo import uygulama as demo

    async def main():
        app = demo.BackupApp(ROOT)
        async with app.run_test(size=(1280, 800)) as pilot:
            await pilot.press("alt+d")
            assert isinstance(app.screen, MenuPopup) and app.screen.list.entries[0][2] == "f5"
            await pilot.press("escape")
            tree = app.query_one("#tree", ui.DirectoryTree)
            line = next(i for i, node in enumerate(tree.lines)
                        if node is not tree.root and node.data and os.path.isdir(node.data))
            y = tree.content.y + (line - tree._top) * app.painter.row + 3
            await pilot.click(tree, offset=(30, y - tree.region.y), button=3)  # sağ tık: o satırın menüsü
            assert isinstance(app.screen, MenuPopup)
            await pilot.press("h")  # Hedef yap
            assert app.query_one("#dst", ui.Input).value == tree.lines[line].data
            app.query_one("#zip").focus()
            await pilot.press("space")  # sıkıştırma kapandı: düzey seçilmez
            assert app.query_one("#level", ui.Slider).disabled
            app.query_one("#notes").focus()  # gizli sekmedeki alan: sekme açılır
            await pilot.pause()
            assert app.query_one("#side", ui.Tabs).active == 1 and not app._errors
    run(main())


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        started = time.perf_counter()
        try:
            fn()
        except Exception:
            failed += 1
            print(f"✗ {name}")
            traceback.print_exc()
        else:
            print(f"✓ {name}  ({time.perf_counter() - started:.2f} sn)")
    print(f"\n{len(tests) - failed}/{len(tests)} geçti")
    sys.exit(1 if failed else 0)
