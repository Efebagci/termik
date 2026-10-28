"""Bileşen çekirdeği testleri: pencere açmadan (SDL'in sahte sürücüsüyle) Pilot ile sürülür.

    python tests/test_core.py       # pytest gerekmez
    python -m pytest tests          # pytest kuruluysa
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

import _ortam  # noqa: E402,F401  (kullanıcının tercihlerinden yalıt)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import termik as ui  # noqa: E402
from termik import keys  # noqa: E402
from termik.layout import distribute, parse_size  # noqa: E402

import pygame  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class Form(ui.App):
    """Testlerin çoğunun kullandığı küçük uygulama."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.calls: list[str] = []

    def compose(self):
        with ui.Row(id="row"):
            yield ui.Static("sol", id="left", width=20)
            yield ui.Static("orta", id="mid")
            yield ui.Static("sağ", id="right", width="25%")
        yield ui.Input(label="Ad", id="name")
        with ui.Row(gap=2, id="buttons"):
            yield ui.Checkbox("Onay", id="chk")
            yield ui.RadioSet("Bir", "İki", "Üç", id="radio")
            yield ui.Spacer()
            yield ui.Button("Tamam", action="confirm", variant="primary", id="ok")
        yield ui.Panel(ui.Log(id="log"), title="Günlük", id="panel")
        yield ui.KeyBar(id="keys")

    @ui.action("Onayla", key="f5", hint="onayla")
    def confirm(self) -> None:
        self.calls.append("confirm")

    @ui.action("Q eylemi", key="q", show=False)
    def q_action(self) -> None:
        self.calls.append("q")

    def on_button_pressed(self, event: ui.Button.Pressed) -> None:
        self.calls.append(f"pressed:{event.button.id}")

    def on_input_submitted(self, event: ui.Input.Submitted) -> None:
        self.calls.append(f"submit:{event.value}")


# ── saf fonksiyonlar ──────────────────────────────────────

def test_sizes_and_distribute():
    assert parse_size(30).kind == "cells" and parse_size(30).value == 30
    assert parse_size("40%").kind == "percent"
    assert parse_size("2fr").value == 2 and parse_size("fr").value == 1
    assert parse_size("auto").kind == "auto" and parse_size("12px").kind == "px"
    specs = [parse_size(s) for s in (10, "1fr", "2fr", "auto")]
    sizes = distribute(specs, [0, 0, 0, 50], 1000, 9)
    assert sizes[0] == 90 and sizes[3] == 50
    assert sizes[1] + sizes[2] == 1000 - 140 and abs(sizes[2] - 2 * sizes[1]) <= 1


def test_key_names():
    pygame.init()
    try:
        assert keys.normalize("Ctrl+Shift+Z") == "ctrl+shift+z"
        assert keys.normalize("Esc") == "escape" and keys.normalize("shift+ctrl+a") == "ctrl+shift+a"
        assert keys.display("enter") == "⏎" and keys.display("ctrl+escape") == "ctrl+esc"
        ev = types.SimpleNamespace
        assert keys.from_event(ev(key=pygame.K_q, mod=pygame.KMOD_LCTRL | pygame.KMOD_RALT)) == "altgr+q"
        assert keys.from_event(ev(key=pygame.K_TAB, mod=pygame.KMOD_LSHIFT)) == "shift+tab"
        assert keys.from_event(ev(key=pygame.K_a, mod=pygame.KMOD_LSHIFT)) == "a"
        assert keys.from_event(ev(key=pygame.K_s, mod=pygame.KMOD_LCTRL)) == "ctrl+s"
    finally:
        pygame.quit()


def test_wrap_and_escape():
    async def main():
        app = ui.App()
        async with app.run_test():
            t = app.painter.text
            lines = t.wrap("bir iki üç dört beş", t.ch * 9)
            assert ["".join(s for s, _ in line) for line in lines] == ["bir iki", "üç dört", "beş"]
            assert len(t.wrap("a\nb", 1000)) == 2
            assert len(t.wrap("x" * 30, t.ch * 10)) == 3  # tek başına sığmayan kelime bölünür
            assert ui.escape("[bold]") == "\\[bold]"
            assert "".join(s for s, _ in t.spans(ui.escape("[bold]yazı[/]"))) == "[bold]yazı[/]"
    run(main())


# ── ağaç ve yerleşim ──────────────────────────────────────

def test_compose_tree():
    async def main():
        app = Form()
        async with app.run_test():
            screen = app.screen
            assert [type(c).__name__ for c in screen.children] == ["Row", "Input", "Row", "Panel", "KeyBar"]
            assert [c.id for c in app.query_one("#row").children] == ["left", "mid", "right"]
            assert isinstance(app.query_one("#panel").children[0], ui.Log)
            assert len(app.query(ui.Static)) == 3 and app.query_one("Log").id == "log"
    run(main())


