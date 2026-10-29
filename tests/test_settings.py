"""Ayarlar ve komut satırı testleri: ayar dosyası, ortam değişkenleri, öncelik sırası, `termik` komutu.

    python tests/test_settings.py
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

import _ortam  # noqa: E402,F401  (kullanıcının tercihlerinden yalıt)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import termik  # noqa: E402
from termik import settings  # noqa: E402
from termik.__main__ import main as cli  # noqa: E402
from termik.flow import Session  # noqa: E402
from termik.theme import THEMES  # noqa: E402


@contextlib.contextmanager
def preferences(text: str = "", **env: str):
    """Geçici bir ayar dosyası ve TERMIK_* ortam değişkenleriyle çalış; çıkınca eski hale dön."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, "ayarlar.toml")
        if text:
            path.write_text(text, encoding="utf-8")
        names = {"TERMIK_CONFIG": str(path), **{f"TERMIK_{k.upper()}": v for k, v in env.items()}}
        saved = {name: os.environ.get(name) for name in names}
        os.environ.update(names)
        settings._warned.clear()
        try:
            yield path
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


@contextlib.contextmanager
def captured(stdin: str = ""):
    """stdin/stdout/stderr'i yakala: (out, err) StringIO'ları verir."""
    saved = sys.stdin, sys.stdout, sys.stderr
    out, err = io.StringIO(), io.StringIO()
    sys.stdin, sys.stdout, sys.stderr = io.StringIO(stdin), out, err
    try:
        yield out, err
    finally:
        sys.stdin, sys.stdout, sys.stderr = saved


def test_file_values_are_checked_and_converted():
    text = ('theme = "orman"\ndensity = "dengeli"\nbar = "segment"\naccent = "#ff8800"\nfont_size = 17\n'
            'panel_fill = true\nradius = "çok"\nbilinmeyen = 1\nlook = "eski"\n')
    with preferences(text), captured() as (_, err):
        prefs = settings.preferences()
    assert prefs["theme"] == "orman" and prefs["density"] == "dengeli" and "look" not in prefs
    assert prefs["tokens"] == {"bar": "segment", "accent": (255, 136, 0), "font_size": 17, "panel_fill": True}
    warnings = err.getvalue()
    for part in ("radius = 'çok'", "bilinmeyen ayar 'bilinmeyen'", "look = 'eski'", "terminal, modern"):
        assert part in warnings, part


def test_component_tokens_are_checked():
    with preferences('tabs = "folder"\nslider = "x"\nselect = "arrows"\n'), captured() as (_, err):
        prefs = settings.preferences()
    assert prefs["tokens"] == {"tabs": "folder", "select": "arrows"} and "bar, line, value" in err.getvalue()


def test_environment_overrides_file():
    with preferences('theme = "orman"\nbar = "segment"\nmode = "window"\n', theme="neon", bar="ascii",
                     mode="tty", panel_fill="evet"):
        prefs = settings.preferences()
    assert prefs["theme"] == "neon" and prefs["mode"] == "terminal"
    assert prefs["tokens"] == {"bar": "ascii", "panel_fill": True}


def test_dialogs_preference():
    with preferences('dialogs = "yerleşik"\n'):
        assert settings.preferences()["dialogs"] == "builtin"
        assert termik.App().dialogs == "builtin" and termik.App(dialogs="native").dialogs == "native"
    with preferences(dialogs="sistem"):
        assert termik.App().dialogs == "native"
    with preferences('dialogs = "pencere"\n'), captured() as (_, err):
        assert "dialogs" not in settings.preferences()
    assert "native, builtin" in err.getvalue()
    assert termik.App().dialogs == "native"  # varsayılan: işletim sisteminin diyaloğu
    try:
        termik.App(dialogs="x")
    except ValueError:
        pass
    else:
        raise AssertionError("bilinmeyen diyalog türü kabul edilmemeli")


def test_broken_file_is_ignored_with_a_warning():
    with preferences('theme = "orman\n'), captured() as (_, err):
        assert settings.preferences() == {"tokens": {}}
    assert "okunamadı" in err.getvalue()


