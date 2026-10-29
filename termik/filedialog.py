"""Dosya ve klasör seçme diyalogları.

    yol = await self.window.ask_open("Resim seç", filetypes=[("Resimler", "*.png *.jpg")])
    yollar = await self.window.ask_open(multiple=True)        # liste; vazgeçilirse boş
    hedef = await self.window.ask_save(name="rapor.md")
    klasör = await self.window.ask_folder(folder="~/Belgeler")

Sonuç pathlib.Path, vazgeçilirse None. Hangi diyaloğun açılacağını `dialogs` ayarı seçer:
"native" (varsayılan) işletim sisteminin kendi diyaloğu, "builtin" pencerenin içinde açılan,
klavyeyle gezilen termik gezgini (FileBrowser). Yerel diyalog bulunamazsa (Linux'ta zenity ya da
kdialog kurulu değilse) ya da pencere sahte sürücüde çalışıyorsa (testler) termik gezgini açılır.

Yerel diyalog ayrı bir thread'de açılır: açıkken pencere çizilmeye devam eder ama girdi almaz.
Windows'ta Common Item Dialog (ctypes ile COM), macOS'ta osascript, Linux'ta zenity ya da kdialog.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from . import system
from .dialog import Dialog
from .markup import escape
from .widget import action
from .widgets import DirectoryTree, Input, Static

if TYPE_CHECKING:
    from .app import Window

Filters = list[tuple[str, list[str]]]


class Unavailable(Exception):
    """Bu sistemde yerel diyalog açılamadı; termik gezginine düşülür."""


def normalize_filters(filetypes) -> Filters:
    """[("Resimler", "*.png *.jpg"), "*.txt", ("Tümü", ["*.*"])] → [("Resimler", ["*.png", "*.jpg"]), …]"""
    out: Filters = []
    for item in filetypes or ():
        label, patterns = (item, item) if isinstance(item, str) else item
        if isinstance(patterns, str):
            patterns = patterns.replace(";", " ").split()
        patterns = [p.strip() for p in patterns if p.strip()]
        if patterns:
            out.append((str(label), patterns))
    return out


def _extension(patterns: list[str]) -> str:
    """Kaydederken eklenecek uzantı: ilk "*.md" gibi kalıptan "md"; "*.*" için boş."""
    for pattern in patterns:
        ext = pattern[2:] if pattern.startswith("*.") else ""
        if ext and not any(ch in ext for ch in "*?["):
            return ext
    return ""


def _folder(folder) -> str | None:
    if folder is None:
        return None
    path = os.path.abspath(os.path.expanduser(os.path.expandvars(str(folder))))
    return path if os.path.isdir(path) else None


async def ask(window: Window, mode: str, title: str, *, filetypes=None, folder=None, name: str = "",
              multiple: bool = False):
    """mode: "open", "save", "folder" ya da "any" (dosya ya da klasör; yerel diyalogda dosya açar).
    Sonuç Path ya da None; multiple=True ise Path listesi."""
    filters = normalize_filters(filetypes)
    start = _folder(folder)
    app = window.app
    backend = _backend() if app.dialogs == "native" and not app._headless else None
    if backend is not None:
        try:
            result = await _in_thread(window, backend, "open" if mode == "any" else mode, title, start, name,
                                      filters, multiple)
        except Unavailable:
            pass
        else:
            return _paths(result, multiple)
    browser = FileBrowser(start or os.getcwd(), mode=mode, title=title, filters=filters, multiple=multiple,
                          name=name)
    return _paths(await window.push_screen_wait(browser), multiple)


def _paths(result, multiple: bool):
    if multiple:
        return [Path(p) for p in ([result] if isinstance(result, str) else result or [])]
    if isinstance(result, list):
        result = result[0] if result else None
    return Path(result) if result else None


async def _in_thread(window: Window, backend: Callable, *args):
    """Yerel diyaloğu ayrı thread'de aç; bu sırada pencere girdi almasın."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    owner = system.hwnd(window.native)
    app = window.app

    def settle(result: Any, exc: BaseException | None) -> None:
        if not future.done():
            future.set_exception(exc) if exc is not None else future.set_result(result)

    def run() -> None:
        try:
            result = backend(*args, owner)
        except BaseException as exc:  # noqa: BLE001 (sonuç olarak bekleyene iletilir)
            loop.call_soon_threadsafe(settle, None, exc)
        else:
            loop.call_soon_threadsafe(settle, result, None)

    window._dialogs += 1
    app._sync_blocking()
    try:
        threading.Thread(target=run, name="termik-diyalog", daemon=True).start()
        return await future
    finally:
        window._dialogs -= 1
        app._sync_blocking()
        if window.is_open and not owner:  # Windows'ta sahibine odağı diyalog kendisi verir
            window.native.focus()


