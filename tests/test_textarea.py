"""Çok satırlı yazı alanı (TextArea) testleri; pencere açmadan Pilot ile sürülür.

    python tests/test_textarea.py
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


def run(coro):
    return asyncio.run(coro)


def make_app(**kwargs) -> ui.App:
    class Editor(ui.App):
        def __init__(self) -> None:
            super().__init__()
            self.changes: list[str] = []
            self.submitted: list[str] = []

        def compose(self):
            yield ui.TextArea(id="ta", **kwargs)
            yield ui.Button("Sonraki", id="next")

        def on_text_area_changed(self, event: ui.TextArea.Changed) -> None:
            self.changes.append(event.text)

        def on_text_area_submitted(self, event: ui.TextArea.Submitted) -> None:
            self.submitted.append(event.text)

    return Editor()


def at(app, ta: ui.TextArea, row: int, col: int) -> tuple[int, int]:
    """(satır, sütun)un ekrandaki yeri (kaydırma yokken, eş genişlikli yazıda)."""
    p = app.painter
    return ta._geom[0] + col * p.ch + 1, ta.content.y + row * p.row + p.row // 2


def test_typing_newlines_and_indent():
    async def main():
        app = make_app()
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            assert app.focused is ta
            await pilot.type("merhaba")
            await pilot.press("enter")
            await pilot.type("  girinti")
            await pilot.press("enter")  # satırın girintisi korunur
            await pilot.type("devam")
            assert ta.text == "merhaba\n  girinti\n  devam"
            assert ta.cursor_location == (2, 7) and app.changes[-1] == ta.text
    run(main())


def test_navigation_keeps_column():
    async def main():
        app = make_app()
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            ta.text = "birinci satır\nikinci\nüçüncü satır uzun"
            await pilot.press("ctrl+home", "end")
            assert ta.cursor_location == (0, 13)
            await pilot.press("down")
            assert ta.cursor_location == (1, 6)  # kısa satırda sona
            await pilot.press("down")
            assert ta.cursor_location == (2, 13)  # hedef sütun korundu
            await pilot.press("home", "left")
            assert ta.cursor_location == (1, 6)
            await pilot.press("right", "ctrl+right")
            assert ta.cursor_location == (2, 6)
            await pilot.press("ctrl+end")
            assert ta.cursor_location == ta.end
    run(main())


def test_selection_replace_and_select_all():
    async def main():
        app = make_app()
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            ta.text = "abc\ndef\nghi"
            await pilot.press("ctrl+home", "shift+down", "shift+right")
            assert ta.selected_text == "abc\nd"
            await pilot.type("X")
            assert ta.text == "Xef\nghi"
            await pilot.press("ctrl+a")
            assert ta.selected_text == "Xef\nghi"
            await pilot.press("delete")
            assert ta.text == ""
    run(main())


def test_join_lines_and_word_delete():
    async def main():
        app = make_app()
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            ta.text = "bir\niki üç"
            await pilot.press("ctrl+home", "down", "home", "backspace")
            assert ta.text == "biriki üç" and ta.cursor_location == (0, 3)
            await pilot.press("end", "ctrl+backspace")
            assert ta.text == "biriki "
            await pilot.press("ctrl+home", "delete")
            assert ta.text == "iriki "
    run(main())


def test_undo_redo():
    async def main():
        app = make_app()
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            await pilot.type("abc")  # arka arkaya harfler tek geri alma adımı
            await pilot.press("enter")
            await pilot.type("def")
            assert ta.text == "abc\ndef"
            await pilot.press("ctrl+z")
            assert ta.text == "abc\n"
            await pilot.press("ctrl+z", "ctrl+z")
            assert ta.text == ""
            await pilot.press("ctrl+y")
            assert ta.text == "abc"
            await pilot.press("ctrl+y", "ctrl+y")
            assert ta.text == "abc\ndef"
    run(main())


def test_clipboard_roundtrip():
    async def main():
        app = make_app()
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            ta.text = "satır 1\nsatır 2"
            await pilot.press("ctrl+a", "ctrl+c", "ctrl+end", "enter", "ctrl+v")
            assert ta.text == "satır 1\nsatır 2\nsatır 1\nsatır 2"
            await pilot.press("ctrl+a", "ctrl+x")
            assert ta.text == ""
    run(main())


def test_wrap_and_vertical_motion():
    async def main():
        app = make_app(width=24)
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            ta.text = "bir iki üç dört beş altı yedi sekiz dokuz on"
            await pilot.pause()
            segs, _ = ta._segments(app.painter, ta._geom[1])
            assert len(segs) > 1 and all(r == 0 for r, _, _ in segs)
            assert "".join(ta.lines[0][s:e] for _, s, e in segs) == ta.lines[0]
            assert all(ta.lines[0][e - 1] == " " for _, _, e in segs[:-1])  # kelime ortasından bölmez
            await pilot.press("ctrl+home", "down")  # aynı mantıksal satırın ikinci görsel satırı
            assert ta.cursor_location == (0, segs[1][1])
    run(main())


def test_tab_behaviors():
    async def main():
        app = make_app()
        async with app.run_test() as pilot:
            await pilot.press("tab")  # varsayılan: odak sonraki bileşene geçer
            assert app.focused.id == "next"
        app = make_app(tab_behavior="indent")
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            await pilot.type("a")
            await pilot.press("home", "tab")
            assert ta.text == "    a" and app.focused is ta
            await pilot.press("shift+tab")
            assert ta.text == "a"
    run(main())


def test_auto_grow():
    async def main():
        app = make_app(rows=1, max_rows=3)
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            row = app.painter.row
            assert ta.region.h == row
            await pilot.type("a")
            await pilot.press("enter")
            await pilot.type("b")
            assert ta.region.h == 2 * row
            for _ in range(3):
                await pilot.press("enter")
                await pilot.type("x")
            assert ta.region.h == 3 * row
    run(main())


def test_submit_key():
    async def main():
        app = make_app(submit_key="enter")
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            await pilot.type("selam")
            await pilot.press("enter")
            assert app.submitted == ["selam"] and ta.text == "selam"
            await pilot.press("shift+enter")  # gönderme tuşu Enter iken yeni satır shift+enter
            assert ta.text == "selam\n"
    run(main())


def test_mouse_click_drag_and_double_click():
    async def main():
        app = make_app()
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            ta.text = "merhaba dünya\nikinci satır"
            await pilot.pause()
            await pilot.click(ta, offset=tuple(v - o for v, o in zip(at(app, ta, 1, 3), ta.region.topleft)))
            assert ta.cursor_location == (1, 3)
            start, end = at(app, ta, 0, 0), at(app, ta, 1, 6)
            app._mouse_move(start, False)
            app._mouse_down(start, 1)
            app._mouse_move(end, True)
            app._mouse_up(end, 1)
            await pilot.pause(0.5)
            assert ta.selected_text == "merhaba dünya\nikinci"
            word = tuple(v - o for v, o in zip(at(app, ta, 0, 10), ta.region.topleft))
            await pilot.click(ta, offset=word)
            await pilot.click(ta, offset=word)  # çift tık kelimeyi seçer
            assert ta.selected_text == "dünya"
    run(main())


def test_read_only_and_line_numbers():
    async def main():
        app = make_app(text="\n".join(f"satır {i}" for i in range(30)), read_only=True, line_numbers=True, rows=5)
        async with app.run_test() as pilot:
            ta = app.query_one("#ta", ui.TextArea)
            before = ta.text
            await pilot.type("x")
            await pilot.press("backspace", "ctrl+z")
            assert ta.text == before
            await pilot.press("ctrl+end")
            assert ta._top == 30 - 5  # imleç görünür alanda
            await pilot.press("ctrl+a", "ctrl+c")
            assert ui.clipboard.get_text() == before  # salt okunurda kopyalama serbest
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
