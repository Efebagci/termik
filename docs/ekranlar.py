"""README ekran görüntülerini (docs/ekran) koddan yeniden üretir: görünüm değişince çalıştırılır.

    python docs/ekranlar.py                 # hepsi
    python docs/ekranlar.py akis grafik     # yalnızca bu gruplar

Gruplar: demo, akis, bilesen, grafik, kolay, pencere. Pencere açılmaz (SDL'in sahte sürücüsü);
kullanıcının ayar dosyası okunmaz, görüntüler varsayılan görünümle (okyanus · terminal · rahat) alınır.
Bileşen galerisi (docs/galeri/) ayrıca docs/galeri.py ile üretilir.
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "ekran"
sys.path.insert(0, str(ROOT))
os.environ["TERMIK_CONFIG"] = str(Path(tempfile.gettempdir()) / "termik-ekran-yok" / "ayarlar.toml")
for _name in [n for n in os.environ if n.startswith("TERMIK_") and n != "TERMIK_CONFIG"]:
    del os.environ[_name]

import termik as ui  # noqa: E402  (pygame'den önce: karşılama satırını sustursun)
import pygame  # noqa: E402
from termik.filedialog import FileBrowser  # noqa: E402
from termik.flow import Session  # noqa: E402
from termik.icon import prompt_icon  # noqa: E402


def shot(pilot, name: str, window=None) -> None:
    pilot.snapshot(str(OUT / f"{name}.png"), window=window)
    print(f"✓ {name}")


# ── demo: çok panelli örnek uygulama ──────────────────────

async def demo() -> None:
    from termik.demo import uygulama

    app = uygulama.BackupApp(ROOT, theme="okyanus", density="rahat", save_state=False)
    async with app.run_test(size=(1280, 800)) as pilot:
        notes = app.query_one("#notes", ui.TextArea)
        notes.focus()
        await pilot.type("Cuma akşamı tam yedek al.")
        await pilot.press("enter")
        await pilot.type("Fotoğraflar klasörü büyüdü; artımlı yedek yeterli olabilir.")
        app.query_one("#side", ui.Tabs).select(0)
        app.query_one("#schedule", ui.Select).index = 1
        app.query_one("#dst").focus()
        await pilot.press("f5")
        await pilot.wait_until(lambda: app.query_one("#bar").progress > 0.45, timeout=30)
        shot(pilot, "demo-calisiyor")
        await pilot.press("escape")
        shot(pilot, "demo-onay")
        await pilot.press("escape")
        await pilot.wait_until(lambda: not app.running, timeout=60)
        shot(pilot, "demo-bitti")
        await pilot.press("alt+d")
        shot(pilot, "demo-menu")
        await pilot.press("escape", "ctrl+p")
        await pilot.type("tema")
        shot(pilot, "demo-palet")
        await pilot.press("escape", "f1")
        await pilot.press("tab", "pagedown")
        shot(pilot, "demo-yardim")
        await pilot.press("escape")
        app.open_settings()
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause(0.1)
        shot(pilot, "pencere-ayarlar", window=app._settings)


# ── akış API'si: termik akis betiğinin adımları ───────────

def _akis_script(s: Session) -> None:
    """termik/demo/akis.py ile aynı akış (oturum açıkça verilir)."""
    s.print("[bold]Yedekleme[/] [faint]· termik akış API'si örneği[/]")
    s.print("[dim]Kaynak klasör taranır, seçilen türdeki dosyalar hedefe kopyalanmış gibi yapılır.[/]")
    s.rule("Ayarlar")
    kaynak = s.ask_path("Kaynak klasör", kind="dir", default=ROOT)
    ayar = s.form("Yedekleme",
                  hedef=ui.Field(Path("C:/Users/efeba/Yedek"), label="Hedef klasör"),
                  mod=ui.Field("Artımlı", choices=["Tam", "Artımlı", "Diferansiyel"]),
                  sıkıştır=True)
    türler = s.choose_many("Dosya türleri", [".py", ".md", ".txt", ".json", ".toml", ".png"],
                           default=[".py", ".md"], min=1)
    with s.spinner("Taranıyor") as tarama:
        dosyalar = []
        for kök, klasörler, adlar in os.walk(kaynak):
            klasörler[:] = [k for k in klasörler if not k.startswith((".", "__")) and k not in ("dist", "build")]
            dosyalar += [Path(kök, ad) for ad in adlar if Path(ad).suffix in türler]
            tarama.update(f"{len(dosyalar)} dosya")
    toplam = sum(f.stat().st_size for f in dosyalar)
    s.info(f"{len(dosyalar)} dosya bulundu, toplam {toplam / 1024:.0f} KB")
    if s.confirm(f"{len(dosyalar)} dosya {ayar['hedef']} klasörüne yedeklensin mi?"):
        for _ in s.track(dosyalar, "Kopyalanıyor", unit="dosya"):
            time.sleep(0.04)
        s.rule("En büyük dosyalar")
        büyükler = sorted(dosyalar, key=lambda f: f.stat().st_size, reverse=True)[:5]
        s.table([{"dosya": ui.escape(str(f.relative_to(kaynak))), "KB": round(f.stat().st_size / 1024, 1)}
                 for f in büyükler])
        s.ok(f"Bitti: {len(dosyalar)} dosya, [bold]{ayar['mod']}[/] yedek" + (", sıkıştırılmış" if ayar["sıkıştır"] else ""))


class _Flow:
    """Akış betiğini ayrı thread'de çalıştırır, görünmez pencereyi Pilot ile sürer (testlerdeki gibi)."""

    def __init__(self, script) -> None:
        self.session = Session(mode="window", headless=True, capture=False, title="Yedekleme", size=(980, 660))
        self.thread = threading.Thread(target=script, args=(self.session,), daemon=True)
        self.thread.start()
        while self.session._backend is None:
            time.sleep(0.01)
        self.app = self.session._backend.app
        self.pilot = ui.Pilot(self.app)

    def run(self, coro, timeout: float = 30.0):
        return asyncio.run_coroutine_threadsafe(coro, self.app._loop).result(timeout)

    def until(self, predicate, timeout: float = 20.0) -> None:
        self.run(self.pilot.wait_until(predicate, timeout), timeout + 2)

    def press(self, *keys: str) -> None:
        self.run(self.pilot.press(*keys))

    def prompt(self, label: str) -> None:
        self.until(lambda: (p := self.app.active_prompt) is not None and p.listening and label in str(p.label))

    def shot(self, name: str) -> None:
        async def take() -> None:
            await self.pilot.pause(0.15)
            shot(self.pilot, name)
        self.run(take())