def _backend() -> Callable | None:
    if sys.platform == "win32":
        return _windows
    if sys.platform == "darwin":
        return _macos if shutil.which("osascript") else None
    kde = "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    for name, fn in (("kdialog", _kdialog), ("zenity", _zenity)) if kde else (("zenity", _zenity), ("kdialog", _kdialog)):
        if shutil.which(name):
            return fn
    return None


# ── Windows: Common Item Dialog ───────────────────────────

_CLSID_OPEN = "{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}"
_CLSID_SAVE = "{C0B4E2F3-BA21-4773-8DBA-335EC946EB8B}"
_IID_OPEN = "{D57C7288-D4AD-4768-BE02-9D969532D960}"
_IID_SAVE = "{84BCCD23-5FDE-4CDB-AEA4-AF64B83D78AB}"
_IID_ITEM = "{43826D1E-E718-42EE-BC55-A1E261C37BFE}"
_CANCELLED = -2147023673  # HRESULT_FROM_WIN32(ERROR_CANCELLED)


def _windows(mode: str, title: str, folder: str | None, name: str, filters: Filters, multiple: bool,
             owner: int):
    """IFileOpenDialog / IFileSaveDialog. owner verilirse diyalog o pencereye bağlı açılır ve onu kilitler."""
    import ctypes
    import uuid
    from ctypes import wintypes as w

    ole32 = ctypes.WinDLL("ole32")
    shell32 = ctypes.WinDLL("shell32")
    ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, w.DWORD)
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = (ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.c_void_p,
                                       ctypes.POINTER(ctypes.c_void_p))
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
    shell32.SHCreateItemFromParsingName.argtypes = (w.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                                    ctypes.POINTER(ctypes.c_void_p))
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long

    def guid(text: str):
        return ctypes.create_string_buffer(uuid.UUID(text).bytes_le, 16)

    def call(obj, index: int, *args, types: tuple = ()) -> int:
        """COM arayüzünün index'inci metodu (sanal tablodan)."""
        table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(table[index])(obj, *args)

    def check(hr: int) -> int:
        if hr < 0:
            raise OSError(f"dosya diyaloğu açılamadı (0x{hr & 0xFFFFFFFF:08X})")
        return hr

    def release(obj) -> None:
        if obj:
            call(obj, 2)

    def path_of(item) -> str:
        text = ctypes.c_void_p()
        check(call(item, 5, 0x80058000, ctypes.byref(text),  # IShellItem::GetDisplayName(SIGDN_FILESYSPATH)
                   types=(w.DWORD, ctypes.POINTER(ctypes.c_void_p))))
        try:
            return ctypes.wstring_at(text.value)
        finally:
            ole32.CoTaskMemFree(text)

    initialized = ole32.CoInitializeEx(None, 0x2 | 0x4) >= 0  # tek thread'li daire, OLE1 DDE kapalı
    dialog = ctypes.c_void_p()
    try:
        save = mode == "save"
        if ole32.CoCreateInstance(guid(_CLSID_SAVE if save else _CLSID_OPEN), None, 1,
                                  guid(_IID_SAVE if save else _IID_OPEN), ctypes.byref(dialog)) < 0 or not dialog:
            raise Unavailable
        options = w.DWORD()
        check(call(dialog, 10, ctypes.byref(options), types=(ctypes.POINTER(w.DWORD),)))  # GetOptions
        flags = options.value | 0x40 | 0x8 | 0x800  # FORCEFILESYSTEM, NOCHANGEDIR, PATHMUSTEXIST
        if mode == "folder":
            flags |= 0x20  # PICKFOLDERS
        elif save:
            flags |= 0x2  # OVERWRITEPROMPT
        else:
            flags |= 0x1000 | (0x200 if multiple else 0)  # FILEMUSTEXIST, ALLOWMULTISELECT
        check(call(dialog, 9, flags, types=(w.DWORD,)))  # SetOptions
        if title:
            check(call(dialog, 17, title, types=(w.LPCWSTR,)))  # SetTitle
        if filters and mode != "folder":
            class Spec(ctypes.Structure):
                _fields_ = [("name", w.LPCWSTR), ("spec", w.LPCWSTR)]

            specs = (Spec * len(filters))(*[Spec(label, ";".join(patterns)) for label, patterns in filters])
            check(call(dialog, 4, len(filters), specs, types=(w.UINT, ctypes.c_void_p)))  # SetFileTypes
            ext = _extension(filters[0][1]) if save else ""
            if ext:
                check(call(dialog, 22, ext, types=(w.LPCWSTR,)))  # SetDefaultExtension
        if name:
            check(call(dialog, 15, name, types=(w.LPCWSTR,)))  # SetFileName
        if folder:
            item = ctypes.c_void_p()
            if shell32.SHCreateItemFromParsingName(folder, None, guid(_IID_ITEM), ctypes.byref(item)) >= 0:
                call(dialog, 12, item, types=(ctypes.c_void_p,))  # SetFolder
                release(item)
        hr = call(dialog, 3, owner or None, types=(w.HWND,))  # Show: kapanana kadar bekler
        if hr == _CANCELLED:
            return None
        check(hr)
        if multiple and mode == "open":
            items = ctypes.c_void_p()
            check(call(dialog, 27, ctypes.byref(items), types=(ctypes.POINTER(ctypes.c_void_p),)))  # GetResults
            try:
                count = w.DWORD()
                check(call(items, 7, ctypes.byref(count), types=(ctypes.POINTER(w.DWORD),)))  # GetCount
                paths = []
                for i in range(count.value):
                    item = ctypes.c_void_p()
                    check(call(items, 8, i, ctypes.byref(item),  # GetItemAt
                               types=(w.DWORD, ctypes.POINTER(ctypes.c_void_p))))
                    try:
                        paths.append(path_of(item))
                    finally:
                        release(item)
                return paths
            finally:
                release(items)
        item = ctypes.c_void_p()
        check(call(dialog, 20, ctypes.byref(item), types=(ctypes.POINTER(ctypes.c_void_p),)))  # GetResult
        try:
            return path_of(item)
        finally:
            release(item)
    finally:
        release(dialog)
        if initialized:
            ole32.CoUninitialize()


