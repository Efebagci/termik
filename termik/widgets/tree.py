"""Ağaç ve klasör ağacı."""

from __future__ import annotations

import fnmatch
import os
from typing import Any, Iterable

from ..draw import Painter
from ..events import Click, Message, MouseMove, MouseScroll
from ..text import Style, escape, plain_text
from ..widget import Widget, action


class TreeNode:
    """Ağaçtaki bir düğüm. add() ile çocuk eklenir; data serbest bir değer taşır (ör. dosya yolu).

    suffix satırın sağına soluk yazılır (ör. dosya boyutu). allow_expand=True, henüz çocuğu
    olmayan bir düğümü açılabilir gösterir; ilk açılışta Tree.load_children çağrılır.
    """

    def __init__(self, tree: Tree | None, parent: TreeNode | None, label: str, data: Any = None, *,
                 expanded: bool = False, allow_expand: bool | None = None, suffix: str = "") -> None:
        self.tree = tree
        self.parent = parent
        self.label = label
        self.data = data
        self.suffix = suffix
        self.children: list[TreeNode] = []
        self.expanded = expanded
        self._allow_expand = allow_expand
        self._loaded = False

    def __repr__(self) -> str:
        return f"<TreeNode {self.label!r}>"

    @property
    def allow_expand(self) -> bool:
        return self._allow_expand if self._allow_expand is not None else bool(self.children)

    @property
    def depth(self) -> int:
        depth, node = 0, self.parent
        while node is not None:
            depth, node = depth + 1, node.parent
        return depth

    @property
    def is_last(self) -> bool:
        return self.parent is None or self.parent.children[-1] is self

    def add(self, label: str, data: Any = None, *, expand: bool = False, allow_expand: bool | None = None,
            suffix: str = "") -> TreeNode:
        node = TreeNode(self.tree, self, label, data, expanded=expand, allow_expand=allow_expand, suffix=suffix)
        self.children.append(node)
        self._changed()
        return node

    def add_leaf(self, label: str, data: Any = None, *, suffix: str = "") -> TreeNode:
        return self.add(label, data, allow_expand=False, suffix=suffix)

    def remove(self) -> None:
        if self.parent is not None:
            self.parent.children.remove(self)
            self.parent._changed()

    def remove_children(self) -> None:
        self.children.clear()
        self._loaded = False
        self._changed()

    def expand(self) -> None:
        if self.expanded or not self.allow_expand:
            return
        if not self.children and not self._loaded and self.tree is not None:
            self._loaded = True
            self.tree.load_children(self)
        self.expanded = True
        self._changed()
        if self.tree is not None:
            self.tree.post_message(Tree.NodeExpanded(self.tree, self))

    def collapse(self) -> None:
        if not self.expanded:
            return
        self.expanded = False
        if self.tree is not None:
            self.tree._collapsed(self)
            self.tree.post_message(Tree.NodeCollapsed(self.tree, self))
        self._changed()

    def toggle(self) -> None:
        if self.expanded:
            self.collapse()
        else:
            self.expand()

    def _changed(self) -> None:
        if self.tree is not None:
            self.tree._lines = None
            self.tree.refresh()


