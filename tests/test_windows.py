"""Birden çok pencere, pencere simgesi, sürükle-bırak ve dosya diyalogları; pencere açmadan (SDL'in
sahte sürücüsüyle) Pilot ve elle üretilen pygame olaylarıyla sürülür.

    python tests/test_windows.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

import _ortam  # noqa: E402,F401  (kullanıcının tercihlerinden yalıt)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import termik as ui  # noqa: E402  (pygame'den önce: karşılama satırını sustursun)
import pygame  # noqa: E402
from termik import filedialog  # noqa: E402
from termik.filedialog import FileBrowser  # noqa: E402
from termik.icon import prompt_icon  # noqa: E402
from termik.palette import CommandPalette  # noqa: E402
from termik.theme import THEMES  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def post(kind: int, window: ui.Window | None = None, **attrs) -> None:
    """Gerçek bir pencereden gelmiş gibi pygame olayı kuyruğa koy (window verilmezse pencere bilgisi yok)."""
    if window is not None:
        attrs["window"] = window.native
    pygame.event.post(pygame.event.Event(kind, **attrs))


def key_event(window: ui.Window, char: str) -> None:
    post(pygame.KEYDOWN, window, key=ord(char), mod=0, unicode=char, scancode=0)
    post(pygame.TEXTINPUT, window, text=char)


def click_event(window: ui.Window, widget: ui.Widget) -> None:
    pos = widget.region.center
    post(pygame.MOUSEBUTTONDOWN, window, pos=pos, button=1)
    post(pygame.MOUSEBUTTONUP, window, pos=pos, button=1)


class Ayarlar(ui.Window):
    TITLE = "Ayarlar"
    SIZE = (520, 360)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.log: list = []
        self.ask_before_close = False

    def compose(self):
        yield ui.Input(id="ad")
        yield ui.Button("Uygula", on_press=lambda: self.log.append("uygula"), id="uygula")
        yield ui.Button("Tema", action="next_theme", id="tema")  # öneksiz: pencerede yok, uygulamada bulunur
        yield ui.Button("Kapat", action="window.close", id="kapat")
        yield ui.KeyBar(id="keys")

    async def can_close(self) -> bool:
        return not self.ask_before_close or await self.confirm("Kaydedilmedi. Kapatılsın mı?")


class Ana(ui.App):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.log: list = []
        self.drops: list = []
        self.allow_close = True

    def compose(self):
        yield ui.Input(id="ana")
        yield ui.Button("Bas", on_press=lambda: self.log.append("ana"), id="bas")
        yield ui.TextArea(id="not", height=4)
        yield ui.Static("bırakma alanı", id="alan")

    @ui.action("Sonraki tema", key="f2")
    def next_theme(self) -> None:
        self.log.append("tema")

    def on_drop(self, event: ui.Drop) -> None:
        self.drops.append((event.paths, event.text, event.sender))

    def can_close(self) -> bool:
        return self.allow_close


# ── pencereler ────────────────────────────────────────────

def test_open_close_and_wait_for_result():
    async def main():
        app = Ana()
        async with app.run_test() as pilot:
            results = []
            w = app.open_window(Ayarlar(), callback=results.append)
            await pilot.pause()
            assert w.is_open and app.windows == [app, w] and app.active_window is w
            assert w.native.size == (520, 360) and w.native is not app.native
            field = w.query_one("#ad")
            assert field.window is w and field.app is app and app.query_one("#ana").window is app
            assert w.focused is field and app.focused is app.query_one("#ana")  # her pencerenin kendi odağı
            assert w.frame_count >= 1 and app.frame_count >= 1
            with tempfile.TemporaryDirectory() as tmp:
                pilot.snapshot(os.path.join(tmp, "ek.png"), window=w)
                assert pygame.image.load(os.path.join(tmp, "ek.png")).get_size() == (520, 360)
            await pilot.click("#kapat")  # action="window.close"
            assert not w.is_open and results == [None] and app.windows == [app]
            assert app.active_window is app and not field.is_mounted and field._window is None

            async def opener():
                return await app.open_window_wait(Ayarlar())

            task = asyncio.ensure_future(opener())
            await pilot.pause()
            second = app.active_window
            assert isinstance(second, Ayarlar)
            second.close({"tema": "orman"})
            await pilot.pause()
            assert task.done() and task.result() == {"tema": "orman"}
            try:
                app.open_window(app)
            except RuntimeError:
                pass
            else:
                raise AssertionError("açık pencere yeniden açılmamalı")
    run(main())


def test_events_go_to_their_window():
    async def main():
        app = Ana()
        async with app.run_test() as pilot:
            w = app.open_window(Ayarlar())
            await pilot.pause()
            click_event(w, w.query_one("#uygula"))
            click_event(app, app.query_one("#bas"))
            await pilot.pause()
            assert w.log == ["uygula"] and app.log == ["ana"]
            assert w.focused is w.query_one("#uygula") and app.focused is app.query_one("#bas")
            w.query_one("#ad").focus()
            app.query_one("#ana").focus()
            key_event(w, "x")  # pencere bilgisi olan tuş o pencereye
            await pilot.pause()
            assert w.query_one("#ad").value == "x" and app.query_one("#ana").value == ""
            post(pygame.WINDOWFOCUSGAINED, app)
            post(pygame.KEYDOWN, key=ord("y"), mod=0, unicode="y", scancode=0)  # pencere bilgisi yok:
            post(pygame.TEXTINPUT, text="y")                                   # klavye odağındakine
            await pilot.pause()
            assert app.active_window is app and app.query_one("#ana").value == "y"
            post(pygame.WINDOWFOCUSGAINED, w)
            await pilot.pause()
            assert app.active_window is w
            await pilot.click(w.query_one("#tema"))  # öneksiz eylem ek pencerede yoksa uygulamada aranır
            assert app.log == ["ana", "tema"]
            native = w.native
            post(pygame.WINDOWCLOSE, w)  # ✕: can_close() izin verir
            await pilot.pause()
            assert not w.is_open and app._running
            pygame.event.post(pygame.event.Event(pygame.TEXTINPUT, text="z", window=native))  # kapanmış pencereden
            pygame.event.post(pygame.event.Event(pygame.WINDOWCLOSE, window=None))  # penceresi bulunamayan olay
            await pilot.pause()
            assert app.query_one("#ana").value == "y" and app._running
    run(main())


def test_shortcuts_palette_and_close_request():
    async def main():
        app = Ana()
        async with app.run_test() as pilot:
            w = app.open_window(Ayarlar())
            await pilot.pause()
            shown = [(key, hint) for key, hint, _, _ in w.active_bindings()]
            assert shown == [("tab", "sonraki"), ("ctrl+p", "komutlar"), ("ctrl+w", "kapat"), ("ctrl+q", "çık")]
            assert [k for k, *_ in app.active_bindings()] == ["f2", "tab", "ctrl+p", "ctrl+q"]  # ana pencerede ctrl+w yok
            await pilot.press("ctrl+p")
            assert isinstance(w.screen, CommandPalette) and len(app.children) == 1  # palet kendi penceresinde
            labels = [c.label for c in w.screen.commands]
            assert "Pencereyi kapat" in labels and any(label.startswith("Tema: ") for label in labels)
            await pilot.press("escape")
            w.ask_before_close = True
            await pilot.press("ctrl+w")
            assert w.is_open and isinstance(w.screen, ui.Dialog)  # can_close sordu
            await pilot.press("escape")  # hayır
            assert w.is_open and len(w.children) == 1
            await pilot.press("ctrl+w", "enter")  # evet
            assert not w.is_open
            app.allow_close = False
            post(pygame.WINDOWCLOSE, app)
            await pilot.press("ctrl+q")
            assert app._running  # ana pencerenin can_close'u izin vermedi
            app.allow_close = True
            await pilot.press("ctrl+q")
            assert not app._running
    run(main())


def test_modal_window_blocks_the_others():
    async def main():
        app = Ana()
        async with app.run_test() as pilot:
            tool = app.open_window(Ayarlar(title="Araç"))
            modal = tool.open_window(Ayarlar(title="Soru"), modal=True)
            await pilot.pause()
            assert app._blocked and tool._blocked and not modal._blocked
            assert modal.native.position[0] >= 0  # açanın ortasına yerleşti
            click_event(app, app.query_one("#bas"))
            click_event(tool, tool.query_one("#uygula"))
            key_event(app, "q")
            post(pygame.WINDOWCLOSE, app)
            await pilot.pause()
            assert app.log == [] and tool.log == [] and app.query_one("#ana").value == "" and app._running
            click_event(modal, modal.query_one("#uygula"))
            await pilot.pause()
            assert modal.log == ["uygula"]
            modal.close()
            await pilot.pause()
            assert not app._blocked and not tool._blocked and app.active_window is tool
            click_event(app, app.query_one("#bas"))
            await pilot.pause()
            assert app.log == ["ana"]
    run(main())


def test_theme_reaches_every_window_and_icon():
    async def main():
        icons: list = []
        from termik import app as app_module
        original = app_module.system.set_icon
        app_module.system.set_icon = lambda native, make: icons.append((native, make(32)))
        try:
            app = Ana(theme="okyanus")
            async with app.run_test() as pilot:
                w = app.open_window(Ayarlar())
                await pilot.pause()
                assert [native for native, _ in icons] == [app.native, w.native]
                icons.clear()
                app.set_theme("orman")
                assert app._dirty and w._dirty and w.theme.name == "orman"
                assert [native for native, _ in icons] == [app.native, w.native]
                assert icons[0][1].get_at((8, 10))[:3] == prompt_icon(THEMES["orman"], 32).get_at((8, 10))[:3]
                custom = pygame.Surface((16, 16))
                custom.fill((255, 0, 0))
                icons.clear()
                w.set_icon(custom)
                app.set_theme("neon")  # kendi simgesi olan pencerenin simgesi tema değişince değişmez
                assert [native for native, _ in icons] == [w.native, app.native]
                assert icons[0][1].get_size() == (32, 32) and icons[0][1].get_at((16, 16))[:3] == (255, 0, 0)
        finally:
            app_module.system.set_icon = original
        icon = prompt_icon(THEMES["okyanus"], 64)
        th = THEMES["okyanus"]
        near = lambda a, b: max(abs(x - y) for x, y in zip(a[:3], b)) < 40  # noqa: E731
        assert icon.get_size() == (64, 64)
        assert near(icon.get_at((17, 19)), th.accent)  # ❯'nin üst kolu
        assert near(icon.get_at((47, 32)), th.text)    # imleç bloğu
        assert icon.get_at((0, 0))[3] < 60             # yuvarlak köşe saydam
    run(main())


# ── sürükle-bırak ─────────────────────────────────────────

def test_drop_files_and_text():
    async def main():
        app = Ana()
        async with app.run_test() as pilot:
            with tempfile.TemporaryDirectory() as tmp:
                a, b = Path(tmp, "a.txt"), Path(tmp, "b c.txt")
                field = app.query_one("#ana")
                await pilot.drop(field, a)
                assert field.value == str(a) and app.focused is field and app.drops == []
                await pilot.drop(field, b, offset=(0, 0))  # bırakılan yere eklenir (başa)
                assert field.value == str(b) + str(a)
                note = app.query_one("#not")
                await pilot.drop(note, a, b)
                assert note.text == f"{a}\n{b}"
                await pilot.drop("#alan", "düz yazı")  # yazı alanı değil: mesaj uygulamaya kadar çıkar
                assert app.drops[-1][:2] == ([], "düz yazı")
                assert ui.Drop([a, b], None, 0, 0).as_text() == f'{a} "{b}"'
                # dosya yöneticisinden gerçek olay sırası: birlikte bırakılanlar tek mesaj, farenin altına
                from termik import app as app_module
                mouse_in = app_module.system.mouse_in
                app_module.system.mouse_in = lambda native: app.query_one("#alan").region.center
                try:
                    post(pygame.DROPBEGIN, app)
                    post(pygame.DROPFILE, app, file=str(a))
                    post(pygame.DROPFILE, app, file=str(b))
                    post(pygame.DROPCOMPLETE, app)
                    await pilot.pause()
                finally:
                    app_module.system.mouse_in = mouse_in
                assert app.drops[-1][0] == [a, b] and app.drops[-1][2] is app.query_one("#alan")
                count = len(app.drops)
                w = app.open_window(Ayarlar(), modal=True)
                post(pygame.DROPFILE, app, file=str(a))  # modal pencerenin altındakine bırakılamaz
                await pilot.pause()
                assert len(app.drops) == count
                await pilot.drop(w.query_one("#ad"), a)
                assert w.query_one("#ad").value == str(a)
    run(main())


# ── dosya diyalogları ─────────────────────────────────────

def _files(tmp: str) -> None:
    Path(tmp, "alt").mkdir()
    Path(tmp, "alt", "derin.txt").write_text("x", encoding="utf-8")
    for name in ("a.txt", "b.txt", "resim.png"):
        Path(tmp, name).write_text("x", encoding="utf-8")


def test_builtin_file_browser():
    async def main():
        app = Ana(dialogs="builtin")
        async with app.run_test() as pilot:
            with tempfile.TemporaryDirectory() as tmp:
                _files(tmp)
                task = asyncio.ensure_future(app.ask_open("Aç", folder=tmp, filetypes=[("Metin", "*.txt")]))
                await pilot.pause()
                browser = app.screen
                assert isinstance(browser, FileBrowser) and app.focused is browser.tree
                names = [os.path.basename(n.data) for n in browser.tree.root.children]
                assert names == ["alt", "a.txt", "b.txt"]  # süzgeç: png görünmez
                await pilot.press("down", "down", "enter")  # alt'ı geç, a.txt'de ⏎
                assert await task == Path(tmp, "a.txt")

                task = asyncio.ensure_future(app.ask_open(folder=tmp, multiple=True))
                await pilot.pause()
                await pilot.press("down", "down", "space", "down", "space", "down", "enter")
                assert await task == [Path(tmp, "a.txt"), Path(tmp, "b.txt"), Path(tmp, "resim.png")]

                task = asyncio.ensure_future(app.ask_folder(folder=tmp))
                await pilot.pause()
                assert [os.path.basename(n.data) for n in app.screen.tree.root.children] == ["alt"]
                await pilot.press("down", "space")
                assert await task == Path(tmp, "alt")

                task = asyncio.ensure_future(app.ask_save(folder=tmp, name="rapor", filetypes=[("Markdown", "*.md")]))
                await pilot.pause()
                assert app.focused is app.screen.filename
                await pilot.press("enter")
                assert await task == Path(tmp, "rapor.md")  # uzantı süzgeçten

                task = asyncio.ensure_future(app.ask_save(folder=tmp, name="a.txt"))
                await pilot.pause()
                await pilot.press("enter")
                assert isinstance(app.screen, ui.Dialog) and not isinstance(app.screen, FileBrowser)  # üzerine yazılsın mı?
                await pilot.press("enter")
                assert await task == Path(tmp, "a.txt")

                task = asyncio.ensure_future(app.ask_open(folder=tmp))
                await pilot.pause()
                await pilot.press("escape")
                assert await task is None
    run(main())


def test_native_dialog_backend_and_fallback():
    async def main():
        app = Ana()
        assert app.dialogs == "native"
        calls = []

        def fake(mode, title, folder, name, filters, multiple, owner):
            calls.append((mode, title, folder, name, filters, multiple, app._blocked))
            time.sleep(0.05)
            return [str(Path(folder, "a.txt"))] if multiple else str(Path(folder, "a.txt"))

        def missing(*args):
            raise filedialog.Unavailable

        original = filedialog._backend
        try:
            async with app.run_test() as pilot:
                app._headless = False  # sahte sürücüde yerel diyalog hiç denenmez; burada deneyelim
                with tempfile.TemporaryDirectory() as tmp:
                    _files(tmp)
                    filedialog._backend = lambda: fake
                    result = await app.ask_open("Seç", folder=tmp, filetypes=[("Metin", "*.txt *.md")])
                    assert result == Path(tmp, "a.txt")
                    assert calls[-1] == ("open", "Seç", tmp, "", [("Metin", ["*.txt", "*.md"])], False, True)
                    assert not app._blocked  # diyalog kapanınca pencere yeniden girdi alır
                    assert await app.ask_open(folder=tmp, multiple=True) == [Path(tmp, "a.txt")]
                    filedialog._backend = lambda: missing
                    task = asyncio.ensure_future(app.ask_save(folder=tmp))
                    await pilot.pause()
                    assert isinstance(app.screen, FileBrowser)  # yerel diyalog yok: termik gezgini
                    await pilot.press("escape")
                    assert await task is None
                    app.dialogs = "builtin"
                    filedialog._backend = lambda: fake
                    count = len(calls)
                    task = asyncio.ensure_future(app.ask_folder(folder=tmp))
                    await pilot.pause()
                    assert isinstance(app.screen, FileBrowser) and len(calls) == count
                    await pilot.press("escape")
                    await task
        finally:
            filedialog._backend = original
    run(main())


def test_demo_settings_window_drop_and_dialogs():
    from termik.demo import uygulama as demo

    async def main():
        app = demo.BackupApp(ROOT, theme="okyanus", density="rahat")
        async with app.run_test(size=(1280, 800)) as pilot:
            await pilot.press("alt+g", "a")  # Görünüm → Ayarlar…
            settings_window = app.active_window
            assert isinstance(settings_window, demo.SettingsWindow) and app.windows == [app, settings_window]
            theme = settings_window.query_one("#theme", ui.Select)
            assert settings_window.focused is theme
            await pilot.press("right")  # sonraki tema: iki pencereye de yansır
            assert app.theme.name == list(THEMES)[1] and settings_window.theme.name == app.theme.name
            assert app._dirty or app.frame_count > 0
            app.query_one("#src").focus()
            await pilot.pause()
            app._key("f4", None)  # ana penceredeki kısayol ayarlar penceresindeki seçimi de günceller
            await pilot.pause()
            assert settings_window.query_one("#density", ui.Select).value == app.density != "rahat"
            await pilot.click(settings_window.query_one("#dialogs", ui.Select))
            await pilot.press("down", "enter")
            assert app.dialogs == "builtin"
            app.open_settings()  # açıkken yenisi açılmaz
            assert len(app.windows) == 2
            settings_window.close()
            await pilot.pause()
            assert app.windows == [app] and app.active_window is app
            with tempfile.TemporaryDirectory() as tmp:
                await pilot.drop("#history", Path(tmp))  # pencereye bırakılan klasör kaynak olur
                assert app.query_one("#src", ui.Input).value == tmp
                await pilot.drop("#dst", Path(tmp, "alt"))  # yol alanına bırakılan yol oradakinin yerine
                assert app.query_one("#dst", ui.Input).value == str(Path(tmp, "alt"))
            await pilot.press("ctrl+o")  # sahte sürücüde termik gezgini
            assert isinstance(app.screen, FileBrowser) and app.screen.mode == "folder"
            await pilot.press("escape")
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
