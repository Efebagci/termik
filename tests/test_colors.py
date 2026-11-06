"""Renkler ve paneller: üç renkli palet, tema oluşturma, öge türü rolleri, öge başına renk, panel
çerçevesi ve odak işareti, tam ekran düğmesi. Pencere açmadan Pilot ile.

    python tests/test_colors.py
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

import termik as ui  # noqa: E402  (pygame'den önce: karşılama satırını sustursun)
from termik import settings  # noqa: E402
from termik.theme import CHOICES, THEMES, hex_color, mix  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def near(a, b, tolerance: int = 14) -> bool:
    return max(abs(x - y) for x, y in zip(a[:3], b[:3])) <= tolerance


def colours(surface, rect):
    return [surface.get_at((x, y)) for x in range(rect.left, rect.right) for y in range(rect.top, rect.bottom)]


def test_palette_names_and_three_colors():
    for name, theme in THEMES.items():
        assert len(theme.palette) == 3 and len(set(theme.palette)) == 3, name  # her tema üç ayrı renk
    th = THEMES["okyanus"]
    for spec, expected in ((1, th.accent), (2, th.accent2), (3, th.accent3), (4, th.accent),
                           ("primary", th.accent), ("secondary", th.accent2), ("tertiary", th.accent3),
                           ("birincil", th.accent), ("ikincil", th.accent2), ("üçüncül", th.accent3),
                           ("accent3", th.accent3), ("green", th.green), ("#ff8800", (255, 136, 0)),
                           ((1, 2, 3), (1, 2, 3))):
        assert th.resolve(spec) == expected, spec
    assert th.color("yok") is None
    shifted = th.tinted(2)
    assert (shifted.accent, shifted.accent2, shifted.accent3) == (th.accent2, th.accent3, th.accent)


def test_make_and_register_theme():
    t = ui.make_theme("deneme-dört", ["#ff0000", "#00ff00", "#0000ff", "#ffff00"], neutral="#777777")
    assert t.palette == ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0))
    assert t.resolve("quaternary") == t.resolve("dördüncül") == t.resolve(4) == (255, 255, 0)
    one = ui.make_theme("tek", ["#3366ff"])  # eksikler renk çemberinde türetilir
    assert len(set(one.palette)) == 3
    dark = ui.make_theme("koyu", accent="#22aa88", background="#000000")
    assert dark.bg[0] < 10 and dark.accent == hex_color("#22aa88")
    try:
        ui.make_theme("boş", [])
    except ValueError:
        pass
    else:
        raise AssertionError("renksiz tema kabul edilmemeli")
    app = ui.App(theme=t)  # Theme nesnesi: kaydedilir, adıyla da seçilir
    assert "deneme-dört" in THEMES and app.theme.name == "deneme-dört"
    assert ui.App(theme="deneme-dört").theme.accent == (255, 0, 0)
    ui.register_theme(ui.make_theme("adıyla", ["#123456"]))
    settings.check_names(theme="adıyla")
    del THEMES["deneme-dört"], THEMES["adıyla"]


class Renkli(ui.App):
    def compose(self):
        with ui.Row(gap=2):
            yield ui.Button("Birincil", lambda: None, variant="primary", id="b1")
            yield ui.Button("Yeşil", lambda: None, variant="primary", color="green", id="b2")
            yield ui.Button("Üçüncül", lambda: None, variant="primary", color=3, id="b3")
        yield ui.ProgressBar(id="bar")


def test_roles_and_per_element_color():
    async def main():
        app = Renkli()
        async with app.run_test() as pilot:
            th = app.theme
            app.query_one("#bar").progress = 1.0
            app.set_focus(None)
            app._render()
            surface = app.native.get_surface()
            fill = lambda w: colours(surface, app.query_one(w).region)  # noqa: E731
            assert any(near(c, th.accent) for c in fill("#b1"))
            assert any(near(c, th.green) for c in fill("#b2")) and not any(near(c, th.accent, 8) for c in fill("#b2"))
            assert any(near(c, th.accent3) for c in fill("#b3"))
            bar = app.query_one("#bar")
            left = surface.get_at((bar.content.x + 2, bar.content.centery))
            assert near(left, th.accent2, 24)  # ilerleme çubuğu varsayılan olarak ikincil renkten başlar
            assert app.color_spec(bar) == 2 and app.color_spec(app.query_one("#b2")) == "green"
            app.set_roles(ProgressBar=3, Button="magenta")  # türün rengi temadan bağımsız değişir
            await pilot.pause()
            assert near(surface.get_at((bar.content.x + 2, bar.content.centery)), th.accent3, 24)
            assert any(near(c, th.magenta) for c in fill("#b1"))
            assert any(near(c, th.green) for c in fill("#b2"))  # öge kendi rengini korur
            app.set_roles(ProgressBar=None, Button=None)  # varsayılana dön
            assert app.roles["ProgressBar"] == ui.ROLES["ProgressBar"]
            app.set_theme("lavanta")  # roller temadan bağımsız: yeni temanın üçüncülü
            await pilot.pause()
            assert any(near(c, THEMES["lavanta"].accent3) for c in fill("#b3"))
            assert not app._errors

        class Ozel(Renkli):
            ROLES = {"Button": 2}

        app = Ozel(roles={"ProgressBar": "yellow"})
        async with app.run_test() as pilot:
            assert app.color_spec(app.query_one("#b1")) == 2 and app.color_spec(app.query_one("#bar")) == "yellow"

        class Liste(ui.OptionList):  # alt sınıf üst sınıfın rolünü kullanır
            pass

        assert app.color_spec(Liste(["a"])) == ui.ROLES["OptionList"]
    run(main())


class Paneller(ui.App):
    def compose(self):
        with ui.Row(gap=2):
            with ui.Panel(title="Odakta", id="p1"):
                yield ui.Input(id="alan")
            with ui.Panel(title="Boşta", id="p2"):
                yield ui.Static("yazı")


def test_panel_frame_and_focus_styles():
    async def main():
        for frame in CHOICES["frame"]:
            for focus in CHOICES["focus"]:
                app = Paneller(frame=frame, focus=focus)
                async with app.run_test(size=(700, 220)) as pilot:
                    th = app.theme
                    app.query_one("#alan").focus()
                    app._render()
                    surface = app.native.get_surface()
                    busy, idle = app.query_one("#p1").frame, app.query_one("#p2").frame
                    side = lambda r: surface.get_at((r.x, r.centery))[:3]  # noqa: E731 (sol kenarın ortası)
                    lit = focus in ("color", "double")
                    if frame in ("line", "faint"):
                        resting = th.border if frame == "line" else mix(th.border, th.bg, 0.5)
                        assert near(side(idle), resting, 3), (frame, focus)
                        assert near(side(busy), th.accent if lit else resting, 3), (frame, focus)
                    else:  # köşeler ya da çizgisiz: kenarın ortasında çizgi yok
                        assert near(side(idle), th.bg, 3), (frame, focus)
                    title = app.query_one("#p1").frame
                    head = colours(surface, title.inflate(0, 0).clip((title.x, title.y - 8, title.w, 16)))
                    named = focus in ("color", "double", "title")
                    assert any(near(c, th.accent) for c in head) == (named or lit), (frame, focus)
                    if focus == "bar":
                        assert near(surface.get_at((busy.x + 3, busy.centery)), th.accent, 3)
                    assert not app._errors
    run(main())


def test_fullscreen_button_and_settings():
    async def main():
        class Tam(ui.App):
            def compose(self):
                yield ui.FullscreenButton(id="fs")

        app = Tam()
        async with app.run_test() as pilot:
            button = app.query_one("#fs", ui.FullscreenButton)
            assert button.label == "⛶ Tam ekran"
            await pilot.click(button)
            assert app.fullscreen and button.label == "⛶ Pencere"
            await pilot.press("f11")  # kısayolla değişince de yazı uyar
            assert not app.fullscreen and button.label == "⛶ Tam ekran"
    run(main())
    from test_settings import captured, preferences
    with preferences('accent3 = "#ff8800"\nframe = "corners"\nfocus = "bar"\nframe2 = 1\n'), captured() as (_, err):
        prefs = settings.preferences()
    assert prefs["tokens"] == {"accent3": (255, 136, 0), "frame": "corners", "focus": "bar"}
    assert "frame2" in err.getvalue()
    with preferences('frame = "kalın"\n'), captured() as (_, err):
        assert "frame" not in settings.preferences()["tokens"]
    assert "line, faint, corners, none" in err.getvalue()


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
