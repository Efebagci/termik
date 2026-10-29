"""Kısa yazım testleri: Form ve label=, bind= ile değer bağlama, sınıfsız uygulama, düğme kısayolu,
akış köprüsü (show, form'da bileşen), iskelet ve izleyerek çalıştırma.

    python tests/test_easy.py
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import py_compile
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import _ortam  # noqa: E402,F401  (kullanıcının tercihlerinden yalıt)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import termik as ui  # noqa: E402
from termik import dev  # noqa: E402
from termik.__main__ import main as cli  # noqa: E402
from termik.flow import window as flow_window  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from test_flow import Harness, run_terminal  # noqa: E402


def run(coro):
    return asyncio.run(coro)


# ── Form ve label= ────────────────────────────────────────

class FormApp(ui.App):
    def compose(self):
        with ui.Form(id="form"):
            yield ui.Input(label="Kaynak", id="kaynak")
            yield ui.Slider(6, max=9, label="Sıkıştırma düzeyi", id="duzey")
            with ui.Row(label="Seçenekler", gap=2, id="secenek"):
                yield ui.Checkbox("Sıkıştır", True)
                yield ui.Checkbox("Şifrele")
            yield ui.RadioSet("Tam", "Artımlı", label="Mod", id="mod")
            yield ui.Static("etiketsiz not", id="not")
        yield ui.Input(label="Form dışında", id="disari")


def test_form_labels_left_and_top():
    async def main():
        app = FormApp()
        async with app.run_test() as pilot:
            p = app.painter
            form = app.query_one("#form", ui.Form)
            kaynak, duzey = app.query_one("#kaynak"), app.query_one("#duzey")
            lw = p.text.width("Sıkıştırma düzeyi") + p.ch * 2  # en uzun etiket + iki karakter
            assert kaynak.region.x == duzey.region.x == form.content.x + lw
            assert kaynak.region.h == p.row  # Form içinde Input tek satır: etiketi Form çizer
            assert app.query_one("#disari").region.h == p.row * 2  # dışarıda bugünkü gibi üstte
            assert app.query_one("#not").region.x == form.content.x  # etiketsiz: bütün genişlik
            assert app.query_one("#mod").region.x == kaynak.region.x
            assert [w.id for w, *_ in form._labels] == ["kaynak", "duzey", "secenek", "mod"]
            assert all(y == w.region.y for w, x, y, _ in form._labels)
            app.set_theme(form_label="top")
            await pilot.pause()
            assert kaynak.region.x == form.content.x and kaynak.region.y == form.content.y + p.row
            assert all(y == w.region.y - p.row for w, x, y, _ in form._labels)
            assert not app._errors
    run(main())


# ── bind= ─────────────────────────────────────────────────

class Ayar(ui.Widget):
    oran = ui.reactive(0.5)  # ara bileşende reactive: iki yönlü


class BindApp(ui.App):
    kaynak = ui.reactive("C:\\Projeler")
    duzey = ui.reactive(6)
    port = ui.reactive(8080)

    def compose(self):
        yield ui.Input(bind="kaynak", id="kaynak")
        yield ui.Slider(0, max=9, bind="duzey", id="duzey")
        yield ui.Input(bind="port", id="port")  # sayı tutan özniteliğe yazı: sayıya çevrilir
        yield ui.Select(["Elle", "Her gün"], bind="zaman", id="zaman")  # tanımsız: alanın değeriyle oluşur
        yield ui.Checkbox("Sıkıştır", True, bind="sikistir", id="sikistir")
        yield ui.RadioSet("Tam", "Artımlı", bind="mod", id="mod")
        yield ui.Spinbox(3, min=1, max=9, bind="sakla", id="sakla")
        yield ui.TextArea(bind="notlar", id="notlar")
        with Ayar(id="ayar"):
            yield ui.Slider(0, max=1, step=0.1, bind="oran", id="oran")


def test_bind_two_way():
    async def main():
        app = BindApp()
        async with app.run_test() as pilot:
            q = app.query_one
            assert q("#kaynak").value == "C:\\Projeler" and q("#duzey").value == 6  # öznitelik alana gelir
            assert q("#port").value == "8080"
            assert (app.zaman, app.sikistir, app.mod, app.sakla, app.notlar) == ("Elle", True, "Tam", 3, "")
            q("#kaynak").focus()
            await pilot.type("X")
            assert app.kaynak == "C:\\ProjelerX"
            q("#duzey").focus()
            await pilot.press("right")
            assert app.duzey == 7
            q("#port").focus()
            await pilot.press("backspace")
            assert app.port == 808
            await pilot.type("a")  # sayıya çevrilemez: öznitelik eskisinde kalır
            assert app.port == 808 and q("#port").value == "808a"
            app.duzey = 2  # reactive → alan
            app.kaynak = "D:\\"
            app.zaman = "Her gün"  # pencerenin düz özniteliği de iki yönlü
            app.sakla = 8
            app.mod = "Artımlı"
            app.notlar = "bir\niki"
            await pilot.pause()
            assert q("#duzey").value == 2 and q("#kaynak").value == "D:\\" and q("#zaman").value == "Her gün"
            assert q("#sakla").value == 8 and q("#mod").index == 1 and q("#notlar").text == "bir\niki"
            await pilot.click("#sikistir")
            assert app.sikistir is False
            ayar = q("#ayar", Ayar)
            assert q("#oran").value == 0.5
            q("#oran").focus()
            await pilot.press("right")
            assert ayar.oran == 0.6 and not hasattr(type(app), "oran")  # en yakın atada
            ayar.oran = 0.1
            await pilot.pause()
            assert q("#oran").value == 0.1
            field = q("#kaynak")
            field.remove()
            app.kaynak = "E:\\"  # kaldırılan alan artık güncellenmez
            assert field.value == "D:\\" and field._bound_to is None
            try:
                ui.Static("x", bind="y")
            except TypeError:
                pass
            else:
                raise AssertionError("değeri olmayan bileşen bind= almamalı")
            assert not app._errors
    run(main())


# ── sınıfsız uygulama ve düğme kısayolu ──────────────────

def test_classless_app_actions_and_button_keys():
    async def main():
        log = []
        app = ui.App(title="Araç")
        app.ad = "dünya"

        @app.compose
        def arayuz():
            with ui.Form():
                yield ui.Input(label="Ad", bind="ad")
            yield ui.Button("Selamla", selamla, key="f5", variant="primary", id="selamla")
            yield ui.Button("Sıfırla", "sifirla", id="sifirla")  # eylem adı da olur
            yield ui.KeyBar()

        def selamla():
            log.append(f"merhaba {app.ad}")

        @app.action("Sıfırla", key="f6")
        def sifirla(a):
            assert a is app
            app.ad = ""

        @app.action
        def gizli():
            log.append("gizli")

        @app.on(ui.Button.Pressed)
        def basildi(event):
            log.append(f"basıldı {event.button.label}")

        @app.on("mount")
        def acildi():
            log.append("açıldı")

        async with app.run_test() as pilot:
            assert log == ["açıldı"]
            assert app.query_one(ui.Input).value == "dünya" and app.focused is app.query_one(ui.Input)
            await pilot.press("f5")  # odak yazı alanındayken de düğmenin kısayolu çalışır
            assert log[-1] == "merhaba dünya"
            await pilot.press("f6")
            assert app.query_one(ui.Input).value == ""  # düz öznitelik de alana yansır
            shown = [(k, h) for k, h, *_ in app.active_bindings()]
            assert shown[:2] == [("f5", "Selamla"), ("f6", "Sıfırla")] and ("ctrl+q", "çık") in shown
            await pilot.click("#sifirla")
            assert log[-1] == "basıldı Sıfırla"
            assert app.run_action("gizli") and log[-1] == "gizli"
            await pilot.press("ctrl+p")
            assert any(c.label == "Selamla" for c in app.screen.commands)  # düğme kısayolu palette de
            await pilot.press("escape")
            task = asyncio.ensure_future(app.confirm("Emin misin?"))
            await pilot.pause()
            await pilot.press("f5")  # diyalog açıkken alttaki ekranın düğme kısayolu çalışmaz
            assert log[-1] != "merhaba " and log.count("merhaba ") == 0
            await pilot.press("escape")
            await task
            button = app.query_one("#selamla")
            button.remove()
            assert "_button_" not in " ".join(app.screen._actions_map())
            assert not app._errors
    run(main())


# ── akış köprüsü ──────────────────────────────────────────

def test_flow_show_and_widget_fields_in_window():
    def script(s):
        tablo = s.show(ui.Table("Dosya", "Boyut"))
        tablo.add_row("rapor.pdf", "1.2 MB")
        tablo.add_row("foto.png", "3.4 MB")
        sayi = tablo.row_count
        ayar = s.form("Ayarlar", düzey=ui.Slider(6, max=9, label="Sıkıştırma"), zaman=ui.Select(["Elle", "Her gün"]),
                      sakla=ui.Spinbox(5, min=1, max=50), ad="Efe")
        return sayi, ayar

    with Harness(script) as h:
        form = h.prompt(flow_window.FormPrompt)
        entries = [e for e in h.app.transcript.children if isinstance(e, flow_window.ShownEntry)]
        assert len(entries) == 1 and entries[0].widget.row_count == 2
        assert "rapor.pdf" in entries[0].plain()
        rows = form.rows
        assert [type(r.field).__name__ for r in rows] == ["Slider", "Select", "Spinbox", "Input"]
        assert rows[0].label == "Sıkıştırma"
        h.press("right")  # düzey 7
        h.press("tab", "right", "tab", "up", "ctrl+enter")  # Her gün, sakla 6, gönder
        assert h.finish() == (2, {"düzey": 7, "zaman": "Her gün", "sakla": 6, "ad": "Efe"})


def test_flow_show_and_widget_fields_in_terminal():
    def script(s):
        tablo = s.show(ui.Table("Dosya", "Boyut"))
        tablo.add_row("rapor.pdf", "1.2 MB")  # terminalde bileşen doğrudan değişir
        s.show(ui.Static("[bold]not[/]"))
        s.show(ui.Canvas())
        return tablo.row_count, s.form("Ayarlar", düzey=ui.Slider(6, max=9), zaman=ui.Select(["Elle", "Her gün"]),
                                       sıkıştır=ui.Checkbox("Sıkıştır", True))

    result, out, error = run_terminal(script, "12\n2\nh\n")
    assert error is None, error
    assert result == (1, {"düzey": 9, "zaman": "Her gün", "sıkıştır": False})  # 12 → en çok 9
    assert "Dosya" in out and "not" in out and "Canvas pencerede gösterilir" in out


# ── iskelet ve izleyerek çalıştırma ──────────────────────

def test_scaffold_kinds_and_cli():
    with tempfile.TemporaryDirectory() as tmp:
        assert dev._names("Yedek aracı") == ("yedek_aracı", "YedekAracı", "Yedek aracı")
        for kind in dev.KINDS:
            files = dev.create(f"deneme {kind}", kind, tmp)
            for path in files:
                py_compile.compile(str(path), doraise=True)
            assert files[0].name == f"deneme_{kind}.py"
        try:
            dev.create("deneme uygulama", "uygulama", tmp)
        except FileExistsError:
            pass
        else:
            raise AssertionError("dolu klasörün üzerine yazılmamalı")
        env = {**os.environ, "PYTHONPATH": str(ROOT), "SDL_VIDEODRIVER": "dummy"}
        for kind in ("uygulama", "arac"):  # üretilen testler gerçekten geçiyor
            folder = Path(tmp, f"deneme_{kind}")
            proc = subprocess.run([sys.executable, "-X", "utf8", f"test_deneme_{kind}.py"], cwd=folder, env=env,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            assert proc.returncode == 0 and "testler geçti" in proc.stdout, proc.stdout + proc.stderr
        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                assert cli(["yeni", "baska", "--tur", "betik"]) == 0 and Path(tmp, "baska", "baska.py").exists()
                assert cli(["yeni", "x", "--tur", "yok"]) == 2
            assert "termik çalıştır" in out.getvalue()
        finally:
            os.chdir(cwd)


def test_watch_restarts_on_change():
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp, "betik.py")
        script.write_text("import time\nprint('bir', flush=True)\ntime.sleep(2)\n", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "termik", "çalıştır", str(script), "--izle"],
                                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace")
        time.sleep(1.0)
        script.write_text("import time\nprint('iki', flush=True)\ntime.sleep(0.3)\n", encoding="utf-8")
        out, _ = proc.communicate(timeout=30)
        assert proc.returncode == 0, out  # ikinci açılış kendiliğinden bitti: izleme de bitti
        assert "bir" in out and "iki" in out and "betik.py değişti" in out


def test_saved_window_place():
    from termik.app import _saved_place

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, "yer.txt")
        os.environ["TERMIK_IZLE_KONUM"] = str(path)
        try:
            assert _saved_place() is None  # dosya yok
            path.write_text("120 80 900 600", encoding="utf-8")
            assert _saved_place() == (120, 80, 900, 600)
            path.write_text("bozuk", encoding="utf-8")
            assert _saved_place() is None
        finally:
            del os.environ["TERMIK_IZLE_KONUM"]


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
