"""Resim, Canvas, sayı alanı (Spinbox) ve bölünebilir panel (Split) testleri; pencere açmadan Pilot ile.

    python tests/test_extras.py
"""

from __future__ import annotations

import asyncio
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
from termik.theme import CHOICES  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def near(a, b, tolerance: int = 12) -> bool:
    return max(abs(x - y) for x, y in zip(a[:3], b[:3])) <= tolerance


def sample(path: Path, size=(200, 100), color=(200, 40, 40)) -> Path:
    img = pygame.Surface(size)
    img.fill(color)
    pygame.image.save(img, str(path))
    return path


# ── resim ─────────────────────────────────────────────────

def test_image_fit_styles_and_errors():
    async def main():
        with tempfile.TemporaryDirectory() as tmp:
            red = sample(Path(tmp, "kirmizi.png"))

            class App(ui.App):
                def compose(self):
                    yield ui.Image(red, id="dogal")
                    yield ui.Image(red, height=6, width=60, fit="contain", frame=False, id="sig")
                    yield ui.Image(Path(tmp, "yok.png"), height=3, id="yok")
                    yield ui.Image(height=3, caption="boş", id="bos")

            app = App()
            async with app.run_test() as pilot:
                p = app.painter
                natural = app.query_one("#dogal", ui.Image)
                assert natural.content.size == (200, 100)  # doğal boyut (ölçek 1)
                fit = app.query_one("#sig", ui.Image)
                box = fit._box(fit.content)
                assert box.h == fit.content.h and box.w == round(fit.content.h * 2)  # oran korunur
                assert box.centerx == fit.content.centerx
                for mode, check in (("cover", lambda b, c: b.w == c.w and b.h >= c.h),
                                    ("stretch", lambda b, c: b.size == c.size),
                                    ("none", lambda b, c: b.size == (200, 100))):
                    fit.fit = mode
                    assert check(fit._box(fit.content), fit.content), mode
                fit.fit = "contain"
                missing = app.query_one("#yok", ui.Image)
                assert missing.image is None and "açılamadı" in missing._error
                surf = app.native.get_surface()
                c = natural.content
                assert near(surf.get_at(c.center), (200, 40, 40))
                for style in CHOICES["image"]:
                    app.set_theme(image=style)
                    await pilot.pause()
                    assert near(surf.get_at(fit.content.center), (200, 40, 40)), style
                    scaled = fit._cache[1]
                    if style == "blocks":
                        assert scaled.get_width() % p.ch == 0 and scaled.get_height() % p.row == 0
                    if style == "pixel":
                        assert scaled.get_width() % max(2, p.ch // 2) == 0
                paletted = pygame.Surface((10, 10), depth=8)  # smoothscale 24/32 bit ister: çevrilir
                missing.source = paletted
                await pilot.pause()
                assert missing.image.get_bitsize() == 32 and missing._error is None
                assert not app._errors
    run(main())


# ── canvas ────────────────────────────────────────────────

def test_canvas_draw_list_units_and_messages():
    async def main():
        events = []

        class App(ui.App):
            def compose(self):
                yield ui.Canvas(height=10, background="bg", id="c")

            def on_canvas_clicked(self, event):
                events.append(("tık", round(event.x, 1), round(event.y, 1), event.button))

            def on_canvas_dragged(self, event):
                events.append(("sürük", round(event.x), round(event.y)))

        app = App()
        async with app.run_test() as pilot:
            c = app.query_one("#c", ui.Canvas)
            p, th = app.painter, app.theme
            box = c.rect(2, 2, 4, 3, fill="accent")
            c.line(0, 0, 10, 0, color="green", width=3)
            c.circle(20, 5, 2, fill="red")
            c.rect(100, 100, 20, 10, fill="yellow", px=True)
            c.text(30, 1, "[bold]yazı[/]")
            c.lines([(0, 9), (5, 8), (10, 9)], color="blue")
            c.polygon([(40, 1), (44, 1), (42, 4)], fill="magenta")
            assert len(c) == 7
            await pilot.pause()
            surf = app.native.get_surface()
            at = lambda x, y: surf.get_at((round(c.content.x + x * p.ch), round(c.content.y + y * p.row)))  # noqa: E731
            assert near(at(4, 3.5), th.accent) and near(at(20, 5), th.red) and near(at(42, 2.5), th.magenta)
            assert near(surf.get_at((c.content.x + 110, c.content.y + 105)), th.yellow)
            assert near(at(5, 0), th.green, 30)
            w, h = c.size
            assert round(w) == round(c.content.w / p.ch) and h == 10
            c.remove(box)
            await pilot.pause()
            assert len(c) == 6 and not near(at(4, 3.5), th.accent)
            app.set_theme("orman")  # ad verilen renkler temayla değişir
            await pilot.pause()
            assert near(at(20, 5), app.theme.red)
            await pilot.click(c, offset=(round(3 * p.ch), round(2 * p.row)))
            assert events[-1] == ("tık", 3.0, 2.0, 1)
            win = c.window
            start = (c.content.x + 10, c.content.y + 10)
            win._mouse_down(start, 1)
            win._mouse_move((c.content.x + 10 * p.ch, c.content.y + 4 * p.row), True)
            win._mouse_up((c.content.x + 10 * p.ch, c.content.y + 4 * p.row), 1)
            assert ("sürük", 10, 4) in events
            c.clear()
            assert len(c) == 0 and not app._errors
    run(main())


# ── sayı alanı ────────────────────────────────────────────

def test_spinbox_keys_typing_and_mouse():
    async def main():
        changes = []

        class App(ui.App):
            def compose(self):
                yield ui.Spinbox(12, min=1, max=99, id="adet", on_change=changes.append)
                yield ui.Spinbox(0.5, min=0, max=1, step=0.05, id="oran")
                yield ui.Spinbox(0, step=2, id="serbest")
                yield ui.Input(id="sonra")

        app = App()
        async with app.run_test() as pilot:
            adet = app.query_one("#adet", ui.Spinbox)
            assert app.focused is adet and adet.text_value() == "12"
            await pilot.press("up", "up", "down")
            assert adet.value == 13 and changes[-1] == 13
            await pilot.press("pageup")
            assert adet.value == 23
            await pilot.press("end")
            assert adet.value == 99
            await pilot.press("pageup")  # sınırda kalır
            assert adet.value == 99
            await pilot.press("home")
            assert adet.value == 1
            await pilot.type("42")  # yazmak değeri baştan yazar
            assert adet.editing and adet._label() == "42" and adet.value == 1
            await pilot.press("enter")
            assert adet.value == 42 and not adet.editing
            await pilot.type("7")
            await pilot.press("escape")  # vazgeç
            assert adet.value == 42 and not adet.editing
            await pilot.type("500")
            await pilot.press("enter")  # sınırın üstü: en büyüğe oturur
            assert adet.value == 99
            await pilot.type("-3")  # min >= 0: eksi yazılmaz
            assert adet._label() == "3"
            await pilot.press("backspace", "enter")  # boşalan alan: değer değişmez
            assert adet.value == 99
            await pilot.press("backspace", "backspace", "1", "tab")  # 99 → 9 → "" → 1, odaktan çıkınca onaylanır
            assert adet.value == 1
            oran = app.query_one("#oran", ui.Spinbox)
            assert app.focused is oran and oran.text_value() == "0.50"
            await pilot.press("up")
            assert oran.value == 0.55
            await pilot.type("0,25")  # virgül de ondalık ayırıcı
            await pilot.press("enter")
            assert oran.value == 0.25
            free = app.query_one("#serbest", ui.Spinbox)
            free.focus()
            await pilot.type("-8")
            await pilot.press("enter", "down")
            assert free.value == -10
            await pilot.click(adet, offset=(adet._plus.centerx - adet.region.x, 5))
            await pilot.click(adet, offset=(adet._plus.centerx - adet.region.x, 5))
            assert adet.value == 3
            await pilot.click(adet, offset=(adet._minus.centerx - adet.region.x, 5))
            assert adet.value == 2
            await pilot.scroll(adet, 1)
            assert adet.value == 3
            adet.disabled = True
            await pilot.scroll(adet, 1)
            assert adet.value == 3
            for style in CHOICES["spin"]:  # her biçimde düğmeler tıklanır
                adet.disabled = False
                app.set_theme(spin=style)
                await pilot.pause()
                before = adet.value
                await pilot.click(adet, offset=(adet._plus.centerx - adet.region.x, adet._plus.centery - adet.region.y))
                assert adet.value == before + 1, style
            try:
                ui.Spinbox(1, min=5, max=1)
            except ValueError:
                pass
            else:
                raise AssertionError("max > min olmalı")
            assert not app._errors
    run(main())


# ── bölünebilir panel ─────────────────────────────────────

class SplitApp(ui.App):
    def compose(self):
        with ui.Split(sizes=[30, "1fr"], id="yatay"):
            yield ui.Panel(ui.Input(id="sol"), title="Sol")
            with ui.Split(direction="column", id="dikey"):
                yield ui.Panel(ui.Input(id="ust"), title="Üst", height=6)
                yield ui.Panel(ui.Static("alt"), title="Alt")

    def on_split_resized(self, event):
        self.resized = getattr(self, "resized", 0) + 1


def test_split_drag_keys_and_proportions():
    async def main():
        app = SplitApp()
        async with app.run_test(size=(1000, 600)) as pilot:
            p = app.painter
            split = app.query_one("#yatay", ui.Split)
            left, right = split._kids()
            assert left.region.w == 30 * p.ch and len(split._seps) == 1
            assert left.region.w + p.ch + right.region.w == split.content.w  # ayraç bir karakter
            dikey = app.query_one("#dikey", ui.Split)
            assert dikey._kids()[0].region.h == 6 * p.row
            sep = split._seps[0]
            await pilot.hover(split, offset=(sep.centerx - split.region.x, sep.centery - split.region.y))
            assert split.cursor == "ew" and split._hover_sep == 0
            await pilot.hover("#sol")
            assert split.cursor is None  # panelin üstünde yeniden boyutlandırma imleci yok
            win = split.window
            grab = (sep.centerx, sep.centery)
            win._mouse_down(grab, 1)
            win._mouse_move((grab[0] + 100, grab[1]), True)
            win._mouse_up((grab[0] + 100, grab[1]), 1)
            await pilot.pause()
            assert left.region.w == 30 * p.ch + 100 and app.resized >= 1
            fractions = split.fractions
            split._layout(p, pygame.Rect(0, 0, 2 * split.region.w, split.region.h))  # pencere büyüdü: oran korunur
            assert abs(left.region.w / (left.region.w + right.region.w) - fractions[0]) < 0.01
            await pilot.pause()  # (yerleşim yeniden pencere boyutunda)
            win._mouse_down(split._seps[0].center, 1)
            win._mouse_move((0, split._seps[0].centery), True)  # en sola: min_size'ta durur
            win._mouse_up((0, split._seps[0].centery), 1)
            await pilot.pause()
            assert left.region.w == 6 * p.ch
            app.query_one("#sol").focus()
            await pilot.press("alt+shift+right")
            assert left.region.w == 8 * p.ch
            sep = split._seps[0]
            await pilot.click(split, offset=(sep.centerx - split.region.x, sep.centery - split.region.y))
            await pilot.click(split, offset=(sep.centerx - split.region.x, sep.centery - split.region.y))
            assert split._fractions is None and left.region.w == 30 * p.ch  # çift tık başa döndürür
            split.set_fractions([1, 3])
            await pilot.pause()
            assert abs(left.region.w - (split.content.w - p.ch) / 4) <= 1
            app.query_one("#ust").focus()
            before = dikey._kids()[0].region.h
            await pilot.press("alt+shift+down")  # içteki (dikey) ayraç
            assert dikey._kids()[0].region.h == before + p.row
            for style in CHOICES["split"]:
                app.set_theme(split=style)
                await pilot.pause()
            assert not app._errors
    run(main())


def test_demo_columns_preview_disk_and_keep():
    from termik.demo import uygulama as demo

    async def main():
        with tempfile.TemporaryDirectory() as tmp:
            sample(Path(tmp, "foto.png"), size=(64, 48))
            Path(tmp, "not.txt").write_text("x", encoding="utf-8")
            app = demo.BackupApp(tmp)
            async with app.run_test(size=(1280, 800)) as pilot:
                columns = app.query_one("#columns", ui.Split)
                assert len(columns._seps) == 2 and columns._kids()[0].region.w == 32 * app.painter.ch
                assert len(app.query_one("#disk", ui.Canvas)) >= 3  # halka, dolu kısım, yazılar
                tree = app.query_one("#tree", ui.DirectoryTree)
                tree.focus()
                image_line = next(i for i, n in enumerate(tree.lines) if n.data and n.data.endswith("foto.png"))
                tree.move_cursor(image_line)
                await pilot.pause()
                preview = app.query_one("#preview", ui.Image)
                assert preview.image is not None and "64×48" in preview.caption
                await pilot.press("enter")
                assert app.query_one("#side", ui.Tabs).active == 2
                keep = app.query_one("#keep", ui.Spinbox)
                keep.focus()
                await pilot.press("up", "up")
                assert keep.value == 7
                app.use_target(tmp)  # hedef değişince disk halkası yeniden çizilir
                assert len(app.query_one("#disk", ui.Canvas)) >= 3
                await pilot.pause()
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