def test_layout():
    async def main():
        app = Form()
        async with app.run_test(size=(1000, 600)):
            p = app.painter
            row = app.query_one("#row")
            left, mid, right = (app.query_one(s) for s in ("#left", "#mid", "#right"))
            assert left.region.w == 20 * p.ch
            assert right.region.w == round(row.content.w * 0.25)
            assert left.region.w + mid.region.w + right.region.w == row.content.w
            assert row.region.h == p.row  # içeriği kadar
            ok, chk = app.query_one("#ok"), app.query_one("#chk")
            assert ok.region.right == app.query_one("#buttons").content.right  # Spacer sağa iter
            assert chk.region.x == app.query_one("#buttons").content.x
            panel, bar = app.query_one("#panel"), app.query_one("#keys")
            assert panel.region.h > 5 * p.row  # içinde Log var: kalan yeri doldurur
            assert bar.region.top >= panel.region.bottom
            assert bar.region.bottom <= app.screen.content.bottom
    run(main())


def test_runtime_mount_and_remove():
    async def main():
        app = Form()
        async with app.run_test() as pilot:
            panel = app.query_one("#panel")
            panel.mount(ui.Button("Yeni", id="new"), before=0)
            await pilot.pause()
            new = app.query_one("#new")
            assert new.is_mounted and new.region.w > 0 and new in app.focus_chain()
            new.focus()
            new.remove()
            await pilot.pause()
            assert not new.is_mounted and app.focused is not None and app.focused is not new
            assert not app.query("#new")
    run(main())


# ── odak ve klavye ────────────────────────────────────────

def test_focus_order():
    async def main():
        app = Form()
        async with app.run_test() as pilot:
            assert app.focused.id == "name"
            order = []
            for _ in range(5):
                await pilot.press("tab")
                order.append(app.focused.id)
            assert order == ["chk", "radio", "ok", "log", "name"]
            await pilot.press("shift+tab")
            assert app.focused.id == "log"
            assert app.query_one("#panel").focus_within
    run(main())


def test_typing_does_not_trigger_shortcuts():
    async def main():
        app = Form()
        async with app.run_test() as pilot:
            await pilot.type("q q")
            assert app.query_one("#name").value == "q q"
            assert "q" not in app.calls
            await pilot.press("f5")  # yazmayan tuş: odak Input'tayken de çalışır
            assert app.calls == ["confirm"]
            app.query_one("#ok").focus()
            await pilot.press("q")
            assert app.calls[-1] == "q"
    run(main())


def test_input_editing():
    async def main():
        app = Form()
        async with app.run_test() as pilot:
            field = app.query_one("#name", ui.Input)
            await pilot.type("merhaba dünya")
            await pilot.press("ctrl+backspace")
            assert field.value == "merhaba "
            await pilot.type("termik")
            await pilot.press("home", *["shift+right"] * 7)
            assert field.selected_text == "merhaba"
            await pilot.type("selam")
            assert field.value == "selam termik" and field.cursor_position == 5
            await pilot.press("ctrl+right", "ctrl+left", "end")
            assert field.cursor_position == len(field.value)
            await pilot.press("enter")
            assert app.calls == ["submit:selam termik"]
            await pilot.press("ctrl+a", "backspace")
            assert field.value == ""
    run(main())


# ── fare ve bileşenler ────────────────────────────────────

def test_checkbox_radio_button():
    async def main():
        app = Form()
        async with app.run_test() as pilot:
            chk = app.query_one("#chk", ui.Checkbox)
            await pilot.click(chk)
            assert chk.value is True and app.focused is chk
            await pilot.press("space")
            assert chk.value is False
            radio = app.query_one("#radio", ui.RadioSet)
            second = radio._rects[1]
            await pilot.click(radio, offset=(second.centerx - radio.region.x, second.centery - radio.region.y))
            assert radio.index == 1 and radio.value == "İki"
            await pilot.press("right")
            assert radio.index == 2
            await pilot.click("#ok")
            assert app.calls == ["pressed:ok", "confirm"]
            await pilot.press("enter")  # odaktaki butona Enter
            assert app.calls[-1] == "confirm"
    run(main())


def test_disabled_button():
    async def main():
        app = Form()
        async with app.run_test() as pilot:
            ok = app.query_one("#ok")
            ok.disabled = True
            await pilot.pause()
            assert ok not in app.focus_chain()
            await pilot.click(ok)
            assert app.calls == []
    run(main())


