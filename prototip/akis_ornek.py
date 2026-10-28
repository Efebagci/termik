"""Akış API'si örneği: yedekleme betiği.

    python prototip/akis_ornek.py                        # pencerede
    TERMIK_MODE=terminal python prototip/akis_ornek.py   # aynı betik terminalde

Dosyalara dokunmaz: kopyalama yalnızca canlandırılır.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import termik  # noqa: E402

termik.setup(title="Yedekleme")

termik.print("[bold]Yedekleme[/] [faint]· termik akış API'si örneği[/]")
termik.print("[dim]Kaynak klasör taranır, seçilen türdeki dosyalar hedefe kopyalanmış gibi yapılır.[/]")
termik.rule("Ayarlar")

kaynak = termik.ask_path("Kaynak klasör", kind="dir", default=Path.cwd())
hedef = termik.ask_path("Hedef klasör", kind="dir", must_exist=False, default=Path.home() / "Yedek")
mod = termik.choose("Mod", ["Tam", "Artımlı", "Diferansiyel"], default="Artımlı")
türler = termik.choose_many("Dosya türleri", [".py", ".md", ".txt", ".json", ".toml", ".png"],
                            default=[".py", ".md"], min=1)

with termik.spinner("Taranıyor") as tarama:
    dosyalar = []
    for kök, klasörler, adlar in os.walk(kaynak):
        klasörler[:] = [k for k in klasörler if not k.startswith((".", "__"))]
        dosyalar += [Path(kök, ad) for ad in adlar if Path(ad).suffix in türler]
        tarama.update(f"{len(dosyalar)} dosya")
toplam = sum(f.stat().st_size for f in dosyalar)
termik.info(f"{len(dosyalar)} dosya bulundu, toplam {toplam / 1024:.0f} KB")

if not dosyalar:
    termik.warn("Seçilen türde dosya yok.")
elif termik.confirm(f"{len(dosyalar)} dosya {hedef} klasörüne yedeklensin mi?"):
    for dosya in termik.track(dosyalar, "Kopyalanıyor", unit="dosya"):
        time.sleep(0.03)  # gerçek betikte: shutil.copy2(dosya, hedef / dosya.relative_to(kaynak))
    termik.rule("En büyük dosyalar")
    büyükler = sorted(dosyalar, key=lambda f: f.stat().st_size, reverse=True)[:5]
    termik.table([{"dosya": termik.escape(str(f.relative_to(kaynak))), "KB": round(f.stat().st_size / 1024, 1)}
                  for f in büyükler])
    termik.ok(f"Bitti: {len(dosyalar)} dosya, [bold]{mod}[/] yedek")
else:
    termik.warn("Vazgeçildi, hiçbir şey kopyalanmadı.")