# ── macOS ve Linux: yardımcı programlar ───────────────────

def _run(args: list[str], multiple: bool, cancelled: Callable[[subprocess.CompletedProcess], bool]):
    try:
        proc = subprocess.run(args, capture_output=True, text=True)
    except OSError as exc:
        raise Unavailable from exc
    if cancelled(proc):
        return None
    if proc.returncode != 0:
        raise Unavailable
    paths = [line for line in proc.stdout.splitlines() if line]
    return paths if multiple else (paths[0] if paths else None)


def _macos(mode: str, title: str, folder: str | None, name: str, filters: Filters, multiple: bool, owner: int):
    def q(text: str) -> str:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    command = {"folder": "choose folder", "save": "choose file name"}.get(mode, "choose file")
    command += f" with prompt {q(title)}"
    if folder:
        command += f" default location POSIX file {q(folder)}"
    if mode == "save" and name:
        command += f" default name {q(name)}"
    if mode == "open":
        patterns = [p for _, group in filters[:1] for p in group]
        if patterns and "*" not in patterns and "*.*" not in patterns:
            command += " of type {" + ", ".join(q(p[2:]) for p in patterns if p.startswith("*.")) + "}"
        if multiple:
            command += " with multiple selections allowed"
    script = (f"set chosen to ({command})\nset out to \"\"\n"
              "if class of chosen is list then\nrepeat with f in chosen\n"
              "set out to out & POSIX path of f & linefeed\nend repeat\n"
              "else\nset out to POSIX path of chosen\nend if\nreturn out")
    return _run(["osascript", "-e", script], multiple, lambda p: p.returncode != 0 and "-128" in p.stderr)


