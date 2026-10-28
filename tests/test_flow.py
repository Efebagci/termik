"""Akış API'si testleri.

Pencere kipi görünmez pencereyle sürülür: script ayrı thread'de çalışır, test pencerenin
döngüsünde Pilot ile tuşlara basar. Terminal kipi sahte stdin/stdout ile denenir. Ana thread'e
bağlı davranışlar (script'in bitişi, pencere kapanınca KeyboardInterrupt, yakalanmayan hata)
ayrı bir Python sürecinde, SDL'in sahte görüntü sürücüsüyle denenir.

    python tests/test_flow.py
"""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

import _ortam  # noqa: E402,F401  (kullanıcının tercihlerinden yalıt)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from termik.app import Pilot  # noqa: E402
from termik.flow import Session, window  # noqa: E402
from termik.flow.common import format_table  # noqa: E402
from termik.flow.terminal import to_ansi  # noqa: E402
from termik.flow.window import PathBrowser, complete_path  # noqa: E402
from termik.markup import plain_text  # noqa: E402
from termik.theme import THEMES  # noqa: E402


class Harness:
    """Script'i ayrı thread'de çalıştırır, görünmez pencereyi Pilot ile sürer.

        with Harness(lambda s: s.ask("Ad")) as h:
            h.prompt()
            h.type("Efe")
            h.press("enter")
            assert h.finish() == "Efe"
    """

    def __init__(self, script, **settings) -> None:
        self.result = self.error = None
        self.session = Session(mode="window", headless=True, **settings)
        self.thread = threading.Thread(target=self._main, args=(script,), daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while self.session._backend is None:  # pencere ilk çağrıda açılır
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise self.error or RuntimeError("pencere açılmadı")
            time.sleep(0.005)
        self.backend = self.session._backend
        self.app = self.backend.app
        self.pilot = Pilot(self.app)

    def _main(self, script) -> None:
        try:
            self.result = script(self.session)
        except BaseException as exc:
            self.error = exc

    def __enter__(self) -> Harness:
        return self

    def __exit__(self, *exc) -> None:
        self.session.close()

    def run(self, coro, timeout: float = 10.0):
        """Coroutine'i pencere thread'inin döngüsünde çalıştır, sonucunu bekle."""
        return asyncio.run_coroutine_threadsafe(coro, self.app._loop).result(timeout)

    def call(self, fn):
        async def go():
            return fn()
        return self.run(go())

    def press(self, *keys: str) -> None:
        self.run(self.pilot.press(*keys))

    def type(self, text: str) -> None:
        self.run(self.pilot.type(text))

    def until(self, predicate, timeout: float = 5.0) -> None:
        self.run(self.pilot.wait_until(predicate, timeout), timeout + 2)

    def prompt(self, kind: type | None = None, after=None):
        """Cevap bekleyen soruyu bekle; after verilirse ondan sonra gelenini."""
        def ready() -> bool:
            p = self.app.active_prompt
            return p is not None and p is not after and p.listening and (kind is None or isinstance(p, kind))
        self.until(ready)
        return self.app.active_prompt

    def text(self) -> str:
        return self.call(lambda: "\n".join(e.plain() for e in self.app.transcript.children))

    def finish(self, timeout: float = 10.0):
        """Script'in bitmesini bekle; hata verdiyse fırlat, yoksa dönüş değerini ver."""
        self.thread.join(timeout)
        assert not self.thread.is_alive(), "script bitmedi"
        if self.error is not None:
            raise self.error
        return self.result

    def done(self) -> str:
        """Script bitsin, pencere sonucu işlesin; dökümü döndür."""
        self.finish()
        self.until(lambda: self.app.outcome is not None)
        return self.text()


def run(coro):
    return asyncio.run(coro)


# ── pencere: çıktı ────────────────────────────────────────

def test_output_transcript():
    def script(s):
        s.print("Merhaba [bold]dünya[/]", 42)
        s.print("a", "b", sep="-", end="")
        s.print(" devam")
        s.print([1, 2])  # yazı olmayan nesne markup sayılmaz
        s.print("[b]olduğu gibi[/b]", markup=False)
        s.ok("tamam")
        s.info("bilgi")
        s.warn("dikkat")
        s.error("olmadı")
        s.rule("Bölüm")
        s.table([("rapor.pdf", 1200)], headers=["ad", "boyut"])

    with Harness(script) as h:
        text = h.done()
        for part in ("Merhaba dünya 42", "a-b devam", "[1, 2]", "[b]olduğu gibi[/b]", "✓ tamam", "• bilgi",
                     "⚠ dikkat", "✗ olmadı", "── Bölüm ──", "rapor.pdf   1200"):
            assert part in text, part
        assert h.app.outcome == "done" and not h.app._errors


def test_output_from_another_thread_goes_above_question():
    def script(s):
        threading.Timer(0.1, s.print, args=("arka plandan",)).start()
        return s.ask("Ad")

    with Harness(script) as h:
        p = h.prompt()
        h.until(lambda: "arka plandan" in "".join(e.plain() for e in h.app.transcript.children))
        kids = h.app.transcript.children
        assert kids.index(p) == len(kids) - 1  # soru hep en altta
        h.type("Efe")
        h.press("enter")
        assert h.finish() == "Efe"


def test_transcript_keeps_last_lines():
    def script(s):
        for i in range(window.MAX_LINES + 300):
            s.print(f"satır {i}")

    with Harness(script) as h:
        lines = h.done().split("\n")
        assert len(lines) == window.MAX_LINES
        assert lines[0] == "satır 300" and lines[-1] == f"satır {window.MAX_LINES + 299}"
        assert h.app.transcript.follow and h.app.transcript.scroll_y == h.app.transcript.max_scroll


# ── pencere: sorular ──────────────────────────────────────

def test_ask_conversion_validation_and_default():
    def script(s):
        return (s.ask("Port", type=int), s.ask("Ad", default="Efe"), s.ask("Oran", default=0.5),
                s.ask("Kod", validate=lambda v: len(v) == 3 or "üç harf olmalı"), s.ask("Parola", password=True))

    with Harness(script) as h:
        p = h.prompt()
        h.type("abc")
        h.press("enter")
        h.until(lambda: p.error)
        assert "tam sayı" in p.error
        h.press("ctrl+a")
        h.type("8080")
        h.press("enter")
        p = h.prompt(after=p)
        assert p.input.value == "Efe" and p.input.selected_text == "Efe"  # varsayılan seçili gelir
        h.press("enter")
        p = h.prompt(after=p)
        h.type("2,5")  # seçili varsayılanın yerine geçer; ondalık virgül de olur
        h.press("enter")
        p = h.prompt(after=p)
        h.type("ab")
        h.press("enter")
        h.until(lambda: p.error == "üç harf olmalı")
        h.type("c")
        h.press("enter")
        p = h.prompt(after=p)
        h.type("gizli")
        h.press("enter")
        assert h.finish() == (8080, "Efe", 2.5, "abc", "gizli")
        text = h.done()
        assert "✓ Parola  ••••••" in text and "gizli" not in text and "✓ Port  8080" in text


def test_choose_filter_keys_and_mouse():
    def script(s):
        return (s.choose("Mod", ["Tam", "Artımlı", "Diferansiyel"]),
                s.choose("Sıkıştırma", {"Yok": None, "Hızlı": 1, "Güçlü": 9}, default=9),
                s.choose("Hedef", ["Disk", "Bulut", "Ağ"]))

    with Harness(script) as h:
        p = h.prompt()
        h.type("artimli")  # Türkçe harfler gevşek eşleşir
        assert [p.list.options[i] for i, _ in p.list.matches] == ["Artımlı"] and "süz:" in p.badge()
        h.press("enter")
        p = h.prompt(after=p)
        assert p.list.cursor_line == 2
        h.press("up", "enter")
        p = h.prompt(after=p)
        lst = p.list
        h.until(lambda: lst.region.h > 0)
        row = h.app.painter.row
        h.run(h.pilot.click(lst, offset=(row, row + row // 2)))  # ikinci satır
        assert h.finish() == ("Artımlı", 1, "Bulut")
        assert "✓ Sıkıştırma  Hızlı" in h.done()


def test_choose_many_limits_and_toggle_all():
    def script(s):
        return s.choose_many("Uzantılar", [".jpg", ".png", ".mp4", ".txt"], default=[".png"], min=1, max=3)

    with Harness(script) as h:
        p = h.prompt()
        assert p.list.selected == {1}
        h.press("space")
        h.press("down", "space")
        assert p.list.selected == {0}
        h.press("ctrl+a", "enter")
        h.until(lambda: "en çok 3" in p.error)
        h.press("ctrl+a", "enter")  # hepsi işaretliyken hepsini kaldırır
        h.until(lambda: "en az 1" in p.error)
        h.type("mp")
        h.press("space", "enter")
        assert h.finish() == [".mp4"]


def test_confirm_keys_and_buttons():
    def script(s):
        return [s.confirm("Bir?"), s.confirm("İki?", default=False), s.confirm("Üç?", yes="Sil", no="Vazgeç"),
                s.confirm("Dört?")]

    with Harness(script) as h:
        p = h.prompt()
        h.press("h")
        p = h.prompt(after=p)
        h.press("enter")
        p = h.prompt(after=p)
        assert "s/v" in p.hints()
        h.press("s")
        p = h.prompt(after=p)
        h.until(lambda: p.choice._rects)
        rect = p.choice._rects[False]
        h.run(h.pilot.click(p.choice, offset=(rect.centerx - p.choice.region.x, rect.centery - p.choice.region.y)))
        assert h.finish() == [False, False, True, False]


def test_ask_path_completion_and_checks():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("rapor.pdf", "readme.md"):
            Path(tmp, name).write_text("x", encoding="utf-8")
        Path(tmp, "resimler").mkdir()
        sep = os.sep
        assert complete_path(os.path.join(tmp, "res")) == (os.path.join(tmp, "resimler") + sep, ["resimler" + sep])
        assert complete_path(os.path.join(tmp, "re")) == (os.path.join(tmp, "re"), ["resimler" + sep, "readme.md"])
        assert complete_path(os.path.join(tmp, "r"), kind="dir")[0] == os.path.join(tmp, "resimler") + sep

        def script(s):
            return s.ask_path("Herhangi"), s.ask_path("Klasör", kind="dir"), s.ask_path("Yeni", must_exist=False)

        with Harness(script) as h:
            p = h.prompt()
            h.type(os.path.join(tmp, "re"))
            h.press("tab")  # ortak kısım zaten yazılı: adaylar arasında döner, klasörler önce
            assert p.input.value == os.path.join(tmp, "resimler") + sep and len(p.candidates) == 2
            h.press("tab")
            assert p.input.value == os.path.join(tmp, "readme.md")
            h.press("shift+tab", "shift+tab")
            assert p.input.value == os.path.join(tmp, "readme.md")
            h.press("enter")
            p = h.prompt(after=p)
            h.type(os.path.join(tmp, "readme.md"))
            h.press("enter")
            h.until(lambda: p.error == "bu bir klasör değil")
            h.press("ctrl+a")
            h.type(os.path.join(tmp, "r"))
            h.press("tab")  # klasör sorusunda dosyalar aday değil: tek aday
            assert p.input.value == os.path.join(tmp, "resimler") + sep and not p.candidates
            h.press("enter")
            p = h.prompt(after=p)
            h.type(f'"{os.path.join(tmp, "yok")}"')  # kopyalanan yolun tırnakları atılır
            h.press("enter")
            assert h.finish() == (Path(tmp, "readme.md"), Path(tmp, "resimler"), Path(tmp, "yok"))


def test_path_browser():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "alt").mkdir()
        Path(tmp, "alt", "veri.csv").write_text("1", encoding="utf-8")

        with Harness(lambda s: s.ask_path("Dosya", kind="file")) as h:
            p = h.prompt()
            h.type(tmp + os.sep)
            h.press("ctrl+o")
            h.until(lambda: isinstance(h.app.screen, PathBrowser))
            browser = h.app.screen
            assert h.app.focused is browser.tree
            h.press("backspace")  # üst klasör: geldiğimiz klasör seçili
            assert browser.folder == os.path.dirname(os.path.normpath(tmp))
            assert os.path.normpath(browser.tree.cursor_node.data) == os.path.normpath(tmp)
            h.press("escape")
            h.until(lambda: not isinstance(h.app.screen, PathBrowser))
            assert h.app.focused is p.input and p.input.value == tmp + os.sep
            h.press("ctrl+o")
            h.until(lambda: isinstance(h.app.screen, PathBrowser))
            h.press("down", "enter")  # klasörde ⏎ açar
            h.press("down", "enter")  # dosyada ⏎ seçer
            h.until(lambda: p.input.value.endswith("veri.csv"))
            h.press("enter")
            assert h.finish() == Path(tmp, "alt", "veri.csv")


# ── pencere: ilerleme ve yaşam döngüsü ────────────────────

def test_track_progress_and_spinner_states():
    def script(s):
        total = sum(s.track(range(5), "Sayılıyor", unit="sayı"))
        with s.progress("İndiriliyor", total=2048, unit="B") as bar:
            bar.advance(1024)
            bar.advance(1024)
        with s.spinner("Bekleniyor") as sp:
            sp.update("yarısı")
        try:
            with s.spinner("Patlıyor"):
                raise ValueError("bozuk")
        except ValueError:
            pass
        for i in s.track(range(10), "Yarım"):
            if i == 3:
                break
        return total

    with Harness(script) as h:
        text = h.done()
        assert h.result == 10
        for part in ("✓ Sayılıyor  5 sayı", "✓ İndiriliyor  2,0 KB", "✓ Bekleniyor  yarısı",
                     "✗ Patlıyor", "ValueError: bozuk", "■ Yarım  3/10 öğe", "durduruldu"):
            assert part in text, part


def test_live_bar_while_running():
    gate = threading.Event()

    def script(s):
        with s.progress("Kopyalanıyor", total=10, unit="dosya") as bar:
            bar.advance(4)
            gate.wait(5)

    with Harness(script) as h:
        h.until(lambda: any(isinstance(e, window.LiveEntry) for e in h.app.transcript.children))
        entry = next(e for e in h.app.transcript.children if isinstance(e, window.LiveEntry))
        h.until(lambda: entry.progress.done == 4)
        h.run(h.pilot.pause(0.15))  # canlı satır kendi zamanlayıcısıyla yenilenir
        assert entry._timer is not None and "4/10 dosya" in entry.plain()
        gate.set()
        assert "✓ Kopyalanıyor  4/10 dosya" in h.done()  # erken biten iş sayacını korur
        assert entry._timer is None


def test_window_closed_interrupts_waiting_question():
    def script(s):
        try:
            s.ask("Bekliyor")
        except KeyboardInterrupt:
            s.print("kayboldu")  # pencere kapalı: sessizce atılır
            try:
                s.ask("Tekrar")
            except KeyboardInterrupt:
                return "kesildi"

    with Harness(script) as h:
        h.prompt()
        h.call(h.app.exit)
        assert h.finish() == "kesildi"


def test_uncaught_error_is_shown_and_window_stays():
    def script(s):
        s.print("başladı")
        try:
            1 / 0
        except ZeroDivisionError as exc:  # excepthook'un yaptığını taklit et
            s._backend.script_failed(type(exc), exc, exc.__traceback__)

    with Harness(script, keep_open=False) as h:
        text = h.done()
        assert h.app.outcome == "failed"
        assert "✗ ZeroDivisionError: division by zero" in text and "1 / 0" in text
        h.run(h.pilot.pause(0.3))
        assert h.backend.thread.is_alive()  # keep_open=False olsa da hata görünür kalır


def test_finished_window_closes_with_enter():
    with Harness(lambda s: s.print("x")) as h:
        h.done()
        assert h.app.outcome == "done" and h.backend.thread.is_alive()
        h.call(lambda: h.app._key("enter", None))
        h.backend.thread.join(5)
        assert not h.backend.thread.is_alive()


def test_keep_open_false_closes_when_done():
    with Harness(lambda s: s.print("x"), keep_open=False) as h:
        h.finish()
        h.backend.thread.join(5)
        assert not h.backend.thread.is_alive()


# ── biçimleme ─────────────────────────────────────────────

def test_ansi_and_table_format():
    th = THEMES["okyanus"]
    g = th.green
    assert to_ansi("[bold green]ok[/] x", th, None) == "ok x"
    assert to_ansi("[bold green]ok[/] x", th, "truecolor") == f"\x1b[1;38;2;{g[0]};{g[1]};{g[2]}mok\x1b[0m x"
    assert to_ansi("[red]a[/]", th, "256").startswith("\x1b[38;5;")
    lines = format_table([{"ad": "a", "n": 5}, {"ad": "uzun ad", "n": 12}])
    assert [plain_text(line) for line in lines] == ["ad        n", "───────  ──", "a         5", "uzun ad  12"]
    assert lines[0].startswith("[bold]ad[/]")


# ── terminal ──────────────────────────────────────────────

def run_terminal(script, answers: str = ""):
    """Script'i terminal kipinde, sahte stdin/stdout ile çalıştır: (sonuç, çıktı, hata)."""
    saved = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(answers), io.StringIO()
    result = error = None
    try:
        result = script(Session(mode="terminal"))
    except BaseException as exc:
        error = exc
    finally:
        out = sys.stdout.getvalue()
        sys.stdin, sys.stdout = saved
    return result, out, error


def test_terminal_questions():
    def script(s):
        return (s.ask("Port", type=int), s.ask("Ad", default="Efe"), s.choose("Mod", ["Tam", "Artımlı"]),
                s.choose("Hedef", ["Disk", "Bulut"]), s.choose_many("Uzantı", [".jpg", ".png", ".mp4"]),
                s.confirm("Devam?"), s.confirm("Sil?", default=False), s.ask_path("Yol", must_exist=False))

    result, out, error = run_terminal(script, "abc\n8080\n\nartim\n2\n1,3\n\nevet\n~\n")
    assert error is None, error
    assert result == (8080, "Efe", "Artımlı", "Bulut", [".jpg", ".mp4"], True, True, Path.home())
    assert "✗ bir tam sayı girin" in out and "? Ad (Efe) › " in out and "(e/H)" in out
    assert "✓ Mod   Artımlı" in out and "\x1b" not in out  # özetler hizalı; boruya giden çıktıda renk yok


def test_terminal_choice_errors():
    def script(s):
        return s.choose("Seç", ["Tam yedek", "Tam kopya", "Artımlı"]), s.choose_many("Çok", ["a", "b", "c"])

    result, out, error = run_terminal(script, "tam\n9\nkopya\n2-3\n")
    assert error is None, error
    assert result == ("Tam kopya", ["b", "c"])
    assert "2 seçenek eşleşti" in out and "1 ile 3 arasında" in out


def test_terminal_output_and_eof():
    def script(s):
        s.print("[bold]kalın[/]", 3)
        s.ok("tamam")
        s.rule("Bölüm")
        for _ in s.track(range(3), "Sayılıyor"):
            pass
        with s.spinner("Bekle"):
            pass
        s.ask("Cevapsız")

    _, out, error = run_terminal(script)
    assert isinstance(error, EOFError) and "Cevapsız" in str(error)
    for part in ("kalın 3\n", "✓ tamam\n", "── Bölüm ──", "✓ Sayılıyor  3 öğe", "✓ Bekle", "? Cevapsız › "):
        assert part in out, part


def test_mode_selection_and_validation():
    saved = os.environ.get("TERMIK_MODE"), sys.stdout
    os.environ["TERMIK_MODE"] = "tty"
    sys.stdout = io.StringIO()
    try:
        s = Session()
        assert s.kind is None
        s.print("x")
        assert s.kind == "terminal" and sys.stdout.getvalue() == "x\n"
    finally:
        if saved[0] is None:
            os.environ.pop("TERMIK_MODE", None)
        else:
            os.environ["TERMIK_MODE"] = saved[0]
        sys.stdout = saved[1]
    for bad in (dict(theme="yok"), dict(density="dar"), dict(look="eski")):
        try:
            Session(**bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"kabul edilmemeliydi: {bad}")
    try:
        Session(mode="xyz").print("x")
    except ValueError as exc:
        assert "bilinmeyen kip" in str(exc)
    else:
        raise AssertionError("bilinmeyen kip kabul edildi")


# ── ayrı süreçte, gerçek ana thread'le ────────────────────

def run_child(code: str, stdin: str = "", timeout: float = 60):
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    env.pop("TERMIK_MODE", None)
    return subprocess.run([sys.executable, "-X", "utf8", "-c", code], input=stdin, env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=timeout)


def test_child_script_end_closes_window():
    r = run_child("import termik\ntermik.setup(keep_open=False)\ntermik.print('merhaba')\nprint('SON')")
    assert r.returncode == 0 and "SON" in r.stdout, r.stderr


def test_child_closing_window_interrupts_main_thread():
    code = (
        "import threading, time, termik\n"
        "termik.setup(keep_open=False)\n"
        "termik.print('başla')\n"
        "app = termik.flow._default._backend.app\n"
        "threading.Timer(0.3, app.call_from_thread, args=(app.exit,)).start()\n"
        "t0 = time.monotonic()\n"
        "try:\n"
        "    time.sleep(20)\n"
        "    print('KESİLMEDİ')\n"
        "except KeyboardInterrupt:\n"
        "    print('KESİLDİ', time.monotonic() - t0 < 5)\n"
    )
    r = run_child(code)
    assert "KESİLDİ True" in r.stdout and r.returncode == 0, (r.stdout, r.stderr)


def test_child_uncaught_error_reaches_window():
    code = (
        "import threading, time, termik\n"
        "termik.setup(keep_open=False)\n"
        "termik.print('başla')\n"
        "backend = termik.flow._default._backend\n"
        "def watch():\n"
        "    while backend.app.outcome != 'failed':\n"
        "        time.sleep(0.02)\n"
        "    last = backend.app.transcript.children[-1].plain().split(chr(10))[0]\n"
        "    print('PENCEREDE:', last, flush=True)\n"
        "    backend.app.call_from_thread(backend.app.exit)\n"
        "threading.Thread(target=watch, daemon=True).start()\n"
        "raise ValueError('bozuk')\n"
    )
    r = run_child(code)
    assert "PENCEREDE: ✗ ValueError: bozuk" in r.stdout and "ValueError: bozuk" in r.stderr, (r.stdout, r.stderr)
    assert r.returncode == 1


def test_child_without_pygame_falls_back_to_terminal():
    code = (
        "import sys\n"
        "sys.modules['pygame'] = None  # pygame yokmuş gibi\n"
        "import termik\n"
        "termik.print('[bold]terminalde[/]')\n"
        "try:\n"
        "    termik.App\n"
        "except ImportError as exc:\n"
        "    print('YOK:', exc)\n"
        "print('CEVAP:', termik.ask('Ad'))\n"
    )
    r = run_child(code, stdin="Efe\n")
    assert "terminalde" in r.stdout and "YOK: termik.App pygame-ce ister" in r.stdout, (r.stdout, r.stderr)
    assert "CEVAP: Efe" in r.stdout and "pygame-ce kurulu değil" in r.stderr


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