def akis() -> None:
    flow = _Flow(_akis_script)
    try:
        flow.prompt("Kaynak klasör")
        flow.press("ctrl+o")
        flow.until(lambda: isinstance(flow.app.screen, FileBrowser))
        flow.press("down", "down", "right")
        flow.shot("akis-gozat")
        flow.press("escape")
        flow.press("enter")
        flow.prompt("Yedekleme")
        flow.shot("akis-form")
        flow.press("ctrl+enter")
        flow.prompt("Dosya türleri")
        flow.press("down", "down", "space", "down")
        flow.shot("akis-secim")
        flow.press("enter")
        flow.prompt("yedeklensin")
        flow.press("enter")
        flow.until(lambda: any(getattr(getattr(e, "progress", None), "fraction", 0) and e.progress.fraction > 0.45
                               for e in flow.app.transcript.children))
        flow.shot("akis-ilerleme")
        flow.thread.join(60)
        flow.until(lambda: flow.app.outcome is not None)
        flow.shot("akis-bitti")
    finally:
        flow.session.close()


# ── bileşen vitrinleri ────────────────────────────────────

class _Liste(ui.Static):
    can_focus = True

    def context_menu(self, event):
        return [ui.MenuItem("&Kopyala", lambda: None, key="ctrl+c"), ui.MenuItem("&Yeniden adlandır", lambda: None, key="f2"),
                None, ui.MenuItem("&Sil", lambda: None, key="delete")]