def test_save_keeps_comments_and_other_keys():
    with preferences('# benim ayarlarım\ntheme = "orman"  # koyu\nbar = "segment"\n\n[ileride]\nx = 1\n') as path:
        settings.save({"theme": "neon", "density": "ferah", "bar": None, "accent": (1, 2, 3)})
        text = path.read_text(encoding="utf-8")
        assert text.splitlines() == ["# benim ayarlarım", 'theme = "neon"', "", 'density = "ferah"',
                                     'accent = "#010203"', "[ileride]", "x = 1"]
        with captured() as (_, err):
            prefs = settings.preferences()
        assert prefs["theme"] == "neon" and prefs["tokens"] == {"accent": (1, 2, 3)}
        assert "bilinmeyen ayar 'ileride'" in err.getvalue()
    with tempfile.TemporaryDirectory() as tmp:  # dosya yoksa açıklamalı başlıkla oluşur
        path = settings.save({"theme": "mono", "font": "C:\\Fonts\\a b.ttf"}, Path(tmp, "yeni", "ayarlar.toml"))
        text = path.read_text(encoding="utf-8")
        assert text.startswith("# termik ayarları") and 'font = "C:\\\\Fonts\\\\a b.ttf"' in text
        assert settings.read_file(path)["font"] == "C:\\Fonts\\a b.ttf"


def test_app_uses_preferences_but_code_wins():
    with preferences('theme = "orman"\ndensity = "sıkı"\nbar = "ascii"\n'):
        app = termik.App()
        assert app.theme.name == "orman" and app.density == "sıkı" and app.theme.bar == "ascii"
        app = termik.App(theme="neon", bar="line")
        assert app.theme.name == "neon" and app.density == "sıkı" and app.theme.bar == "line"
    for bad in (dict(theme="yok"), dict(look="eski"), dict(density="dar")):
        try:
            termik.App(**bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"kabul edilmemeliydi: {bad}")
    assert termik.App().theme.name == "okyanus"  # ayar yoksa varsayılan
    assert termik.with_look(THEMES["mono"], accent="#102030").accent == (16, 32, 48)


def test_session_mode_and_colors_from_preferences():
    with preferences('mode = "terminal"\ntheme = "günbatımı"\n'), captured() as (out, _):
        s = Session()
        s.print("x")
        assert s.kind == "terminal" and out.getvalue() == "x\n"
        assert s._style().name == "günbatımı" and s._backend.theme.accent == THEMES["günbatımı"].accent
        s.restyle(theme="neon")
        assert s._backend.theme.name == "neon"


def test_restyle_live_window():
    from test_flow import Harness

    with preferences('theme = "orman"\n'):
        with Harness(lambda s: (s.print("x"), s.restyle(theme="neon", density="ferah", bar="ascii"))) as h:
            h.done()
            h.until(lambda: h.app.theme.name == "neon")
            assert h.app.density == "ferah" and h.app.theme.bar == "ascii"


def test_cli_help_version_and_path():
    with captured() as (out, _):
        assert cli([]) == 0 and cli(["--version"]) == 0 and cli(["ayarlar", "--yol"]) == 0
    text = out.getvalue()
    assert "termik demo" in text and f"termik {termik.__version__}" in text
    assert text.strip().endswith(str(settings.config_path()))
    with captured() as (_, err):
        assert cli(["uç"]) == 2
    assert "bilinmeyen komut" in err.getvalue()


def test_cli_edit_settings_in_terminal():
    import termik.flow as flow

    with preferences('theme = "orman"\n# yorum kalır\n', mode="terminal") as path:
        answers = "neon\n2\n\n3\n2\ne\n"  # tema, görünüm (modern), yoğunluk (varsayılan), kip, diyalog, kaydet
        try:
            with captured(answers) as (out, _):
                assert cli(["ayarlar"]) == 0
        finally:
            flow._default = None
        text = path.read_text(encoding="utf-8")
        assert 'theme = "neon"' in text and 'look = "modern"' in text and 'density = "rahat"' in text
        assert 'mode = "terminal"' in text and 'dialogs = "builtin"' in text and "# yorum kalır" in text
        assert "✓ Kaydedildi." in out.getvalue()


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
