"""termik komut satırı: örnekleri açar, proje iskeleti kurar, ayarları düzenler.

    termik demo [klasör]               bileşen katmanı demosu: çok panelli bir uygulama
    termik akis                        akış API'si örneği: script'e birkaç satırla pencere
    termik yeni AD [--tur TÜR]         proje iskeleti: uygulama (varsayılan) · arac · betik
    termik çalıştır DOSYA.py [--izle]  çalıştır; --izle kaydettikçe yeniden açar
    termik ayarlar                     görünüm, kip ve dosya diyaloğu tercihlerini düzenle
    termik ayarlar --yol               ayar dosyasının yerini yaz
    termik --version                   sürümü yaz

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
    overridden = [name for key in ("theme", "look", "density", "mode", "dialogs")
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
    dialogs = termik.choose("Dosya seçerken hangi diyalog açılsın?",
                            {"işletim sisteminin kendi diyaloğu": "native",
                             "termik'in klavyeyle gezilen gezgini": "builtin"},
                            default=prefs.get("dialogs", "native"))

    chosen = {"theme": theme, "look": look, "density": density, "mode": mode, "dialogs": dialogs}
    termik.table([{"ayar": key, "dosyada": termik.escape(str(saved.get(key, "—"))), "yeni": value}
                  for key, value in chosen.items()])
    if termik.confirm(f"{path} dosyasına kaydedilsin mi?"):
        settings.save(chosen, path)
        termik.ok("Kaydedildi.")
    else:
        termik.warn("Kaydedilmedi; hiçbir şey değişmedi.")


def _new(args: list[str]) -> int:
    from . import dev

    kind = "uygulama"
    if "--tur" in args:
        i = args.index("--tur")
        kind = args[i + 1] if i + 1 < len(args) else ""
        args = args[:i] + args[i + 2:]
    if len(args) != 1 or kind not in dev.KINDS:
        print(f"kullanım: termik yeni AD [--tur {' | '.join(dev.KINDS)}]", file=sys.stderr)
        return 2
    try:
        files = dev.create(args[0], kind)
    except FileExistsError as exc:
        print(f"termik: {exc}", file=sys.stderr)
        return 1
    main_file = files[0]
    print(f"✓ {main_file.parent} oluşturuldu:")
    for path in files:
        print(f"    {path}")
    print(f"Çalıştırmak için:  termik çalıştır {main_file} --izle")
    if len(files) > 1:
        print(f"Testler için:      python {files[1]}")
    return 0


def _run(args: list[str]) -> int:
    from . import dev

    watch = "--izle" in args
    args = [a for a in args if a != "--izle"]
    if not args:
        print("kullanım: termik çalıştır DOSYA.py [--izle] [argümanlar…]", file=sys.stderr)
        return 2
    return dev.run(args[0], args[1:], watch=watch)


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
    if command in ("yeni", "new"):
        return _new(rest)
    if command in ("çalıştır", "calistir", "run"):
        return _run(rest)
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
