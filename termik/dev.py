"""Geliştirme araçları: proje iskeleti (`termik yeni`) ve kaydettikçe yeniden açma (`termik çalıştır --izle`).

    termik yeni yedekci                 # bileşenlerle, sınıflı uygulama + testi
    termik yeni donusturucu --tur arac  # sınıf yazmadan küçük araç + testi
    termik yeni rapor --tur betik       # akış API'siyle betik
    termik çalıştır yedekci/yedekci.py --izle
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from string import Template

KINDS = ("uygulama", "arac", "betik")

_APP = Template('''"""$title: termik ile yazılmış bir uygulama.

    termik çalıştır $module.py --izle   # kaydettikçe pencere yeniden açılır
    python test_$module.py              # testler
"""

import termik as ui


class $cls(ui.App):
    TITLE = "$title"
    SIZE = (900, 560)

    ad = ui.reactive("")   # bind="ad" ile alana bağlı: biri değişince öbürü de
    adet = ui.reactive(1)

    def compose(self):
        yield ui.Header("$title", "termik uygulaması")
        with ui.Panel(title="Selamlama"):
            with ui.Form():
                yield ui.Input(label="Ad", bind="ad", placeholder="adın")
                yield ui.Spinbox(label="Kaç kez", bind="adet", min=1, max=5)
        with ui.Row():
            yield ui.Spacer()
            yield ui.Button("Selamla", self.selamla, key="f5", variant="primary")
        yield ui.Log(id="log")
        yield ui.KeyBar()

    def selamla(self):
        for _ in range(self.adet):
            self.query_one("#log", ui.Log).ok(f"Merhaba [bold]{ui.escape(self.ad or 'dünya')}[/]!")


if __name__ == "__main__":
    $cls().run()
''')

_APP_TEST = Template('''"""$title testleri: pencere açmadan sürülür.  python test_$module.py"""

import asyncio

from $module import $cls


async def main():
    app = $cls()
    async with app.run_test() as pilot:
        await pilot.type("Efe")
        await pilot.press("tab", "up", "f5")  # Kaç kez alanına geç, 2 yap, f5 Selamla
        assert app.ad == "Efe" and app.adet == 2
        assert sum("Efe" in line for line in app.query_one("#log").lines) == 2
    print("✓ testler geçti")


asyncio.run(main())
''')

_TOOL = Template('''"""$title: sınıf yazmadan kurulmuş küçük bir termik aracı.

    termik çalıştır $module.py --izle
"""

import termik as ui

app = ui.App(title="$title")
app.dosya = ""        # bind="dosya" ile alana bağlı
app.buyuk_harf = False


@app.compose
def arayuz():
    with ui.Form():
        yield ui.Input(label="Dosya", bind="dosya", placeholder="dosyayı buraya bırak ya da ctrl+o")
        yield ui.Checkbox("Büyük harfe çevir", bind="buyuk_harf")
    with ui.Row():
        yield ui.Spacer()
        yield ui.Button("Satırları say", say, key="f5", variant="primary")
    yield ui.Log(id="log")
    yield ui.KeyBar()


@app.action("Dosya seç", key="ctrl+o")
async def sec():
    yol = await app.ask_open("Dosya seç", filetypes=[("Metin", "*.txt *.md *.py"), ("Tümü", "*.*")])
    if yol:
        app.dosya = str(yol)


def say():
    log = app.query_one("#log", ui.Log)
    try:
        metin = open(app.dosya, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        log.error(f"açılamadı: {ui.escape(str(exc))}")
        return
    if app.buyuk_harf:
        metin = metin.upper()
    log.ok(f"{metin.count(chr(10)) + 1} satır, {len(metin)} karakter")


if __name__ == "__main__":
    app.run()
''')

_TOOL_TEST = Template('''"""$title testleri.  python test_$module.py"""

import asyncio
import tempfile
from pathlib import Path

import termik as ui
from $module import app


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        dosya = Path(tmp, "deneme.txt")
        dosya.write_text("bir\\niki\\nüç", encoding="utf-8")
        async with app.run_test() as pilot:
            await pilot.drop(app.query_one(ui.Input), dosya)  # dosyayı alana bırak
            await pilot.press("f5")
            assert app.dosya == str(dosya)
            assert any("3 satır" in line for line in app.query_one("#log").lines)
    print("✓ testler geçti")


asyncio.run(main())
''')

_SCRIPT = Template('''"""$title: termik'in akış API'siyle yazılmış bir betik.

    termik çalıştır $module.py
