"""Bileşen galerisini üret: her örneğin kodunu çalıştırır, görüntüsünü kırpar, docs/bilesenler.md'yi yazar.

    python docs/galeri.py

Örneklerin kodu yalnızca burada durur; sayfadaki kod ile görüntü böylece hep birbirini tutar.
Pencere açılmaz (SDL'in sahte sürücüsü); kullanıcının ayar dosyası kullanılmaz.
"""

from __future__ import annotations

import asyncio
import math
import os
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

DOCS = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS.parent))
os.environ["TERMIK_CONFIG"] = str(Path(tempfile.gettempdir()) / "termik-galeri-yok.toml")

import termik as ui  # noqa: E402
import pygame  # noqa: E402

OUT = DOCS / "galeri"

# (dosya adı, başlık, açıklama, kod) — kod compose() içinde çalışır
EXAMPLES: list[tuple[str, str, str, str]] = [
    ("yazi", "Static, Label", "Markup yazı. `Static` genişliğe göre satır kaydırır, `Label` tek satırda kalıp `…` ile kısalır.", '''
yield ui.Static("Markup: [bold]kalın[/], [accent]vurgu[/], [green]✓ tamam[/], [red]✗ hata[/]")
yield ui.Label("Tek satır, sığmazsa kısalır: " + "çok " * 20, width=48)
'''),
    ("buton", "Button", "İkinci argüman fonksiyon ya da eylem adı; `key=` kısayolu ekranın her yerinde çalışır ve "
     "kısayol satırında görünür.", '''
with ui.Row(gap=2):
    yield ui.Button("Vazgeç", "app.quit")
    yield ui.Button("Kaydet", kaydet, key="ctrl+s", variant="primary")
'''),
    ("form", "Form, Input, Select, Slider, Spinbox", "Form etiketleri solda hizalı bir sütunda çizer; "
     "`bind=` alanı uygulamanın özniteliğine bağlar.", '''
with ui.Form():
    yield ui.Input(label="Kaynak", bind="kaynak", placeholder="klasör")
    yield ui.Input("gizli", label="Parola", password=True)
    yield ui.Select(["Elle", "Her gün 22:00", "Her hafta"], label="Zamanlama")
    yield ui.Slider(6, max=9, label="Düzey")
    yield ui.Spinbox(5, min=1, max=50, label="Sakla")
'''),
    ("secim", "Checkbox, RadioSet", "Onay kutusu ve tek seçimli grup; Space, ←/→ ve tıkla değişir.", '''
with ui.Form():
    with ui.Row(label="Seçenekler", gap=2):
        yield ui.Checkbox("Sıkıştır", True)
        yield ui.Checkbox("Şifrele")
    yield ui.RadioSet("Tam", "Artımlı", "Fark", label="Mod")
'''),
    ("liste", "OptionList", "Yazdıkça bulanık süzülen seçenek listesi; `multi=True` ile çoklu seçim.", '''
yield ui.OptionList(["Avrupa (Frankfurt)", "Avrupa (İstanbul)", "Asya (Tokyo)", "Amerika (Virginia)"], rows=4)
'''),
    ("textarea", "TextArea", "Çok satırlı yazı: seçim, pano, geri al, satır numaraları.", '''
yield ui.TextArea("Cuma akşamı tam yedek al.\\nFotoğraflar klasörü büyüdü.", line_numbers=True, rows=3)
'''),
    ("sekme", "Tabs, Tab", "Sekmeli kapsayıcı; ctrl+tab ya da başlığa tık.", '''
with ui.Tabs():
    with ui.Tab("Genel"):
        yield ui.Static("Genel ayarlar burada.")
    with ui.Tab("Gelişmiş"):
        yield ui.Static("…")
    with ui.Tab("Hakkında"):
        yield ui.Static("termik")
'''),
    ("panel", "Panel", "Başlıklı çerçeve; içindekileri alt alta dizer, odak içindeyken çerçevesi yanar.", '''
with ui.Panel(title="Yedekleme", info="tam yedek"):
    yield ui.Static("348 dosya · 6,3 MB")
'''),
    ("ilerleme", "ProgressBar, Sparkline", "İlerleme çubuğu ve akan değerler için mini grafik.", '''
yield ui.ProgressBar(0.62)
yield ui.Sparkline([3, 5, 2, 8, 6, 9, 4, 7, 10, 6, 8, 12], label="CPU", value_format="{:.0f} %")
'''),
    ("tablo", "Table", "Sabit başlıklı tablo; başlığa tıklayınca sıralar.", '''
tablo = ui.Table("Dosya", ("Boyut", 10, "right"), height=5)
tablo.add_row("rapor.pdf", "1,2 MB")
tablo.add_row("foto.png", "3,4 MB")
tablo.add_row("notlar.md", "12 KB")
yield tablo
'''),
    ("agac", "Tree, DirectoryTree", "Açılır kapanır ağaç; klasör ağacı alt klasörleri ilk açılışta okur.", '''
yield ui.DirectoryTree(".", height=6)
'''),
    ("gunluk", "Log", "Kayan kayıt: info, ok, warn, error; saat damgası.", '''
log = ui.Log(timestamps=True, height=3)
log.info("taranıyor: C:/Projeler")
log.ok("348 dosya · 6,3 MB")
log.warn("2 dosya atlandı")
yield log
'''),
    ("resim", "Image", "Resim (dosya ya da Surface); kutuya oranı korunarak sığar.", '''
yield ui.Image("manzara.png", height=8, caption="manzara.png · 320×200")
'''),
    ("grafik", "Chart", "Çizgi, alan ve çubuk grafiği; canlı veri için `append`.", '''
with ui.Row(gap=2, height=11):
    yield ui.Chart({"cpu": [30, 52, 41, 63, 48, 70, 55], "bellek": [50, 52, 55, 53, 58, 57, 60]},
                   title="Kullanım %", y_min=0, y_max=100)
    yield ui.Chart({"Ocak": 12, "Şubat": 30, "Mart": 22, "Nisan": 41}, kind="bar", title="Dosya (bin)")
'''),
    ("canvas", "Canvas", "Serbest çizim; çağrılar saklanır, birim karakter ve satır.", '''
c = ui.Canvas(height=7)
c.rect(1, 0.5, 14, 3, fill="raised", color="border")
c.text(2.5, 1.3, "[bold accent]Canvas[/]")
c.lines([(18 + i / 2, 3 - 2 * math.sin(i / 3)) for i in range(50)], color="green", width=2)
c.circle(8, 5.5, 1.4, fill="accent2")
c.arc(50, 3.5, 2.6, 90 - 360 * 0.7, 90, color="yellow", width=5)
yield c
'''),
    ("split", "Split", "Bölünebilir kapsayıcı; ayraç fareyle sürüklenir, oranlar korunur.", '''
with ui.Split(sizes=[24, "1fr"], height=5):
    yield ui.Panel(ui.Static("sol"), title="Dosyalar")
    yield ui.Panel(ui.Static("sağ"), title="Önizleme")
'''),
    ("menu", "MenuBar, Menu", "Menü çubuğu: Alt+harf ya da F10 açar.", '''
yield ui.MenuBar(ui.Menu("&Dosya", [ui.MenuItem("&Kaydet", kaydet, key="ctrl+s")]),
                 ui.Menu("&Görünüm", []), ui.Menu("&Yardım", []))
'''),
    ("cubuklar", "Header, KeyBar, StatusBar", "Başlık, geçerli kısayollar ve durum çubuğu.", '''
yield ui.Header("termik", "bileşen katmanı", clock=False)
yield ui.KeyBar()
yield ui.StatusBar(mode="HAZIR", left="termik demo", right="okyanus · rahat")
'''),
]


