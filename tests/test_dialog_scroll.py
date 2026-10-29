"""Modal diyalog ve ScrollView testleri; pencere açmadan Pilot ile sürülür.

    python tests/test_dialog_scroll.py
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
from termik.filedialog import FileBrowser  # noqa: E402


def run(coro):
    return asyncio.run(coro)


# ── diyaloglar ────────────────────────────────────────────

class DialogApp(ui.App):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.results: list = []

    def compose(self):
        yield ui.Input(id="name")
        yield ui.Button("Sor", id="ask")

    @ui.action("Onayla", key="f5")
    async def ask_confirm(self) -> None:
        self.results.append(await self.confirm("Emin misin?"))

    @ui.action("Bilgi", key="f6")
    async def ask_alert(self) -> None:
        await self.alert("Bitti")
        self.results.append("alert")

    @ui.action("Sor", key="f7")
    async def ask_prompt(self) -> None:
        self.results.append(await self.prompt("Adın?", value="Efe"))


def test_confirm_keys_and_focus_restore():
    async def main():
        app = DialogApp()
        async with app.run_test() as pilot:
            await pilot.press("f5")
            assert isinstance(app.screen, ui.Dialog) and app.focused.label == "Evet"
            await pilot.press("tab")  # odak diyaloğun içinde döner
            assert app.focused.label == "Vazgeç"
            await pilot.press("tab", "enter")
            assert app.results == [True] and app.focused.id == "name"
            await pilot.press("f5", "escape")
            assert app.results == [True, False]
            await pilot.press("f5", "shift+tab", "enter")
            assert app.results == [True, False, False]
    run(main())


def test_alert_mouse_and_outside_click():
    async def main():
        app = DialogApp()
        async with app.run_test() as pilot:
            await pilot.press("f6")
            await pilot.click(app.screen, offset=(3, 3))  # dışarı tıklamak kapatmaz
            assert isinstance(app.screen, ui.Dialog) and app.results == []
            await pilot.click(app.screen.query_one(ui.Button))
            assert app.results == ["alert"] and not isinstance(app.screen, ui.Dialog)
    run(main())


def test_prompt():
    async def main():
        app = DialogApp()
        async with app.run_test() as pilot:
            await pilot.press("f7")
            dialog = app.screen
            assert app.focused is dialog.input and dialog.input.value == "Efe"
            await pilot.press("ctrl+a")
            await pilot.type("Ada")
            await pilot.press("enter")
            assert app.results == ["Ada"]
            await pilot.press("f7", "escape")
            assert app.results == ["Ada", None]
    run(main())


def test_push_screen_callback():
    async def main():
        app = DialogApp()
        async with app.run_test() as pilot:
            got: list = []
            app.push_screen(ui.Dialog("Seç", "Hangisi?", buttons=[("A", 1), ("B", 2)], default=0), callback=got.append)
            await pilot.pause()
            await pilot.press("tab", "enter")
            assert got == [2] and not app._errors
    run(main())


# ── ScrollView ────────────────────────────────────────────

class ScrollApp(ui.App):
    def compose(self):
        with ui.ScrollView(id="sv", height=8):
            for i in range(20):
                yield ui.Input(f"alan {i}", id=f"f{i}")
        yield ui.Button("son", id="last")


def visible_in(widget: ui.Widget, sv: ui.ScrollView) -> bool:
    return sv.content.top <= widget.region.top and widget.region.bottom <= sv.content.bottom


def test_scrollview_reveals_focus_and_scrolls():
    async def main():
        app = ScrollApp()
        async with app.run_test() as pilot:
            sv = app.query_one("#sv", ui.ScrollView)
            p = app.painter
            assert sv._virtual == 20 * p.row and sv.max_scroll == 20 * p.row - sv.content.h
            assert app.focused.id == "f0" and not sv.can_focus
            for _ in range(12):
                await pilot.press("tab")
            field = app.query_one("#f12")
            assert app.focused is field and visible_in(field, sv) and sv.scroll_y > 0
            before = sv.scroll_y
            await pilot.scroll(sv, 1)  # tekerlek yukarı
            assert sv.scroll_y == max(0, before - 3 * p.row)
            await pilot.press("pagedown")  # Input kullanmıyor: ScrollView'e kabarcıklanır
            assert sv.scroll_y > max(0, before - 3 * p.row)
            await pilot.press("shift+tab")
            assert visible_in(app.focused, sv)
    run(main())


def test_scrollview_keys_when_nothing_focusable():
    async def main():
        class TextScroll(ui.App):
            def compose(self):
                yield ui.ScrollView(ui.Static("\n".join(f"satır {i}" for i in range(40))), id="sv", height=6)

        app = TextScroll()
        async with app.run_test() as pilot:
            sv = app.query_one("#sv", ui.ScrollView)
            p = app.painter
            assert app.focused is sv
            await pilot.press("down")
            assert sv.scroll_y == p.row
            await pilot.press("end")
            assert sv.scroll_y == sv.max_scroll
            await pilot.press("home")
            assert sv.scroll_y == 0
            await pilot.press("pagedown")
            assert sv.scroll_y == sv.content.h - p.row
    run(main())


def test_scrollview_scrollbar_drag():
    async def main():
        app = ScrollApp()
        async with app.run_test() as pilot:
            sv = app.query_one("#sv", ui.ScrollView)
            c = sv.content
            top, _ = sv._thumb()
            grab, drop = (c.right - 3, top + 2), (c.right - 3, c.bottom + 20)
            app._mouse_move(grab, False)
            app._mouse_down(grab, 1)
            app._mouse_move(drop, True)
            app._mouse_up(drop, 1)
            await pilot.pause()
            assert sv.scroll_y == sv.max_scroll
            click = (c.right - 3, c.y + 2)  # çubuğun boş yerine tık: oraya atla
            await pilot.click(sv, offset=(click[0] - sv.region.x, click[1] - sv.region.y))
            assert sv.scroll_y == 0
    run(main())


def test_scrollview_short_content_lets_fr_grow():
    async def main():
        class Short(ui.App):
            def compose(self):
                with ui.ScrollView(id="sv", height=10):
                    yield ui.Static("başlık")
                    yield ui.Log(id="log")

        app = Short()
        async with app.run_test():
            sv, log = app.query_one("#sv", ui.ScrollView), app.query_one("#log")
            assert sv.max_scroll == 0 and log.region.bottom == sv.content.bottom
    run(main())


def test_demo_help_and_prompt():
    from termik.demo import uygulama as demo

    async def main():
        app = demo.BackupApp(ROOT)
        async with app.run_test(size=(1280, 800)) as pilot:
            await pilot.press("f1")
            dialog = app.screen
            assert isinstance(dialog, ui.Dialog) and dialog.query_one(ui.ScrollView).max_scroll > 0
            await pilot.press("escape")
            await pilot.press("ctrl+p")
            await pilot.type("hedef")
            await pilot.press("enter")  # palet → "Hedef klasörü seç…" → klasör diyaloğu (sahte sürücüde termik'in)
            browser = app.screen
            assert isinstance(browser, FileBrowser) and browser.mode == "folder"
            first = browser.tree.root.children[0].data
            await pilot.press("down", "space")
            assert app.query_one("#dst", ui.Input).value == first
            notes = app.query_one("#notes", ui.TextArea)
            notes.focus()
            await pilot.type("ilk not")
            assert "1 satır · 7 karakter" in app.query_one("#notes-panel", ui.Panel).info
            assert not app._errors
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