class _Vitrin(ui.App):
    SIZE = (1000, 560)

    def compose(self):
        yield ui.MenuBar(
            ui.Menu("&Dosya", [ui.MenuItem("&Yeni", "new"), ui.MenuItem("&Aç…", "open_file"), ui.MenuItem("&Kaydet", "save"),
                               None, ui.MenuItem("Ç&ık", "app.quit")]),
            ui.Menu("Dü&zen", [ui.MenuItem("&Geri al", lambda: None, key="ctrl+z"),
                               ui.MenuItem("Satır &numaraları", lambda: None, checked=True),
                               ui.MenuItem("Sözcük &kaydır", lambda: None, checked=False)]),
            ui.Menu("&Görünüm", [ui.MenuItem("&Tema değiştir", "app.command_palette")]),
            ui.Menu("&Yardım", [ui.MenuItem("&Hakkında", lambda: None)]),
        )
        with ui.Row(gap=2):
            with ui.Panel(title="Ayarlar", width=60):
                with ui.Tabs():
                    with ui.Tab("Genel"):
                        with ui.Form():
                            yield ui.Input("Efe", label="Ad")
                            yield ui.Select(["Tam", "Artımlı", "Diferansiyel"], index=1, label="Mod", id="mod",
                                            tooltip="Yedekleme türü: [bold]artımlı[/] yalnızca değişenleri kopyalar")
                            yield ui.Slider(6, min=0, max=9, label="Sıkıştırma")
                            yield ui.Slider(40, min=0, max=100, step=5, format="{:.0f} MB/sn", label="Hız sınırı")
                            with ui.Row(label="Seçenekler", gap=2):
                                yield ui.Checkbox("Doğrula", True)
                                yield ui.Checkbox("Ayrıntılı günlük")
                    with ui.Tab("Gelişmiş"):
                        yield ui.Checkbox("Ayrıntılı günlük")
                    with ui.Tab("Hakkında"):
                        yield ui.Static("termik")
            with ui.Panel(title="Dosyalar"):
                yield _Liste("rapor.pdf\nnotlar.md\nfoto.png  [faint](sağ tık: menü)[/]", id="liste")
        yield ui.KeyBar()

    @ui.action("Yeni", key="ctrl+n")
    def new(self) -> None:
        pass

    @ui.action("Aç…", key="ctrl+o")
    def open_file(self) -> None:
        pass

    @ui.action("Kaydet", key="ctrl+s")
    def save(self) -> None:
        pass


def _sample_image(path: Path) -> Path:
    w, h = 320, 200
    img = pygame.Surface((w, h))
    for y in range(h):
        t = y / h
        img.fill((int(30 + 200 * t), int(60 + 90 * t), int(140 - 60 * t)), (0, y, w, 1))
    pygame.draw.circle(img, (255, 210, 90), (230, 70), 34)
    pygame.draw.polygon(img, (40, 70, 60), [(0, 200), (90, 90), (170, 200)])
    pygame.draw.polygon(img, (30, 50, 45), [(110, 200), (220, 110), (320, 200)])
    pygame.image.save(img, str(path))
    return path