def _sample_image(path: Path) -> None:
    w, h = 320, 200
    img = pygame.Surface((w, h))
    for y in range(h):
        t = y / h
        img.fill((int(30 + 200 * t), int(60 + 90 * t), int(140 - 60 * t)), (0, y, w, 1))
    pygame.draw.circle(img, (255, 210, 90), (230, 70), 34)
    pygame.draw.polygon(img, (40, 70, 60), [(0, 200), (90, 90), (170, 200)])
    pygame.draw.polygon(img, (30, 50, 45), [(110, 200), (220, 110), (320, 200)])
    pygame.image.save(img, str(path))


def _sample_folder(root: Path) -> None:
    (root / "belgeler").mkdir()
    (root / "fotoğraflar").mkdir()
    for name, size in (("rapor.pdf", 1240), ("notlar.md", 380), ("bütçe.xlsx", 9100)):
        (root / name).write_bytes(b"x" * size)


async def _shoot(name: str, code: str) -> None:
    namespace = {"ui": ui, "math": math, "kaydet": lambda: None}
    exec("def compose(self):\n" + textwrap.indent(code.strip("\n"), "    ") + "\n", namespace)
    app = type("Galeri", (ui.App,), {"compose": namespace["compose"], "SIZE": (760, 900)})(theme="okyanus")
    async with app.run_test(size=(760, 900)) as pilot:
        await pilot.pause()
        app.set_focus(None)  # odak halkası görüntüye girmesin
        await pilot.pause()
        kids = [w for w in app.screen.children if w.display]
        area = kids[0].region.unionall([w.region for w in kids[1:]]) if kids else app.screen.region
        surface = app.native.get_surface()
        crop = area.inflate(app.painter.ch * 2, app.painter.row).clip(surface.get_rect())
        app._render()
        pygame.image.save(surface.subsurface(crop).copy(), str(OUT / f"{name}.png"))
        assert not app._errors, (name, app._errors)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    pygame.init()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp, "Projeler")
        work.mkdir()
        _sample_image(work / "manzara.png")
        _sample_folder(work)
        cwd = os.getcwd()
        os.chdir(work)  # örneklerdeki "manzara.png" ve "." buraya bakar
        try:
            for name, _, _, code in EXAMPLES:
                asyncio.run(_shoot(name, code))
                print(f"✓ {name}")
        finally:
            os.chdir(cwd)
    page = ["# Bileşen galerisi", "",
            "Her görüntünün altındaki kod onu üreten kodun kendisidir (`compose()` içinde). Sayfa ",
            "`python docs/galeri.py` ile yeniden üretilir.", ""]
    page += [f"- [{title}](#{name})" for name, title, _, _ in EXAMPLES] + [""]
    for name, title, about, code in EXAMPLES:
        page += [f'<a id="{name}"></a>', "", f"## {title}", "", about, "", f"![{title}](galeri/{name}.png)", "",
                 "```python", code.strip("\n"), "```", ""]
    page += ["Bütün bileşenler, seçenekleri ve kavramlar için [başvuru (README)](https://github.com/Efebagci/termik#readme).", ""]
    (DOCS / "bilesenler.md").write_text("\n".join(page), encoding="utf-8", newline="\n")
    print(f"✓ {DOCS / 'bilesenler.md'}")


if __name__ == "__main__":
    main()