class Tree(Widget):
    """Açılır kapanır ağaç.

    ↑/↓ gezer, → açar ya da ilk çocuğa iner, ← kapatır ya da üst düğüme çıkar, Enter/Space
    açar-kapatır ve Tree.NodeSelected iletir. Fareyle satıra tıkla; oka tıklamak ya da çift tık
    aç-kapa yapar. guides=True dalları ince çizgilerle bağlar (`tree` komutundaki gibi).

        tree = Tree("Belgeler")
        projeler = tree.root.add("projeler", expand=True)
        projeler.add_leaf("notlar.txt", suffix="3 KB")
    """

    default_height = "1fr"
    can_focus = True

    class NodeHighlighted(Message):
        def __init__(self, tree: Tree, node: TreeNode) -> None:
            super().__init__()
            self.tree, self.node = tree, node

    class NodeSelected(Message):
        def __init__(self, tree: Tree, node: TreeNode) -> None:
            super().__init__()
            self.tree, self.node = tree, node

    class NodeExpanded(Message):
        def __init__(self, tree: Tree, node: TreeNode) -> None:
            super().__init__()
            self.tree, self.node = tree, node

    class NodeCollapsed(Message):
        def __init__(self, tree: Tree, node: TreeNode) -> None:
            super().__init__()
            self.tree, self.node = tree, node

    def __init__(self, label: str = "", data: Any = None, *, show_root: bool = True, guides: bool = True,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.root = TreeNode(self, None, label, data, expanded=True)
        self.show_root = show_root
        self.guides = guides
        self.cursor_line = 0
        self._lines: list[TreeNode] | None = None
        self._top = 0
        self._visible = 1
        self._hover: int | None = None
        self._geometry = (0, 0, 0)  # son çizimdeki (sol boşluk, girinti, derinlik kayması)

    def load_children(self, node: TreeNode) -> None:
        """Tembel yükleme kancası: açılabilir ama boş bir düğüm ilk kez açılırken çağrılır."""

    # ── satırlar ve imleç ─────────────────────────────────

    @property
    def lines(self) -> list[TreeNode]:
        """Görünen düğümler, yukarıdan aşağı."""
        if self._lines is None:
            out: list[TreeNode] = []

            def walk(node: TreeNode) -> None:
                out.append(node)
                if node.expanded:
                    for child in node.children:
                        walk(child)

            for start in ([self.root] if self.show_root else self.root.children):
                walk(start)
            self._lines = out
        return self._lines

    @property
    def cursor_node(self) -> TreeNode | None:
        lines = self.lines
        return lines[min(self.cursor_line, len(lines) - 1)] if lines else None

    def move_cursor(self, line: int) -> None:
        lines = self.lines
        if not lines:
            return
        line = max(0, min(len(lines) - 1, line))
        if line != self.cursor_line:
            self.cursor_line = line
            self.post_message(Tree.NodeHighlighted(self, lines[line]))
        if line < self._top:
            self._top = line
        elif line >= self._top + self._visible:
            self._top = line - self._visible + 1
        self.refresh()

    def select(self, node: TreeNode) -> None:
        """Düğümü görünür yap (atalarını açarak) ve imleci üstüne getir."""
        ancestor = node.parent
        while ancestor is not None:
            ancestor.expand()
            ancestor = ancestor.parent
        if node in self.lines:
            self.move_cursor(self.lines.index(node))

    def _collapsed(self, node: TreeNode) -> None:
        """Kapanan düğümün altında kalan imleç düğümün kendisine çıkar."""
        current = self.cursor_node
        ancestor = current.parent if current is not None else None
        while ancestor is not None:
            if ancestor is node:
                self._lines = None
                self.move_cursor(self.lines.index(node))
                return
            ancestor = ancestor.parent

    # ── çizim ─────────────────────────────────────────────

    def render(self, p: Painter) -> None:
        th = p.theme
        c = self.content
        lines = self.lines
        self._visible = max(1, c.h // p.row)
        self.cursor_line = max(0, min(self.cursor_line, len(lines) - 1))
        self._top = max(0, min(self._top, len(lines) - self._visible))
        bar = p.ch if len(lines) > self._visible else 0
        lead = p.ch // 2 + (p.ch * 2 if th.selection == "pointer" else 0)
        indent = p.ch * 2
        shift = 0 if self.show_root else 1
        self._geometry = (lead, indent, shift)
        focused = self.has_focus
        right = c.right - bar - p.ch // 2
        for row in range(min(self._visible, len(lines) - self._top)):
            i = self._top + row
            node = lines[i]
            y = c.y + row * p.row
            fg = None
            if i == self.cursor_line:
                fg = p.selection((c.x, y, c.w - bar, p.row), focused=focused)
                if th.selection == "pointer":
                    p.write(c.x + p.ch // 2, y, "❯", Style(bold=True), th.accent if focused else th.dim)
            elif i == self._hover:
                p.hover((c.x, y, c.w - bar, p.row))
            depth = node.depth - shift
            x = c.x + lead + depth * indent
            if self.guides and depth > 0:
                self._draw_guides(p, node, depth, c.x + lead, y, fg or th.border)
            if node.allow_expand:
                p.write(x, y, "▾" if node.expanded else "▸", color=fg or th.faint)
            suffix_w = p.text.width(node.suffix) + p.ch if node.suffix else 0
            label = [(plain_text(node.label), Style(bold=True, fg=fg))] if fg else node.label
            p.write(x + p.ch * 2, y, p.text.elide(label, right - suffix_w - x - p.ch * 2))
            if node.suffix:
                p.write(right, y, node.suffix, color=fg or th.faint, right=True)
        p.scrollbar(c.right - 2, c.y, self._visible * p.row, len(lines), self._visible, self._top, active=focused)

    def _draw_guides(self, p, node: TreeNode, depth: int, base_x: int, y: int, color) -> None:
        """├─ └─ │ dalları, piksele oturan ince çizgilerle (satır aralığında kopmaz)."""
        indent, half, surface = p.ch * 2, p.ch // 2, p.surface
        gx = base_x + (depth - 1) * indent + half
        surface.fill(color, (gx, y, 1, p.row // 2 + 1 if node.is_last else p.row))
        surface.fill(color, (gx, y + p.row // 2, indent - half - 3, 1))
        ancestor, level = node.parent, depth - 1
        while level > 0 and ancestor is not None:  # atası son çocuk değilse onun dalı sürer
            if not ancestor.is_last:
                surface.fill(color, (base_x + (level - 1) * indent + half, y, 1, p.row))
            ancestor, level = ancestor.parent, level - 1

    # ── fare ──────────────────────────────────────────────

    def _line_at(self, y: int) -> int | None:
        row = (y - self.content.y) // max(1, self.app.painter.row)
        i = self._top + row
        return i if 0 <= row < self._visible and i < len(self.lines) else None

    def on_click(self, event: Click) -> None:
        i = self._line_at(event.y)
        if i is None:
            return
        event.stop()
        node = self.lines[i]
        self.move_cursor(i)
        lead, indent, shift = self._geometry
        arrow_x = self.content.x + lead + (node.depth - shift) * indent
        on_arrow = arrow_x - indent // 4 <= event.x < arrow_x + indent
        if node.allow_expand and (on_arrow or event.count == 2):
            node.toggle()
        if event.count == 2:
            self.post_message(Tree.NodeSelected(self, node))

    def on_mouse_move(self, event: MouseMove) -> None:
        i = self._line_at(event.y)
        if i != self._hover:
            self._hover = i
            self.refresh()

    def on_mouse_leave(self) -> None:
        self._hover = None
        self.refresh()

    def on_mouse_scroll(self, event: MouseScroll) -> None:
        event.stop()
        self._top = max(0, min(self._top - event.dy * 3, len(self.lines) - self._visible))
        self.refresh()

    # ── klavye ────────────────────────────────────────────

    @action("Yukarı", key="up", show=False, palette=False)
    def cursor_up(self) -> None:
        self.move_cursor(self.cursor_line - 1)

    @action("Aşağı", key="down", show=False, palette=False)
    def cursor_down(self) -> None:
        self.move_cursor(self.cursor_line + 1)

    @action("Sayfa yukarı", key="pageup", show=False, palette=False)
    def page_up(self) -> None:
        self.move_cursor(self.cursor_line - max(1, self._visible - 1))

    @action("Sayfa aşağı", key="pagedown", show=False, palette=False)
    def page_down(self) -> None:
        self.move_cursor(self.cursor_line + max(1, self._visible - 1))

    @action("Başa", key="home", show=False, palette=False)
    def cursor_home(self) -> None:
        self.move_cursor(0)

    @action("Sona", key="end", show=False, palette=False)
    def cursor_end(self) -> None:
        self.move_cursor(len(self.lines) - 1)

    @action("Kapat ya da üste çık", key="left", show=False, palette=False)
    def collapse_or_parent(self) -> None:
        node = self.cursor_node
        if node is None:
            return
        if node.expanded and node.allow_expand:
            node.collapse()
        elif node.parent is not None and node.parent in self.lines:
            self.move_cursor(self.lines.index(node.parent))

    @action("Aç ya da içe gir", key="right", show=False, palette=False)
    def expand_or_child(self) -> None:
        node = self.cursor_node
        if node is None or not node.allow_expand:
            return
        if not node.expanded:
            node.expand()
        elif node.children:
            self.move_cursor(self.cursor_line + 1)

    @action("Seç", key="enter,space", show=False, palette=False)
    def select_cursor(self) -> None:
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand:
            node.toggle()
        self.post_message(Tree.NodeSelected(self, node))


def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


class DirectoryTree(Tree):
    """Klasör ağacı: alt klasörler ilk açıldıklarında okunur, dosyaların yanında boyut yazar.

    node.data dosyanın ya da klasörün tam yoludur. Gizli dosyalar (nokta ile başlayanlar) ve
    IGNORE'daki klasörler gösterilmez. patterns=("*.png", "*.jpg") yalnızca eşleşen dosyaları,
    dirs_only=True yalnızca klasörleri gösterir.
    """

    IGNORE = frozenset({"__pycache__", ".git", ".venv", "venv", "node_modules"})

    def __init__(self, path: str, *, show_hidden: bool = False, patterns: Iterable[str] | None = None, dirs_only: bool = False,
                 **kwargs) -> None:
        path = os.path.abspath(os.path.expanduser(str(path)))
        super().__init__(f"[blue]{escape(os.path.basename(path) or path)}[/]", data=path, **kwargs)
        self.show_hidden = show_hidden
        self.patterns = [p.casefold() for p in patterns] if patterns else None
        self.dirs_only = dirs_only
        self.root._allow_expand = True
        self.root.expanded = False
        self.root.expand()

    def load_children(self, node: TreeNode) -> None:
        try:
            entries = list(os.scandir(node.data))
        except OSError as exc:
            node.add_leaf(f"[red]✗[/] [dim]{escape(exc.strerror or str(exc))}[/]")
            return
        dirs, files = [], []
        for entry in entries:
            if entry.name in self.IGNORE or (not self.show_hidden and entry.name.startswith(".")):
                continue
            try:
                (dirs if entry.is_dir() else files).append(entry)
            except OSError:
                continue
        for entry in sorted(dirs, key=lambda e: e.name.casefold()):
            node.add(f"[blue]{escape(entry.name)}[/]", entry.path, allow_expand=True)
        if self.dirs_only:
            files = []
        elif self.patterns:
            files = [e for e in files if any(fnmatch.fnmatchcase(e.name.casefold(), p) for p in self.patterns)]
        for entry in sorted(files, key=lambda e: e.name.casefold()):
            try:
                size = _human_size(entry.stat().st_size)
            except OSError:
                size = ""
            node.add_leaf(escape(entry.name), entry.path, suffix=size)