def _zenity(mode: str, title: str, folder: str | None, name: str, filters: Filters, multiple: bool, owner: int):
    args = ["zenity", "--file-selection", f"--title={title}"]
    if mode == "folder":
        args.append("--directory")
    elif mode == "save":
        args += ["--save", "--confirm-overwrite"]
    elif multiple:
        args += ["--multiple", "--separator=\n"]
    if mode == "save" and name:
        args.append(f"--filename={os.path.join(folder or os.getcwd(), name)}")
    elif folder:
        args.append(f"--filename={folder}{os.sep}")
    args += [f"--file-filter={label} | {' '.join(patterns)}" for label, patterns in filters if mode != "folder"]
    return _run(args, multiple, lambda p: p.returncode == 1)


def _kdialog(mode: str, title: str, folder: str | None, name: str, filters: Filters, multiple: bool, owner: int):
    start = folder or os.getcwd()
    if mode == "folder":
        args = ["kdialog", "--getexistingdirectory", start]
    else:
        target = os.path.join(start, name) if mode == "save" and name else start
        args = ["kdialog", "--getsavefilename" if mode == "save" else "--getopenfilename", target]
        if filters:
            args.append("\n".join(f"{label} ({' '.join(patterns)})" for label, patterns in filters))
        if multiple and mode == "open":
            args += ["--multiple", "--separate-output"]
    return _run(args + ["--title", title], multiple, lambda p: p.returncode == 1)


# ── termik gezgini ────────────────────────────────────────

def _keys(*pairs: tuple[str, str]) -> str:
    return "  [faint]·[/]  ".join(f"[dim]{escape(key)}[/] [faint]{text}[/]" for key, text in pairs)


class _BrowserTree(DirectoryTree):
    """Gezginin ağacı: space imleçtekini seçer (çoklu seçimde işaretler), ⌫ üst klasöre çıkar."""

    def _browser(self) -> FileBrowser | None:
        return next((a for a in self.ancestors() if isinstance(a, FileBrowser)), None)

    @action("Seç", key="space", show=False, palette=False)
    def pick(self) -> None:
        node, browser = self.cursor_node, self._browser()
        if node is not None and node.data and browser is not None:
            browser.pick(node.data, toggle=True)

    @action("Üst klasör", key="backspace", show=False, palette=False)
    def go_up(self) -> None:
        browser = self._browser()
        if browser is not None:
            browser.go_up()