class _Kalan(ui.App):
    SIZE = (1180, 640)

    def __init__(self, picture: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.picture = picture

    def compose(self):
        with ui.Split(sizes=[52, "1fr"], id="split"):
            with ui.Panel(title="Resim", gap=0.5):
                yield ui.Image(self.picture, height=11, caption="ornek-resim.png · 320×200")
                with ui.Form():
                    yield ui.Spinbox(12, min=1, max=99, label="Adet", id="adet")
                    yield ui.Spinbox(0.5, min=0, max=1, step=0.05, label="Oran")
            with ui.Split(direction="column", sizes=["2fr", "1fr"]):
                with ui.Panel(title="Canvas"):
                    yield ui.Canvas(id="canvas", height="1fr")
                with ui.Panel(title="Notlar"):
                    yield ui.Static("Ayraçları fareyle sürükle; çift tık başa döndürür.")
        yield ui.KeyBar()

    def on_mount(self):
        c = self.query_one("#canvas", ui.Canvas)
        c.rect(1, 0.5, 14, 4, fill="raised", color="border")
        c.text(2.5, 1.5, "[bold accent]Canvas[/]")
        c.lines([(18 + i * 0.5, 4 - 2.5 * math.sin(i / 4)) for i in range(70)], color="secondary", width=2)
        c.circle(8, 8, 3, fill="tertiary")
        c.polygon([(20, 11), (26, 7), (32, 11)], fill="yellow")
        c.line(0, 12.5, 50, 12.5, color="dim")
        self.query_one("#adet").focus()


async def bilesen() -> None:
    for name, keys, tokens in (("bilesen-menu", ("alt+d",), {}),
                               ("bilesen-select", ("tab", "enter"), {}),
                               ("bilesen-sagtik", None, {}),
                               ("bilesen-modern-menu2", ("alt+z",), {"look": "modern"})):
        app = _Vitrin(theme="okyanus", **tokens)
        async with app.run_test(size=_Vitrin.SIZE) as pilot:
            if name == "bilesen-select":
                app.query_one("#mod").focus()
                await pilot.press("enter")
            elif keys is None:
                liste = app.query_one("#liste")
                await pilot.click(liste, offset=(60, 40), button=3)
            else:
                await pilot.press(*keys)
            shot(pilot, name)
    with tempfile.TemporaryDirectory() as tmp:
        picture = _sample_image(Path(tmp, "ornek-resim.png"))
        for name, tokens in (("bilesen-kalan", {}), ("bilesen-kalan-bloklar", {"image": "blocks", "field": "filled",
                                                                                 "split": "hidden"})):
            app = _Kalan(picture, theme="okyanus", **tokens)
            async with app.run_test(size=_Kalan.SIZE) as pilot:
                split = app.query_one("#split", ui.Split)
                await pilot.hover(split, offset=(split._seps[0].centerx - split.region.x, 40))
                shot(pilot, name)


# ── grafikler ─────────────────────────────────────────────

class _Grafikler(ui.App):
    SIZE = (1200, 700)

    def compose(self):
        cpu = [50 + 18 * math.sin(i / 3) + 8 * math.sin(i / 1.3) for i in range(60)]
        ram = [40 + 6 * math.sin(i / 9) + i * 0.15 for i in range(60)]
        with ui.Split(direction="column"):
            with ui.Split():
                with ui.Panel(title="Canlı"):
                    yield ui.Chart({"cpu": cpu, "bellek": ram}, title="Kullanım %", y_min=0, y_max=100,
                                   x=[f"{i}s" for i in range(60)], height="1fr", id="canli")
                with ui.Panel(title="Alan"):
                    yield ui.Chart([3, 4, 3.5, 5, 4.6, 6, 7.2, 6.5, 8, 9.4, 11, 13.5],
                                   x=["pzt", "sal", "çar", "per", "cum", "cmt", "paz", "pzt", "sal", "çar", "per", "cum"],
                                   kind="area", title="Günlük yedek (GB)", height="1fr")
            with ui.Split():
                with ui.Panel(title="Çubuk"):
                    yield ui.Chart({"Ocak": 12, "Şubat": 30, "Mart": 22, "Nisan": 41, "Mayıs": 36}, kind="bar",
                                   title="Aylık dosya (bin)", height="1fr")
                with ui.Panel(title="Yan yana çubuk"):
                    yield ui.Chart({"tam": [7, 5, 4, 8], "artımlı": [9, 12, 11, 15]}, x=["H1", "H2", "H3", "H4"],
                                   kind="bar", title="Yedek süresi (dk)", height="1fr")


async def grafik() -> None:
    for name, tokens in (("grafik", {}), ("grafik-braille", {"chart": "braille"})):
        app = _Grafikler(theme="okyanus", **tokens)
        async with app.run_test(size=_Grafikler.SIZE) as pilot:
            chart = app.query_one("#canli", ui.Chart)
            await pilot.hover(chart, offset=(chart.region.w * 3 // 5, chart.region.h // 2))
            await pilot.pause(0.1)
            shot(pilot, name)


# ── sınıf yazmadan kurulmuş araç ──────────────────────────

async def kolay() -> None:
    app = ui.App(title="Ayarlar", theme="okyanus")
    app.kaynak = "C:\\ProjelerX"
    app.duzey = 6

    @app.compose
    def arayuz():
        with ui.Panel(title="Ayarlar"):
            with ui.Form():
                yield ui.Input(label="Kaynak", bind="kaynak", id="kaynak")
                yield ui.Slider(max=9, label="Düzey", bind="duzey")
                yield ui.Select(["Elle", "Her gün 22:00", "Her hafta"], label="Zamanlama")
                yield ui.Spinbox(5, min=1, max=50, label="Sakla")
                with ui.Row(label="Seçenekler", gap=2):
                    yield ui.Checkbox("Sıkıştır", True)
                    yield ui.Checkbox("Şifrele")
                yield ui.RadioSet("Tam", "Artımlı", label="Mod")
                yield ui.TextArea(label="Not", rows=2, placeholder="isteğe bağlı")
        with ui.Row(gap=2):
            yield ui.Spacer()
            yield ui.Button("Sıfırla", lambda: None, key="f6")
            yield ui.Button("Dönüştür", lambda: None, key="f5", variant="primary")
        yield ui.KeyBar()

    async with app.run_test(size=(900, 560)) as pilot:
        app.query_one("#kaynak").focus()
        await pilot.press("end")
        shot(pilot, "kolay-arac")


# ── pencereler: ayarlar penceresi demoda; termik gezgini ve simgeler ──

async def pencere() -> None:
    from termik.demo import uygulama

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp, "Belgeler")
        (root / "raporlar").mkdir(parents=True)
        (root / "resimler").mkdir()
        for name, size in (("notlar.txt", 1840), ("taslak.txt", 7300), ("bütçe.md", 2950), ("foto.png", 91000)):
            (root / name).write_bytes(b"x" * size)
        app = uygulama.BackupApp(str(root), theme="okyanus", density="rahat", dialogs="builtin", save_state=False)
        async with app.run_test(size=(1100, 640)) as pilot:
            task = asyncio.ensure_future(app.ask_save("Notları kaydet", folder=root, name="notlar",
                                                     filetypes=[("Metin", "*.txt")]))
            await pilot.pause()
            app.screen.tree.focus()
            await pilot.press("down", "down", "right", "down")
            await pilot.pause(0.1)
            shot(pilot, "pencere-gezgin")
            await pilot.press("escape")
            await task
    size, gap = 64, 28
    names = list(ui.THEMES)[:6]
    img = pygame.Surface((len(names) * (size + gap) + gap, size + 2 * gap), pygame.SRCALPHA)
    img.fill((0, 0, 0, 0))
    for i, name in enumerate(names):
        img.blit(prompt_icon(ui.THEMES[name], size), (gap + i * (size + gap), gap))
    pygame.image.save(img, str(OUT / "pencere-simgeleri.png"))
    print("✓ pencere-simgeleri")


GROUPS = {"demo": demo, "akis": akis, "bilesen": bilesen, "grafik": grafik, "kolay": kolay, "pencere": pencere}


def main(argv: list[str]) -> None:
    wanted = argv or list(GROUPS)
    for name in wanted:
        fn = GROUPS[name]
        result = fn()
        if asyncio.iscoroutine(result):
            asyncio.run(result)


if __name__ == "__main__":
    main(sys.argv[1:])
