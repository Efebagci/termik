"""Komut paleti, ağaç, tablo ve mini grafik testleri; pencere açmadan Pilot ile sürülür.

    python tests/test_widgets.py    # pytest gerekmez
    python -m pytest tests          # pytest kuruluysa
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

import termik as ui  # noqa: E402


def run(coro):
    return asyncio.run(coro)


# ── komut paleti ──────────────────────────────────────────

class Commands(ui.App):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.calls: list[str] = []

    def compose(self):
        yield ui.Input(id="name")
        yield ui.Button("Tamam", id="ok")
        yield ui.KeyBar()

    @ui.action("Yedeklemeyi başlat", key="f5")
    def start(self) -> None:
        self.calls.append("start")

    @ui.action("Günlüğü temizle")
    def clear_log(self) -> None:
        self.calls.append("clear")

    @ui.action("Gizli iş", palette=False)
    def hidden(self) -> None:
        self.calls.append("hidden")


def test_palette_lists_and_runs():
    async def main():
        app = Commands()
        async with app.run_test() as pilot:
            await pilot.press("ctrl+p")
            palette = app.screen
            assert isinstance(palette, ui.CommandPalette)
            labels = [command.label for command, _ in palette.matches]
            assert labels[:2] == ["Yedeklemeyi başlat", "Günlüğü temizle"]
            assert "Gizli iş" not in labels and "Komut paleti" not in labels
            assert "Çık" in labels and "Tema: neon" in labels and "Yoğunluk: ferah" in labels
            assert app.focused.id == "palette-query"
            await pilot.type("baslat")  # Türkçe gevşek eşleşme: "baslat" → "başlat"
            assert palette.matches[0][0].label == "Yedeklemeyi başlat"
            await pilot.press("enter")
            assert app.calls == ["start"]
            assert not isinstance(app.screen, ui.CommandPalette) and app.focused.id == "name"
    run(main())


def test_palette_navigation_and_close():
    async def main():
        app = Commands()
        async with app.run_test() as pilot:
            await pilot.press("ctrl+p", "down", "down", "up")
            assert app.screen.index == 1
            await pilot.press("escape")
            assert not isinstance(app.screen, ui.CommandPalette)
            await pilot.press("ctrl+p", "ctrl+p")  # aç-kapa
            assert not isinstance(app.screen, ui.CommandPalette)
            await pilot.press("ctrl+p")
            await pilot.click(app.screen, offset=(5, 5))  # kutunun dışına tıklamak kapatır
            assert not isinstance(app.screen, ui.CommandPalette)
            await pilot.press("ctrl+p")
            await pilot.type("xyzw")
            assert app.screen.matches == []
            await pilot.press("enter")  # eşleşme yokken hiçbir şey olmaz
            assert isinstance(app.screen, ui.CommandPalette) and app.calls == []
            assert not app._errors
    run(main())


def test_palette_theme_command_by_mouse():
    async def main():
        app = Commands()
        async with app.run_test() as pilot:
            await pilot.press("ctrl+p")
            await pilot.type("neon")
            assert app.screen.matches[0][0].label == "Tema: neon"
            p = app.painter
            await pilot.click(app.screen.results, offset=(p.ch * 4, p.row // 2 + p.row // 2))
            assert app.theme.name == "neon" and not isinstance(app.screen, ui.CommandPalette)
    run(main())


# ── ağaç ──────────────────────────────────────────────────

class LazyTree(ui.Tree):
    def load_children(self, node: ui.TreeNode) -> None:
        node.add_leaf("2026")
        node.add_leaf("2025")
        self.app.loaded.append(node.label)


class TreeApp(ui.App):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.selected: list[str] = []
        self.loaded: list[str] = []

    def compose(self):
        tree = LazyTree("Belgeler", id="tree")
        projeler = tree.root.add("projeler", expand=True)
        projeler.add_leaf("termik")
        projeler.add_leaf("audn-cli")
        tree.root.add("fotoğraflar", allow_expand=True)  # çocukları ilk açılışta yüklenir
        tree.root.add_leaf("notlar.txt", suffix="3 KB")
        yield tree

    def on_tree_node_selected(self, event: ui.Tree.NodeSelected) -> None:
        self.selected.append(event.node.label)


def labels(tree: ui.Tree) -> list[str]:
    return [ui.plain_text(node.label) for node in tree.lines]


def test_tree_keyboard():
    async def main():
        app = TreeApp()
        async with app.run_test() as pilot:
            tree = app.query_one("#tree", ui.Tree)
            assert labels(tree) == ["Belgeler", "projeler", "termik", "audn-cli", "fotoğraflar", "notlar.txt"]
            assert app.focused is tree
            await pilot.press("down", "left")  # projeler'i kapat
            assert labels(tree) == ["Belgeler", "projeler", "fotoğraflar", "notlar.txt"]
            await pilot.press("down", "right")  # fotoğraflar: tembel yükle ve aç
            assert app.loaded == ["fotoğraflar"]
            assert labels(tree)[-3:] == ["2026", "2025", "notlar.txt"]
            await pilot.press("right")  # ilk çocuğa in
            assert tree.cursor_node.label == "2026"
            await pilot.press("left")  # üste çık
            assert tree.cursor_node.label == "fotoğraflar"
            await pilot.press("left", "right", "left")  # kapat, aç (yeniden yüklemez), kapat
            assert app.loaded == ["fotoğraflar"]
            await pilot.press("end", "enter")
            assert app.selected == ["notlar.txt"]
    run(main())


def test_tree_collapse_moves_cursor_up():
    async def main():
        app = TreeApp()
        async with app.run_test() as pilot:
            tree = app.query_one("#tree", ui.Tree)
            await pilot.press("down", "down")  # termik
            tree.root.children[0].collapse()  # projeler kapanınca imleç projeler'e çıkar
            assert tree.cursor_node.label == "projeler"
    run(main())


def test_tree_mouse():
    async def main():
        app = TreeApp()
        async with app.run_test() as pilot:
            tree = app.query_one("#tree", ui.Tree)
            p = app.painter
            lead, indent, _ = tree._geometry
            arrow = (tree.content.x + lead + indent + p.ch // 2 - tree.region.x, p.row + p.row // 2)
            await pilot.click(tree, offset=arrow)  # projeler'in okuna tık: kapat
            assert not tree.root.children[0].expanded
            await pilot.pause(0.5)
            row = (p.ch * 12, p.row * 3 + p.row // 2)  # notlar.txt
            await pilot.click(tree, offset=row)
            await pilot.click(tree, offset=row)  # çift tık seçer
            assert app.selected == ["notlar.txt"] and not app._errors
    run(main())


def test_directory_tree():
    async def main():
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "b_klasör" / "iç").mkdir(parents=True)
            (base / "__pycache__").mkdir()
            (base / "a.txt").write_text("x" * 2048)
            (base / ".gizli").write_text("")
            (base / "b_klasör" / "c.md").write_text("")

            class DirApp(ui.App):
                def compose(self):
                    yield ui.DirectoryTree(tmp, id="tree")

            app = DirApp()
            async with app.run_test() as pilot:
                tree = app.query_one("#tree", ui.DirectoryTree)
                assert labels(tree)[1:] == ["b_klasör", "a.txt"]  # klasör önce; gizli ve önbellek yok
                assert tree.lines[2].suffix == "2.0 KB" and tree.lines[2].data == str(base / "a.txt")
                tree.select(tree.lines[1])
                await pilot.press("right")
                assert labels(tree)[2:4] == ["iç", "c.md"]
    run(main())


# ── tablo ─────────────────────────────────────────────────

class TableApp(ui.App):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.selected: list = []

    def compose(self):
        table = ui.Table(("Ad", 10), ("Boyut", None, "right"), ("Not", "1fr"), id="table")
        for name, size in (("b", "10"), ("a", "9"), ("c", "100")):
            table.add_row(name, size, f"[dim]{name}-not[/]", key=name)
        yield table

    def on_table_row_selected(self, event: ui.Table.RowSelected) -> None:
        self.selected.append(event.key)


def test_table_cursor_sort_select():
    async def main():
        app = TableApp()
        async with app.run_test() as pilot:
            table = app.query_one("#table", ui.Table)
            p = app.painter
            assert app.focused is table and table.cursor_key == "b"
            await pilot.press("down", "enter")
            assert app.selected == ["a"]
            x, w = table._edges[1]
            assert table._edges[0][1] == 10 * p.ch and w >= p.text.width("100")
            header = (x + w // 2 - table.region.x, p.row // 2)
            await pilot.click(table, offset=header)  # Boyut'a göre: 9 < 10 < 100 (doğal sıra)
            assert [key for _, key in table.rows] == ["a", "b", "c"] and table.sorted_by == (1, False)
            assert table.cursor_key == "a"  # imleç aynı satırda kaldı
            await pilot.pause(0.5)
            await pilot.click(table, offset=header)  # tersine
            assert [key for _, key in table.rows] == ["c", "b", "a"]
            await pilot.pause(0.5)
            third = (p.ch * 3, table._header_h(p) + p.row * 2 + p.row // 2)
            await pilot.click(table, offset=third)
            await pilot.click(table, offset=third)  # çift tık seçer
            assert table.cursor_row == 2 and app.selected[-1] == "a"
            table.add_row("d", "5", "", key="d")  # sıralı tabloya eklenen satır yerine oturur
            assert [key for _, key in table.rows] == ["c", "b", "a", "d"]
    run(main())


def test_table_scroll_and_placeholder():
    async def main():
        class Big(ui.App):
            def compose(self):
                table = ui.Table("No", "Ad", id="t")
                for i in range(200):
                    table.add_row(str(i), f"satır {i}")
                yield table
                yield ui.Table("Boş", id="empty", height=5)

        app = Big()
        async with app.run_test(size=(800, 500)) as pilot:
            table = app.query_one("#t", ui.Table)
            await pilot.press("pagedown")
            assert table.cursor_row == table._visible - 1
            await pilot.press("end")
            assert table.cursor_row == 199 and table._top == 200 - table._visible
            await pilot.scroll(table, 2)  # tekerlek yukarı
            assert table._top == 200 - table._visible - 6
            assert app.query_one("#empty", ui.Table).row_count == 0 and not app._errors
    run(main())


# ── mini grafik ve çift tık ───────────────────────────────

def test_sparkline():
    async def main():
        class Spark(ui.App):
            def compose(self):
                yield ui.Sparkline([0.1, 0.5], label="CPU", value_format="{:.0%}", max_value=1.0, maxlen=5, id="s")
                yield ui.Sparkline(id="tall", height=3, value_format=lambda v: f"{v:.1f}")

        app = Spark()
        async with app.run_test() as pilot:
            spark = app.query_one("#s", ui.Sparkline)
            for value in (0.2, 0.3, 0.9, 1.5):
                spark.append(value)
            assert spark.data == [0.5, 0.2, 0.3, 0.9, 1.5]
            app.query_one("#tall", ui.Sparkline).append(3)
            await pilot.pause()
            assert not app._errors
    run(main())


def test_double_click_count():
    async def main():
        counts: list[int] = []

        class Clicks(ui.App):
            def compose(self):
                yield ui.Static("tıkla", id="s")

            def on_click(self, event: ui.Click) -> None:
                counts.append(event.count)

        app = Clicks()
        async with app.run_test() as pilot:
            for _ in range(3):
                await pilot.click("#s")
            await pilot.pause(0.5)
            await pilot.click("#s")
            assert counts == [1, 2, 1, 1]
    run(main())


def test_option_list_messages_filter_and_multi():
    class Lists(ui.App):
        def __init__(self) -> None:
            super().__init__()
            self.events: list = []

        def compose(self):
            yield ui.OptionList(["Elma", "Armut", "Çilek", "Şeftali"], id="tek", rows=3,
                                on_select=lambda i: self.events.append(("geri çağrı", i)))
            yield ui.OptionList(["a", "b", "c"], id="cok", multi=True, selected=[2])

        def on_option_list_highlighted(self, event: ui.OptionList.Highlighted) -> None:
            self.events.append(("imleç", event.option_list.id, event.index))

        def on_option_list_selected(self, event: ui.OptionList.Selected) -> None:
            self.events.append(("seçildi", event.index, event.label))

        def on_option_list_submitted(self, event: ui.OptionList.Submitted) -> None:
            self.events.append(("onaylandı", event.indices))

    async def main():
        app = Lists()
        async with app.run_test() as pilot:
            tek = app.query_one("#tek", ui.OptionList)
            assert app.focused is tek and tek.region.h == 3 * app.painter.row  # en çok 3 satır
            await pilot.press("down")
            await pilot.type("cilek")  # Türkçe harfler gevşek eşleşir
            assert [tek.options[i] for i, _ in tek.matches] == ["Çilek"] and tek.value == "Çilek"
            await pilot.press("enter", "tab", "space", "down", "space", "enter")
            assert app.events == [("imleç", "tek", 1), ("imleç", "tek", 2), ("seçildi", 2, "Çilek"),
                                  ("geri çağrı", 2), ("imleç", "cok", 1), ("onaylandı", [0, 1, 2])]
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