def test_keybar_lists_and_clicks():
    async def main():
        app = Form()
        async with app.run_test() as pilot:
            shown = [(key, hint) for key, hint, _, _ in app.active_bindings()]
            assert shown == [("f5", "onayla"), ("tab", "sonraki"), ("ctrl+p", "komutlar"), ("ctrl+q", "çık")]
            bar = app.query_one("#keys", ui.KeyBar)
            first = bar._items[0][0]
            await pilot.click(bar, offset=(first.centerx - bar.region.x, first.centery - bar.region.y))
            assert app.calls == ["confirm"]
    run(main())


def test_log_scroll_and_follow():
    async def main():
        app = Form()
        async with app.run_test() as pilot:
            log = app.query_one("#log", ui.Log)
            for i in range(60):
                log.write(f"satır {i}")
            await pilot.pause()
            assert log._back == 0 and log._visible < 60
            await pilot.scroll(log, 1)
            assert log._back == 3
            log.write("yeni")  # yukarıdayken görünüm yerinde kalır
            assert log._back == 4
            log.focus()
            await pilot.press("end")
            assert log._back == 0
            await pilot.press("pageup")
            assert log._back == log._visible - 1
    run(main())


# ── reaktif, async, işçiler, bildirimler ──────────────────

class Counter(ui.Static):
    count = ui.reactive(0)

    def __init__(self, **kwargs) -> None:
        super().__init__("0", **kwargs)
        self.seen: list[tuple[int, int]] = []

    def watch_count(self, old: int, new: int) -> None:
        self.seen.append((old, new))
        self.update(str(new))


def test_reactive_watch():
    async def main():
        class CounterApp(ui.App):
            def compose(self):
                yield Counter(id="c")

        app = CounterApp()
        async with app.run_test() as pilot:
            counter = app.query_one("#c", Counter)
            app._dirty = False
            counter.count = 3
            counter.count = 3  # aynı değer: izleyici çağrılmaz
            assert counter.seen == [(0, 3)] and counter.text == "3" and app._dirty
            await pilot.pause()
            assert not app._dirty
    run(main())


def test_async_action_and_thread_worker():
    async def main():
        def slow(n: int) -> int:  # bloklayan iş: thread'de koşar
            time.sleep(0.3)
            return n * 2

        class WorkerApp(ui.App):
            result = None

            def compose(self):
                yield ui.Static("hazır", id="s")

            @ui.action("Çalıştır", key="f5")
            async def go(self) -> None:
                self.result = await self.run_worker(slow, 21)

        app = WorkerApp()
        async with app.run_test() as pilot:
            await pilot.press("f5")
            ticks = 0
            while app.result is None:  # iş sürerken döngü dönmeye devam etmeli
                app._tick()
                ticks += 1
                await asyncio.sleep(0.01)
            assert app.result == 42 and ticks > 5 and not app._errors
    run(main())


def test_notify_and_error_report():
    async def main():
        class Broken(ui.App):
            def compose(self):
                yield ui.Button("Boz", on_press=lambda: 1 / 0, id="b")

        app = Broken()
        async with app.run_test() as pilot:
            app.notify("merhaba", timeout=0.1)
            assert len(app._toasts) == 1
            await pilot.pause(0.25)
            assert app._toasts == []
            await pilot.click("#b")  # hata uygulamayı düşürmez, bildirim olur
            assert isinstance(app._errors[0], ZeroDivisionError) and app._toasts[0][1] == "err"
    run(main())


def test_every_theme_and_density_renders():
    async def main():
        app = Form()
        async with app.run_test() as pilot:
            for name in ui.THEMES:
                for density in ui.DENSITIES:
                    app.set_theme(name, density=density)
                    await pilot.pause()
            app.set_theme("okyanus", density="rahat", title="inline", bar="segment", button="angle")
            await pilot.pause()
            assert not app._errors
    run(main())


def test_demo_app():
    from termik.demo import uygulama as demo

    async def main():
        app = demo.BackupApp(ROOT)
        async with app.run_test(size=(1200, 760)) as pilot:
            await pilot.press("f5")
            await pilot.wait_until(lambda: app.query_one("#bar").progress >= 1 and not app.running, timeout=15)
            assert app.query_one("#statusbar").mode == "HAZIR"
            assert any(kind == "ok" for _, kind in app._toasts)
            assert any("tamamlandı" in line for line in app.log.lines)
            history = app.query_one("#history", ui.Table)
            assert history.row_count == len(demo.HISTORY) + 1 and "✓" in history.rows[0][0][0]
            await pilot.press("f5")
            await pilot.pause(0.2)
            await pilot.press("escape")  # onay diyaloğu açılır
            assert isinstance(app.screen, ui.Dialog) and app.running
            await pilot.press("enter")  # "İptal et"
            await pilot.wait_until(lambda: not app.running)
            assert any("iptal" in line for line in app.log.lines)
            pilot.snapshot(str(Path(tempfile.gettempdir()) / "termik-demo.png"))
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
