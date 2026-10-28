"""termik komut satırı: örnekleri açar, ayarları düzenler.

    termik demo [klasör]   bileşen katmanı demosu: çok panelli bir uygulama
    termik akis            akış API'si örneği: script'e birkaç satırla pencere
    termik ayarlar         görünüm ve kip tercihlerini düzenle
    termik ayarlar --yol   ayar dosyasının yerini yaz
    termik --version       sürümü yaz

`python -m termik …` aynı işi görür.
"""

from __future__ import annotations

import os
import sys

from . import __version__, settings


def edit_settings() -> None:
    """Tercihleri akış API'siyle sor; seçilen görünüm hemen uygulanır, onaylanırsa dosyaya yazılır."""
    import termik
    from .theme import DENSITIES, THEMES

    path = settings.config_path()
    saved = settings.read_file(path)
    prefs = settings.preferences()
    termik.setup(title="termik ayarları")
    termik.print(f"[bold]termik ayarları[/]  [faint]{termik.escape(str(path))}[/]")
    termik.print("[dim]Seçtiğin görünüm hemen uygulanır; kaydedersen her termik penceresi onu kullanır.[/]")
    overridden = [name for key in ("theme", "look", "density", "mode")
                  if os.environ.get(name := f"TERMIK_{key.upper()}")]
    if overridden:
        termik.warn(f"{', '.join(overridden)} ortam değişkeni dosyadaki değeri ezer")

    theme = termik.choose("Renk teması", list(THEMES), default=prefs.get("theme", "okyanus"))
    termik.restyle(theme=theme)
    look = termik.choose("Görünüm", {"terminal · keskin köşe, köşeli butonlar": "terminal",
                                     "modern · yuvarlak köşe, kart zemini": "modern"},
                         default=prefs.get("look", "terminal"))
    termik.restyle(look=look)
    density = termik.choose("Yoğunluk", list(DENSITIES), default=prefs.get("density", "rahat"))
    termik.restyle(density=density)
    mode = termik.choose("Script'ler nerede açılsın?", {"pencerede, açılamazsa terminalde": "auto",
                                                        "her zaman pencerede": "window",
                                                        "her zaman terminalde": "terminal"},
                         default=prefs.get("mode", "auto"))

    chosen = {"theme": theme, "look": look, "density": density, "mode": mode}
    termik.table([{"ayar": key, "dosyada": termik.escape(str(saved.get(key, "—"))), "yeni": value}
                  for key, value in chosen.items()])
    if termik.confirm(f"{path} dosyasına kaydedilsin mi?"):
        settings.save(chosen, path)
        termik.ok("Kaydedildi.")
    else:
        termik.warn("Kaydedilmedi; hiçbir şey değişmedi.")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    command, rest = (args[0], args[1:]) if args else ("", [])
    if command in ("", "-h", "--help", "yardım", "yardim"):
        print(__doc__.strip())
        return 0
    if command in ("-V", "--version", "sürüm", "surum"):
        print(f"termik {__version__}")
        return 0
    if command == "demo":
        from .demo import uygulama
        uygulama.main(rest)
        return 0
    if command in ("akis", "akış"):
        from .demo import akis
        akis.main()
        return 0
    if command == "ayarlar":
        if "--yol" in rest:
            print(settings.config_path())
        else:
            edit_settings()
        return 0
    print(f"termik: bilinmeyen komut {command!r}; komutlar için: termik --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