class FileBrowser(Dialog):
    """termik'in kendi dosya gezgini: işletim sisteminin diyaloğu yoksa ya da dialogs = "builtin" ise.

    ⏎ klasörü açar ya da dosyayı seçer, space imleçtekini seçer (çoklu seçimde işaretler), ⌫ üst
    klasöre çıkar. Kaydederken alttaki alana dosya adı yazılır; dosya ağaçta seçili klasöre kaydedilir.
    Sonuç yol (str), çoklu seçimde yol listesi; vazgeçilirse None.
    """

    def __init__(self, start: str, *, mode: str = "any", title: str = "", filters: Filters | None = None,
                 multiple: bool = False, name: str = "") -> None:
        save = mode == "save"
        super().__init__(title or "Gözat", buttons=[("Vazgeç", None), ("Kaydet" if save else "Seç", True)],
                         default=1, width=76)
        self.mode = mode
        self.multiple = multiple and mode == "open"
        self.filters = normalize_filters(filters)
        self.folder = start
        self.marked: dict[str, str] = {}  # işaretlenen dosyalar → ağaçtaki asıl etiketleri
        self.filename = Input(name, label="Ad", placeholder="dosya adı") if save else None
        self.tree = self._tree(start)
        self.where = Static(self._where(start), wrap=False)

    def _tree(self, path: str) -> _BrowserTree:
        patterns = self.filters[0][1] if self.filters else None
        if patterns and any(p in ("*", "*.*") for p in patterns):
            patterns = None
        return _BrowserTree(path, height=14, patterns=patterns, dirs_only=self.mode == "folder")

    def _where(self, path: str) -> str:
        if self.filename is not None:
            path = os.path.join(self._save_folder(path), self._final_name() or "…")
        line = f"[faint]{escape(path)}[/]"
        if self.filters:
            label, patterns = self.filters[0]
            line += f"  [faint]· {escape(label)} ({escape(' '.join(patterns))})[/]"
        return line

    def compose_body(self):
        yield self.where
        yield self.tree
        if self.filename is not None:
            yield self.filename
        hints = [("⏎", "aç"), ("space", "işaretle" if self.multiple else "seç"), ("⌫", "üst klasör"),
                 ("esc", "vazgeç")]
        yield Static(_keys(*hints), wrap=False)

    def on_mount(self) -> None:
        if self.filename is not None and self.filename.value:
            self.filename.focus()
        else:
            self.tree.focus()

    def _save_folder(self, path: str | None = None) -> str:
        """Kaydedilecek klasör: ağaçta seçili klasör, dosya seçiliyse onun klasörü."""
        if path is None:
            node = self.tree.cursor_node
            path = node.data if node is not None and node.data else self.folder
        return path if os.path.isdir(path) else os.path.dirname(path)

    def choose(self, result: Any) -> None:
        if result is not True:
            self.dismiss(None)
        elif self.filename is not None:
            self.call_later(self.submit_save)
        elif self.multiple and self.marked:
            self.dismiss(list(self.marked))
        else:
            node = self.tree.cursor_node
            self.pick(node.data if node is not None and node.data else self.folder)

    def pick(self, path: str, *, toggle: bool = False) -> None:
        """Bir yol seçildi (⏎, space ya da çift tık)."""
        node = self.tree.cursor_node
        if self.filename is not None:  # kaydet: klasör açılır, dosyanın adı alana geçer
            if os.path.isdir(path):
                if node is not None:
                    node.expand()
            else:
                self.filename.value = os.path.basename(path)
                self.filename.focus()
            self.where.update(self._where(path))
            return
        if self.mode == "folder":
            self.dismiss(path if os.path.isdir(path) else os.path.dirname(path))
        elif self.mode == "open" and os.path.isdir(path):  # dosya bekleniyor: klasörü aç
            if node is not None:
                node.expand()
        elif self.multiple and toggle:
            self._toggle(node)
        elif self.multiple:
            self.dismiss([*self.marked, *([path] if path not in self.marked else [])])
        else:
            self.dismiss(path)

    def _toggle(self, node) -> None:
        if node is None or not node.data:
            return
        if node.data in self.marked:
            node.label = self.marked.pop(node.data)
        else:
            self.marked[node.data] = node.label
            node.label = f"[green]✓[/] {node.label}"
        self.tree.refresh()
        count = len(self.marked)
        self.where.update(f"[faint]{count} dosya işaretli[/]" if count else self._where(node.data))

    def _final_name(self) -> str:
        """Yazılan ad; uzantısı yoksa süzgeçteki ilk uzantı eklenir ("notlar" → "notlar.txt")."""
        name = self.filename.value.strip().strip('"')
        ext = _extension(self.filters[0][1]) if self.filters else ""
        return f"{name}.{ext}" if name and ext and not os.path.splitext(name)[1] else name

    async def submit_save(self) -> None:
        name = self._final_name()
        if not name:
            self.filename.focus()
            self.window.notify("dosya adı yazın", "warn")
            return
        path = name if os.path.isabs(name) else os.path.join(self._save_folder(), name)
        if os.path.isdir(path):
            self.window.notify("bu bir klasör", "warn")
            return
        if os.path.exists(path) and not await self.window.confirm(
                f"[bold]{escape(os.path.basename(path))}[/] zaten var. Üzerine yazılsın mı?", title="Kaydet",
                yes="Üzerine yaz"):
            return
        self.dismiss(path)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.where.update(self._where(self._save_folder()))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.call_later(self.submit_save)

    def on_tree_node_highlighted(self, event) -> None:
        path = event.node.data or self.folder
        if self.multiple and self.marked:
            return
        self.where.update(self._where(path))

    def on_tree_node_selected(self, event) -> None:
        event.stop()
        path = event.node.data
        if path and not os.path.isdir(path):  # dosyaya ⏎ ya da çift tık: seç
            self.pick(path)

    def go_up(self) -> None:
        current = os.path.normpath(self.folder)
        parent = os.path.dirname(current)
        if not parent or parent == current:
            return
        tree = self._tree(parent)
        box = self.tree.parent
        box.mount(tree, before=box.children.index(self.tree))
        self.tree.remove()
        self.tree, self.folder = tree, parent
        self.marked.clear()
        tree.focus()
        for node in tree.root.children:  # geldiğimiz klasör seçili olsun
            if node.data and os.path.normpath(node.data) == current:
                tree.select(node)
                break
        self.where.update(self._where(parent))