Pencere açılamazsa aynı betik terminalde çalışır.
"""

import time

import termik

termik.setup(title="$title")
ad = termik.ask("Adın?", default="dünya")
adet = termik.ask("Kaç adım?", default=20)
if termik.confirm(f"{adet} adım çalıştırılsın mı?"):
    for _ in termik.track(range(adet), "Çalışıyor", unit="adım"):
        time.sleep(0.05)
termik.ok(f"Bitti, [bold]{termik.escape(ad)}[/]!")
''')


def _names(name: str) -> tuple[str, str, str]:
    """Proje adından modül adı, sınıf adı ve başlık: "Yedek aracı" → ("yedek_aracı", "YedekAracı", "Yedek aracı")."""
    module = re.sub(r"\W+", "_", name.strip()).strip("_").lower() or "uygulama"
    if module[0].isdigit():
        module = "u_" + module
    cls = "".join(part[:1].upper() + part[1:] for part in module.split("_") if part) or "Uygulama"
    title = name.strip().replace("_", " ")
    return module, cls, title[:1].upper() + title[1:]


def create(name: str, kind: str = "uygulama", where: str | os.PathLike = ".") -> list[Path]:
    """İskeleti where/<modül>/ klasörüne yaz; yazılan dosyaları döndürür. Klasör doluysa FileExistsError."""
    if kind not in KINDS:
        raise ValueError(f"bilinmeyen tür {kind!r} ({', '.join(KINDS)})")
    module, cls, title = _names(name)
    folder = Path(where) / module
    if folder.exists() and any(folder.iterdir()):
        raise FileExistsError(f"{folder} boş değil; üzerine yazılmadı")
    values = {"module": module, "cls": cls, "title": title}
    files = {"uygulama": [(f"{module}.py", _APP), (f"test_{module}.py", _APP_TEST)],
             "arac": [(f"{module}.py", _TOOL), (f"test_{module}.py", _TOOL_TEST)],
             "betik": [(f"{module}.py", _SCRIPT)]}[kind]
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, template in files:
        path = folder / filename
        path.write_text(template.substitute(values), encoding="utf-8", newline="\n")
        written.append(path)
    return written


# ── izleyerek çalıştırma ──────────────────────────────────

_SKIP = {".git", "__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".mypy_cache"}


def _mtimes(folder: Path) -> dict[Path, float]:
    found = {}
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in _SKIP and not d.startswith(".")]
        for name in files:
            if name.endswith(".py"):
                path = Path(root, name)
                try:
                    found[path] = path.stat().st_mtime
                except OSError:
                    pass
    return found


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def run(path: str, args: list[str] | None = None, *, watch: bool = False, interval: float = 0.4) -> int:
    """Python dosyasını çalıştır. watch=True ise klasördeki .py dosyaları değişince yeniden başlatır;
    pencere bir önceki yerinde ve boyutunda açılır. Pencere kapatılınca izleme de biter."""
    script = Path(path).resolve()
    if not script.is_file():
        print(f"termik: dosya yok: {path}", file=sys.stderr)
        return 2
    command = [sys.executable, str(script), *(args or [])]
    if not watch:
        return subprocess.call(command)
    folder = script.parent
    place = Path(tempfile.gettempdir()) / f"termik-izle-{abs(hash(str(script)))}.txt"
    env = {**os.environ, "TERMIK_IZLE_KONUM": str(place)}
    print(f"▶ {script.name} izleniyor: .py dosyaları değişince yeniden açılır (durdurmak için Ctrl+C)")
    proc: subprocess.Popen | None = None
    try:
        while True:
            seen = _mtimes(folder)
            proc = subprocess.Popen(command, env=env)
            changed: list[Path] = []
            while not changed:
                time.sleep(interval)
                now = _mtimes(folder)
                changed = [p for p, m in now.items() if seen.get(p) != m] + [p for p in seen if p not in now]
                if not changed and proc.poll() is not None:
                    if proc.returncode == 0:  # pencere kapatıldı: izleme de biter
                        return 0
                    print(f"✗ {script.name} hatayla bitti; dosyayı düzeltip kaydedince yeniden açılır")
                    while not changed:  # düzeltilmesini bekle
                        time.sleep(interval)
                        now = _mtimes(folder)
                        changed = [p for p, m in now.items() if seen.get(p) != m]
            _stop(proc)
            names = ", ".join(sorted({p.name for p in changed}))
            print(f"↻ {names} değişti, yeniden açılıyor")
    except KeyboardInterrupt:
        if proc is not None:
            _stop(proc)
        return 130
    finally:
        try:
            place.unlink()
        except OSError:
            pass
