"""Grafik (veri katmanı, bileşen, akışta chart) ve durum kaydı (SAVE_STATE) testleri.

    python tests/test_chart_state.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

import _ortam  # noqa: E402,F401  (kullanıcının tercihlerinden yalıt)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import termik as ui  # noqa: E402
from termik.app import _on_screen  # noqa: E402
from termik.flow import window as flow_window  # noqa: E402
from termik.plot import ChartData, fmt, nice_ticks  # noqa: E402
from termik.theme import CHOICES  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from test_flow import Harness, run_terminal  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def near(a, b, tolerance: int = 40) -> bool:
    return max(abs(x - y) for x, y in zip(a[:3], b[:3])) <= tolerance


# ── veri katmanı ──────────────────────────────────────────

def test_ticks_and_turkish_numbers():
    assert nice_ticks(0, 97, 6) == [0, 20, 40, 60, 80, 100]
    assert nice_ticks(3, 14, 4) == [0, 5, 10, 15]
    assert nice_ticks(0.2, 0.9, 4) == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert nice_ticks(5, 5) == [4, 4.5, 5, 5.5, 6]  # tek değer: çevresinde bir aralık
    assert [fmt(v) for v in (12400, 3.0, 0.25, 56.43, 123.45, 1234.4, -7)] ==         ["12.400", "3", "0,25", "56,4", "123,5", "1.234", "-7"]


def test_chart_data_shapes_and_live_values():
    single = ChartData([1, 2, 3])
    assert [s.name for s in single.series] == ["değer"] and not single.named and single.count == 3
    multi = ChartData({"cpu": [1, 2], "bellek": [3]})
    assert [s.name for s in multi.series] == ["cpu", "bellek"] and multi.named and multi.count == 2
    bars = ChartData({"Ocak": 12, "Şubat": 30}, kind="bar")
    assert bars.x == ["Ocak", "Şubat"] and bars.series[0].values == [12, 30] and bars.value_range() == (0.0, 30.0)
    live = ChartData({"cpu": []}, max_points=3)
    for i in range(5):
        live.append("cpu", i * 10, label=f"{i}s")
    live.append("yeni", 7)  # olmayan seri açılır
    assert live.get("cpu").values == [20, 30, 40] and live.x == ["2s", "3s", "4s"] and live.get("yeni").values == [7]
    live.append(99)  # ilk seriye
    assert live.get("cpu").values == [30, 40, 99]
    assert ChartData([5, 6], y_min=0, y_max=10).value_range() == (0, 10)
    assert ChartData([1], y_format="{:.0f} %").format(42.4) == "42 %"
    live.clear()
    assert live.count == 0 and [s.name for s in live.series] == ["cpu", "yeni"]
    assert ChartData(kind="line").colors() == [] and ChartData({"a": [], "b": []}).colors() == ["accent", "accent2"]
    try:
        ChartData(kind="pasta")
    except ValueError:
        pass
    else:
        raise AssertionError("bilinmeyen tür kabul edilmemeli")


def test_chart_text_for_terminal():
    lines = ChartData({"cpu": [0, 50, 100]}, title="CPU").text_lines(width=12, height=4)
    assert lines[0] == "[bold]CPU[/]" and "100" in lines[1] and "█" in lines[1] and "━[/] cpu" in lines[-1]
    bars = ChartData({"Ocak": 10, "Şubat": 20}, kind="bar").text_lines(width=40)
    assert bars[0].startswith("Ocak") and bars[1].count("█") > bars[0].count("█")
    assert ChartData().text_lines() == ["[faint](veri yok)[/]"]


# ── bileşen ───────────────────────────────────────────────

class ChartApp(ui.App):
    def compose(self):
        yield ui.Chart({"cpu": [0, 100, 0, 100], "bellek": [50, 50, 50, 50]}, title="Kullanım", y_min=0,
                       y_max=100, id="line", height=12)
        yield ui.Chart({"Ocak": 12, "Şubat": 30}, kind="bar", id="bar", height=10)
        yield ui.Chart(id="empty", height=6)


def test_chart_renders_hover_and_live():
    async def main():
        app = ChartApp()
        async with app.run_test() as pilot:
            th = app.theme
            line = app.query_one("#line", ui.Chart)
            plot = line._plot
            surface = app.native.get_surface()
            # bellek serisi 50'de yatay çizgi: ortadaki satır ikinci rengin (accent2)
            mid = round(line._y(50, plot, 0, 100))
            assert any(near(surface.get_at((plot.centerx + d, mid)), th.accent2) for d in range(-3, 4))
            bar = app.query_one("#bar", ui.Chart)
            bx = bar._xs(bar._plot, 2)[1]
            assert near(surface.get_at((round(bx), bar._plot.bottom - 4)), th.accent)  # Şubat çubuğu
            await pilot.hover(line, offset=(plot.x + plot.w // 3 - line.region.x, plot.centery - line.region.y))
            assert line._hover_index(line._xs(plot, 4)) == 1  # en yakın nokta
            for kind in ("line", "area", "bar"):
                for style in CHOICES["chart"]:
                    line.kind = kind
                    app.set_theme(chart=style)
                    await pilot.pause()
            app._dirty = False
            line.append("cpu", 30)
            assert app._dirty and line.data.count == 5
            empty = app.query_one("#empty", ui.Chart)
            empty.append(3)
            await pilot.pause()
            assert empty.series[0].values == [3] and not app._errors
    run(main())


def test_flow_chart_window_and_terminal():
    def script(s):
        cpu = s.chart({"cpu": []}, title="CPU", max_points=3)
        for v in (10, 20, 30, 40):
            cpu.append("cpu", v)
        return cpu.data.get("cpu").values

    with Harness(script) as h:
        assert h.finish() == [20, 30, 40]
        entries = [e for e in h.app.transcript.children if isinstance(e, flow_window.ShownEntry)]
        assert isinstance(entries[0].widget, ui.Chart) and "CPU" in entries[0].plain()
    result, out, error = run_terminal(lambda s: s.chart({"Ocak": 3, "Şubat": 6}, kind="bar") and None)
    assert error is None and "Ocak" in out and "█" in out


# ── durum kaydı ───────────────────────────────────────────

class Remembering(ui.App):
    SAVE_STATE = True
    STATE_NAME = "termik-test-durum"
    kaynak = ui.reactive("C:/varsayılan")

    def compose(self):
        with ui.Split(sizes=[20, "1fr"], id="kolonlar", height=8):
            with ui.Form():
                yield ui.Input(label="Kaynak", bind="kaynak")
                yield ui.Spinbox(3, min=1, max=9, label="Sakla", bind="sakla")
                yield ui.Input(label="Parola", password=True, bind="parola")
                yield ui.Input(label="Geçici", bind="gecici", persist=False)
            with ui.Tabs(id="sekmeler"):
                with ui.Tab("Bir"):
                    yield ui.Static("1")
                with ui.Tab("İki"):
                    yield ui.Static("2")


def test_save_state_roundtrip():
    async def main():
        first = Remembering()
        first.forget_state()
        async with first.run_test() as pilot:
            assert not first.save_state  # run_test altında SAVE_STATE kendiliğinden kapalı
        assert not first.state_path.exists()
        app = Remembering(save_state=True)  # açıkça istenince testte de çalışır
        async with app.run_test() as pilot:
            app.kaynak, app.sakla, app.parola, app.gecici = "D:/yedek", 7, "gizli", "x"
            app.query_one("#kolonlar", ui.Split).set_fractions([1, 1])
            app.query_one("#sekmeler", ui.Tabs).active = 1
            await pilot.pause()
        state = json.loads(app.state_path.read_text(encoding="utf-8"))
        assert state["değerler"] == {"kaynak": "D:/yedek", "sakla": 7}  # parola ve persist=False yok
        assert state["sekme"] == {"sekmeler": 1} and abs(state["split"]["kolonlar"][0] - 0.5) < 0.01
        assert "pencere" not in state  # sahte sürücüde pencere yeri saklanmaz
        again = Remembering(save_state=True)
        async with again.run_test() as pilot:
            assert again.kaynak == "D:/yedek" and again.sakla == 7
            assert again.query_one(ui.Input).value == "D:/yedek" and again.query_one(ui.Spinbox).value == 7
            assert again.query_one("#sekmeler", ui.Tabs).active == 1
            split = again.query_one("#kolonlar", ui.Split)
            assert abs(split.fractions[0] - 0.5) < 0.02
            again.forget_state()
            again.save_state = False
        assert not again.state_path.exists()
    run(main())


def test_state_file_names_and_bad_input():
    app = ui.App(title="Benim Aracım")
    assert app.state_path.name == "benim-aracım.json" and app.state_path.parent.name == "durum"
    assert Remembering().state_path.name == "termik-test-durum.json"
    path = Remembering().state_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bozuk", encoding="utf-8")
    try:
        assert Remembering()._read_state() == {}
    finally:
        path.unlink()
    assert _on_screen([100, 100, 800, 600]) == (100, 100, 800, 600)
    assert _on_screen([-50000, -50000, 800, 600]) is None  # monitör çıkarılmış: yok say
    assert _on_screen("bozuk") is None and _on_screen([1, 2, 0, 4]) is None


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)
             and fn.__module__ == __name__]
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
