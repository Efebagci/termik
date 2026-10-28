"""Akış API'si: script'lere input()/print() kadar kısa kodla pencereli arayüz.

    import termik

    kaynak = termik.ask_path("Kaynak klasör", kind="dir")
    mod = termik.choose("Mod", ["Tam", "Artımlı"])
    if termik.confirm(f"{kaynak} yedeklensin mi?"):
        for dosya in termik.track(dosyalar, "Kopyalanıyor", unit="dosya"):
            kopyala(dosya)
    termik.ok("Bitti")

İlk çağrıda pencere ayrı bir thread'de açılır; script kendi thread'inde çalışmayı sürdürür,
uzun işler sırasında pencere donmaz. Sorular cevaplanana kadar bekler; cevaplanan soru
dökümde tek satırlık özete dönüşür. Script bitince pencere açık kalır (setup(keep_open=False)
ile kapanır); yakalanmayan hata pencerede gösterilir. Pencereyi kapatmak script'te
KeyboardInterrupt doğurur, terminalde Ctrl+C'ye basmak gibi.

Pencere açılamıyorsa (SSH, CI, pygame yok) aynı script terminalde çalışır: sorular satır
satır sorulur, renkler ANSI ile verilir. TERMIK_MODE=terminal ya da TERMIK_MODE=window kipi
zorlar.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, TypeVar

from .. import settings
from ..markup import escape
from ..theme import THEMES, Theme, with_look
from . import capture as _capture
from .common import ICONS, Progress, format_table

__all__ = [
    "Field", "Password", "Progress", "Session", "ask", "ask_path", "choose", "choose_many", "confirm", "error",
    "form", "info", "ok", "print", "progress", "restyle", "rule", "setup", "spinner", "table", "track", "warn",
]

T = TypeVar("T")


class Field:
    """form() alanının ayrıntıları; çoğu zaman gerekmez, form(port=8080) yeter.

        termik.form("Bağlantı",
                    port=termik.Field(8080, label="Port numarası",
                                      validate=lambda p: 0 < p < 65536 or "1–65535 arası olmalı"),
                    mod=termik.Field("Artımlı", choices=["Tam", "Artımlı"]))

    default alanın ilk değeri; type cevabı çevirir (verilmezse default'un türü). choices alanı
    seçim yapar (liste, (etiket, değer) çiftleri ya da sözlük; default bir değer ya da etiket).
    password gizli yazı alanı yapar; validate ask()'taki gibi denetler; label etiketi değiştirir.
    """

    def __init__(self, default: Any = None, *, type: Callable[[str], Any] | None = None, label: str | None = None,
                 choices: Iterable | dict | None = None, password: bool = False,
                 validate: Callable[[Any], Any] | None = None, placeholder: str = "") -> None:
        self.default, self.type, self.label = default, type, label
        self.choices, self.password, self.validate, self.placeholder = choices, password, validate, placeholder


class Password(Field):
    """Gizli yazı alanı: form(parola=termik.Password) ya da form(parola=termik.Password("varsayılan"))."""

    def __init__(self, default: Any = None, **kwargs) -> None:
        super().__init__(default, password=True, **kwargs)


class Session:
    """Bir akış oturumu: döküm penceresi (ya da terminal) ve ona yazan, soru soran metotlar.

    Modül düzeyindeki termik.ask, termik.print… ilk kullanımda kendiliğinden kurulan
    varsayılan oturuma gider; ayrı oturum testlerde ya da gömülü kullanımda gerekir.

    mode: "auto" (pencere; açılamazsa terminal), "window" ya da "terminal". Verilmezse
    kullanıcının tercihine (TERMIK_MODE, ayar dosyası) bakılır. headless=True pencereyi görünmez
    açar (testler için). keep_open=False pencereyi script bitince kapatır; hata olursa yine de açık
    kalır. capture=True (varsayılan) pencere açıkken script'in print(), stderr, logging ve input()
    çağrılarını da pencereye taşır.
    """

    def __init__(self, *, title: str | None = None, theme: str | None = None, look: str | None = None,
                 density: str | None = None, size: tuple[int, int] | None = None, mode: str | None = None,
                 keep_open: bool = True, capture: bool = True, headless: bool = False, **tokens) -> None:
        settings.check_names(theme=theme, look=look, density=density)
        if mode is not None and str(mode).strip().lower() not in settings.MODES:
            raise ValueError(f"bilinmeyen kip: {mode!r} (auto, window ya da terminal)")
        self.title = title or _script_name()
        self.theme, self.look, self.density = theme, look, density
        self.size = size
        self.mode = mode
        self.keep_open = keep_open
        self.capture = capture
        self.headless = headless
        self.tokens = tokens
        self._backend = None
        self._opening = False  # pencere açılırken yakalanan yazılar oturumu yeniden açmaya kalkmasın
        self._lock = threading.Lock()

    @property
    def started(self) -> bool:
        return self._backend is not None

    @property
    def kind(self) -> str | None:
        """Açıldıysa "window" ya da "terminal"."""
        return None if self._backend is None else self._backend.kind

    def _io(self):
        backend = self._backend
        if backend is None:
            with self._lock:
                if self._backend is None:
                    self._opening = True
                    try:
                        self._backend = _open(self)
                    finally:
                        self._opening = False
                    if self.capture and self._backend.kind == "window":
                        _capture.install(self)
                backend = self._backend
        return backend

    def close(self) -> None:
        """Pencereyi şimdi kapat (terminal kipinde bir şey yapmaz)."""
        if self._backend is not None:
            self._backend.close()

    def _style(self) -> Theme:
        """Oturumun geçerli teması: koddaki değerler, yoksa kullanıcının tercihleri, yoksa varsayılanlar."""
        prefs = settings.preferences()
        return with_look(THEMES[self.theme or prefs.get("theme", "okyanus")], self.look or prefs.get("look", "terminal"),
                         density=self.density or prefs.get("density"), **{**prefs["tokens"], **self.tokens})

    def restyle(self, theme: str | None = None, *, look: str | None = None, density: str | None = None,
                **tokens) -> None:
        """Görünümü çalışırken değiştir: termik.restyle(theme="neon", bar="segment")."""
        settings.check_names(theme=theme, look=look, density=density)
        self.theme, self.look, self.density = theme or self.theme, look or self.look, density or self.density
        self.tokens.update(tokens)
        if self._backend is not None:
            self._backend.restyle(theme, look=look, density=density, **tokens)

    # ── çıktı ─────────────────────────────────────────────

    def print(self, *objects: Any, sep: str = " ", end: str = "\n", markup: bool = True) -> None:
        """print() gibi yaz. Yazılar markup'tır ("[green]✓[/] tamam"); diğer nesneler olduğu
        gibi yazılır, markup sayılmaz. markup=False yazıları da olduğu gibi yazar."""
        self._io().write(escape(sep).join(_text(o, markup) for o in objects) + escape(end))

    def ok(self, *objects: Any, sep: str = " ") -> None:
        """✓ simgeli satır."""
        self._status("ok", objects, sep)

    def info(self, *objects: Any, sep: str = " ") -> None:
        """• simgeli satır."""
        self._status("info", objects, sep)

    def warn(self, *objects: Any, sep: str = " ") -> None:
        """⚠ simgeli satır."""
        self._status("warn", objects, sep)

    def error(self, *objects: Any, sep: str = " ") -> None:
        """✗ simgeli satır."""
        self._status("error", objects, sep)

    def _status(self, kind: str, objects: tuple, sep: str) -> None:
        icon, color = ICONS[kind]
        self._io().write(f"[{color}]{icon}[/] " + escape(sep).join(_text(o, True) for o in objects) + "\n")

    def rule(self, title: str = "") -> None:
        """Ayraç çizgisi: ── Başlık ──────────"""
        self._io().rule(title)

    def table(self, rows: Iterable, headers: Iterable | None = None) -> None:
        """Hizalı tablo yaz; rows dizi ya da sözlük listesi (başlıklar anahtarlardan gelir)."""
        self._io().table(format_table(rows, headers))

    # ── sorular ───────────────────────────────────────────

    def ask(self, label: str, *, default: Any = None, placeholder: str = "", password: bool = False,
            type: Callable[[str], Any] | None = None, validate: Callable[[Any], Any] | None = None) -> Any:
        """Yazı sor. type= cevabı çevirir (int, float, Path…), validate= denetler.

        default verilirse alan onunla dolu gelir; boş bırakılırsa default döner. type verilmezse
        default'un türü kullanılır (default=8080 → int). Çevirme ya da doğrulama başarısızsa
        hata sorunun altında gösterilir ve soru tekrarlanır. validate False ya da hata mesajı
        döndürerek veya ValueError fırlatarak cevabı reddeder.
        """
        convert = type or (default.__class__ if default is not None and not isinstance(default, (str, bool))
                           else str)
        prompt = self._io().prompt("ask", label, value="" if default is None else str(default),
                                   placeholder=placeholder, password=password)
        while True:
            raw = prompt.wait()
            try:
                value = default if raw == "" and default is not None else _convert(raw, convert)
                _check(value, validate)
            except ValueError as exc:
                prompt.reject(str(exc) or "geçersiz değer")
                continue
            shown = str(value)
            prompt.accept("••••••" if password else escape(shown) if shown else "[faint](boş)[/]")
            return value

    def ask_path(self, label: str, *, default: str | os.PathLike | None = None, must_exist: bool = True,
                 kind: str | None = None, validate: Callable[[Path], Any] | None = None) -> Path:
        """Dosya ya da klasör yolu sor; Path döndürür. Pencerede Tab tamamlar, Ctrl+O ağaçtan seçtirir.

        kind="dir" yalnızca klasör, kind="file" yalnızca dosya kabul eder. must_exist=False
        henüz olmayan yollara (ör. yeni hedef klasör) izin verir. "~" ve ortam değişkenleri
        açılır, kopyalanan yolların tırnakları atılır.
        """
        if kind not in (None, "file", "dir"):
            raise ValueError(f"kind 'file', 'dir' ya da None olmalı: {kind!r}")
        prompt = self._io().prompt("path", label, value="" if default is None else str(default), kind=kind)
        while True:
            text = prompt.wait().strip().strip('"').strip()
            if not text and default is not None:
                text = str(default)
            try:
                if not text:
                    raise ValueError("bir yol girin")
                path = Path(os.path.expandvars(os.path.expanduser(text)))
                if must_exist and not path.exists():
                    raise ValueError(f"bulunamadı: {path}")
                if kind == "dir" and path.exists() and not path.is_dir():
                    raise ValueError("bu bir klasör değil")
                if kind == "file" and path.exists() and not path.is_file():
                    raise ValueError("bu bir dosya değil")
                _check(path, validate)
            except ValueError as exc:
                prompt.reject(str(exc) or "geçersiz yol")
                continue
            prompt.accept(escape(str(path)))
            return path

    def choose(self, label: str, options: Iterable[T] | dict[str, T], *, default: Any = None) -> T:
        """Listeden bir seçenek seçtir; seçeneğin kendisini döndürür.

        options yazı listesi, (etiket, değer) çiftleri ya da {etiket: değer} sözlüğü olabilir;
        etiketler düz yazıdır. Pencerede yazdıkça liste bulanık aramayla süzülür. default bir
        değer ya da etiket olabilir; verilmezse ilk seçenek.
        """
        items = _options(options)
        if not items:
            raise ValueError("choose(): seçenek listesi boş")
        index = 0 if default is None else _index_of(items, default)
        prompt = self._io().prompt("choose", label, options=[name for name, _ in items], index=index)
        i = prompt.wait()
        prompt.accept(escape(items[i][0]))
        return items[i][1]

    def choose_many(self, label: str, options: Iterable[T] | dict[str, T], *, default: Iterable = (),
                    min: int = 0, max: int | None = None) -> list[T]:
        """Birden çok seçenek seçtir; seçilenlerin listesini (sırası korunarak) döndürür.

        Pencerede space işaretler, ctrl+a hepsini işaretler ya da kaldırır, Enter onaylar.
        min/max seçim sayısını sınırlar. default önceden işaretli değerler ya da etiketler.
        """
        items = _options(options)
        if not items:
            raise ValueError("choose_many(): seçenek listesi boş")
        selected = sorted({_index_of(items, d) for d in default})
        prompt = self._io().prompt("many", label, options=[name for name, _ in items], selected=selected)
        while True:
            picked = sorted(prompt.wait())
            if len(picked) < min:
                prompt.reject(f"en az {min} seçim yapın")
            elif max is not None and len(picked) > max:
                prompt.reject(f"en çok {max} seçim yapılabilir")
            else:
                break
        prompt.accept(", ".join(escape(items[i][0]) for i in picked) or "[faint]seçim yok[/]")
        return [items[i][1] for i in picked]

    def confirm(self, label: str, *, default: bool = True, yes: str = "Evet", no: str = "Hayır") -> bool:
        """Evet/hayır sor. Pencerede ←/→ seçer, Enter onaylar; baş harfler (e/h) ve y/n doğrudan cevaplar."""
        prompt = self._io().prompt("confirm", label, default=bool(default), yes=yes, no=no)
        answer = bool(prompt.wait())
        prompt.accept(escape(yes if answer else no))
        return answer

    def form(self, title: str = "", /, **fields: Any) -> dict[str, Any]:
        """Birkaç alanı tek seferde sor; {ad: değer} döndürür.

            ayar = termik.form("Bağlantı", sunucu="localhost", port=8080, mod=["Tam", "Artımlı"],
                               sıkıştır=True, parola=termik.Password)

        Değerin türü alanı belirler: yazı ya da sayı dolu gelen yazı alanı olur (sayı türü korunur,
        type= gibi), str/int/float/Path türü boş alan, liste ya da sözlük seçim, bool onay kutusu,
        termik.Password gizli yazı. Ayrıntı (etiket, doğrulama, seçimde varsayılan) için
        termik.Field. Etiketler adlardan çıkar: hedef_klasör → "Hedef klasör". Pencerede Tab
        alanlar arasında gezer, ⏎ sonraki alana geçer (sonuncusunda gönderir), ctrl+⏎ hemen gönderir.
        Hatalı alanlar işaretlenir ve form yeniden sorulur.
        """
        specs = [_form_field(name, value) for name, value in fields.items()]
        if not specs:
            raise ValueError("form(): en az bir alan gerekli")
        prompt = self._io().prompt("form", title, fields=[spec.ui() for spec in specs])
        while True:
            raw = prompt.wait()
            values, errors = {}, {}
            for spec in specs:
                try:
                    values[spec.name] = spec.parse(raw[spec.name])
                except ValueError as exc:
                    errors[spec.name] = str(exc) or "geçersiz değer"
            if not errors:
                break
            prompt.reject(errors)
        prompt.accept({spec.name: spec.summary(raw[spec.name], values[spec.name]) for spec in specs})
        return values

    # ── ilerleme ─────────────────────────────────────────

    def track(self, iterable: Iterable[T], label: str = "", *, total: float | None = None,
              unit: str = "öğe") -> Iterator[T]:
        """Döngüyü ilerleme çubuğuyla sar: `for f in termik.track(dosyalar, "Kopyalanıyor"): …`.

        Toplam len() ile bulunur; bulunamazsa total= verilmedikçe sayaç belirsiz ilerler.
        Döngü break ile biterse satır "durduruldu" olarak kapanır.
        """
        if total is None:
            try:
                total = len(iterable)  # type: ignore[arg-type]
            except TypeError:
                pass
        bar = Progress(self, label, total=total, unit=unit)
        try:
            for item in iterable:
                yield item
                bar.advance()
        except GeneratorExit:
            bar.finish("stopped")
            raise
        except BaseException as exc:
            bar.finish("error", exc)
            raise
        else:
            bar.finish("ok")

    def progress(self, label: str = "", *, total: float | None = None, unit: str = "öğe") -> Progress:
        """Elle ilerletilen çubuk; with ile kullanılır, p.advance(n) ile ilerler. unit="B" bayt gösterir."""
        return Progress(self, label, total=total, unit=unit)

    def spinner(self, label: str = "") -> Progress:
        """Dönen işaret ve geçen süre: `with termik.spinner("İndiriliyor"): …`. sp.update(yazı) açıklama ekler."""
        return Progress(self, label, kind="spinner")


# ── yardımcılar ───────────────────────────────────────────

def _text(obj: Any, markup: bool) -> str:
    return obj if markup and isinstance(obj, str) else escape(str(obj))


def _options(options) -> list[tuple[str, Any]]:
    if isinstance(options, dict):
        return [(str(k), v) for k, v in options.items()]
    out = []
    for item in options:
        if isinstance(item, tuple) and len(item) == 2:
            out.append((str(item[0]), item[1]))
        else:
            out.append((str(item), item))
    return out


def _index_of(items: list[tuple[str, Any]], wanted: Any) -> int:
    for i, (_, value) in enumerate(items):
        try:
            if value == wanted:
                return i
        except Exception:  # == ile karşılaştırılamayan değerler (ör. diziler)
            continue
    for i, (name, _) in enumerate(items):
        if name == wanted:
            return i
    raise ValueError(f"seçeneklerde yok: {wanted!r}")


def _convert(raw: str, convert: Callable[[str], Any]) -> Any:
    if convert is str:
        return raw
    if convert is int:
        try:
            return int(raw.strip())
        except ValueError:
            raise ValueError("bir tam sayı girin") from None
    if convert is float:
        text = raw.strip()
        if text.count(",") == 1 and "." not in text:  # ondalık virgül: 3,5
            text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
            raise ValueError("bir sayı girin") from None
    if isinstance(convert, type) and issubclass(convert, os.PathLike):
        text = raw.strip().strip('"')
        if not text:
            raise ValueError("bir yol girin")
        return convert(os.path.expandvars(os.path.expanduser(text)))
    try:
        return convert(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(str(exc) or "geçersiz değer") from None


def _check(value: Any, validate: Callable[[Any], Any] | None) -> None:
    if validate is None:
        return
    verdict = validate(value)
    if verdict is False:
        raise ValueError("geçersiz değer")
    if isinstance(verdict, str) and verdict:
        raise ValueError(verdict)


def _label_of(name: str) -> str:
    """Alan adından etiket: hedef_klasör → "Hedef klasör", isim → "İsim" (Türkçe büyük harf)."""
    text = name.replace("_", " ").strip()
    return {"i": "İ", "ı": "I"}.get(text[:1], text[:1].upper()) + text[1:]


class _FormField:
    """form()'daki bir alan: türü (yazı, onay kutusu, seçim), arayüze giden tanımı ve cevabın çevrilmesi."""

    def __init__(self, name: str, field: Field) -> None:
        self.name = name
        self.label = field.label or escape(_label_of(name))
        self.field = field
        default = field.default
        if field.choices is not None:
            self.kind = "choice"
            self.items = _options(field.choices)
            if not self.items:
                raise ValueError(f"form(): {name} alanının seçenekleri boş")
            self.index = 0 if default is None else _index_of(self.items, default)
        elif isinstance(default, bool) or field.type is bool:
            self.kind = "check"
        else:
            self.kind = "text"
            self.convert = field.type or (default.__class__ if default is not None and not isinstance(default, str)
                                          else str)

    def ui(self) -> dict[str, Any]:
        spec: dict[str, Any] = {"name": self.name, "label": self.label, "kind": self.kind,
                                "password": self.field.password, "placeholder": self.field.placeholder}
        if self.kind == "choice":
            spec.update(value=self.index, options=[label for label, _ in self.items])
        elif self.kind == "check":
            spec["value"] = bool(self.field.default)
        else:
            spec["value"] = "" if self.field.default is None else str(self.field.default)
        return spec

    def parse(self, raw: Any) -> Any:
        if self.kind == "choice":
            value = self.items[raw][1]
        elif self.kind == "check":
            value = bool(raw)
        elif raw == "" and self.field.default is not None:
            value = self.field.default
        else:
            value = _convert(raw, self.convert)
        _check(value, self.field.validate)
        return value

    def summary(self, raw: Any, value: Any) -> str:
        if self.kind == "choice":
            return escape(self.items[raw][0])
        if self.kind == "check":
            return "evet" if value else "hayır"
        if self.field.password:
            return "••••••"
        return escape(str(value)) if str(value) else "[faint](boş)[/]"


def _form_field(name: str, value: Any) -> _FormField:
    """form(ad=değer) değerinden alan: Field, Field sınıfı (termik.Password), seçenekler, tür ya da varsayılan."""
    if isinstance(value, type) and issubclass(value, Field):
        value = value()
    if not isinstance(value, Field):
        if isinstance(value, (list, tuple, dict)):
            value = Field(choices=value)
        elif isinstance(value, type):
            value = Field(type=value)
        else:
            value = Field(value)
    return _FormField(name, value)


def _script_name() -> str:
    main = sys.modules.get("__main__")
    path = getattr(main, "__file__", None) or (sys.argv[0] if sys.argv else "")
    name = os.path.splitext(os.path.basename(path or ""))[0]
    return name if name and not name.startswith("-") else "termik"  # python -c'de "-c" olmasın


def _no_window() -> str | None:
    """Pencerenin hiç denenmeyeceği durumlar."""
    if sys.platform == "darwin":
        return "macOS'ta pencere ana thread'de açılmalı; bu kip henüz yok"
    if sys.platform.startswith(("linux", "freebsd")) and not (os.environ.get("DISPLAY")
                                                             or os.environ.get("WAYLAND_DISPLAY")):
        return "görüntü sunucusu yok"
    return None


def _note(message: str) -> None:
    if sys.stderr is not None:
        try:
            sys.stderr.write(message + "\n")
        except (OSError, ValueError):
            pass


def _open(session: Session):
    """Arka ucu seç ve aç: pencere, olmazsa terminal."""
    if session.mode:
        mode = settings.MODES[session.mode.strip().lower()]
    else:  # TERMIK_MODE ya da ayar dosyasındaki mode
        mode = settings.preferences().get("mode", "auto")
    if mode != "terminal" and (mode == "window" or session.headless or _no_window() is None):
        try:
            from .window import WindowBackend
            return WindowBackend(session)
        except Exception as exc:
            if mode == "window":
                raise
            if isinstance(exc, ImportError):
                _note("termik: pygame-ce kurulu değil, terminalde devam ediliyor (pip install pygame-ce)")
            else:
                _note(f"termik: pencere açılamadı ({type(exc).__name__}: {exc}), terminalde devam ediliyor")
    from .terminal import TerminalBackend
    return TerminalBackend(session)


# ── varsayılan oturum ─────────────────────────────────────

_default: Session | None = None
_default_lock = threading.Lock()


def _session() -> Session:
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = Session()
    return _default


def setup(*, title: str | None = None, theme: str | None = None, look: str | None = None,
          density: str | None = None, size: tuple[int, int] | None = None, mode: str | None = None,
          keep_open: bool = True, capture: bool = True, **tokens) -> None:
    """Varsayılan oturumu ayarla; ilk çıktıdan ya da sorudan önce çağrılmalı.

        termik.setup(title="Yedekleme", theme="orman", density="dengeli", bar="segment")

    title pencere başlığı (varsayılan: script'in adı); theme, look, density ve biçim
    belirteçleri bileşen katmanındakilerle aynı. size pencere boyutu (piksel, ölçek 1.0'da).
    capture=True (varsayılan) script'in kendi print(), stderr, logging ve input() çağrılarını
    pencereye taşır; böylece eski bir script'e pencere vermek için bu tek satır yeter. Pencere ilk
    yazıda ya da ilk soruda açılır. capture=False bunu kapatır.
    """
    global _default
    with _default_lock:
        if _default is not None and _default.started:
            raise RuntimeError("termik.setup() pencere açılmadan, ilk çıktıdan önce çağrılmalı")
        if _default is not None:
            _capture.uninstall(_default)
        _default = Session(title=title, theme=theme, look=look, density=density, size=size, mode=mode,
                           keep_open=keep_open, capture=capture, **tokens)
        if capture:
            _capture.install(_default)


def restyle(theme: str | None = None, *, look: str | None = None, density: str | None = None, **tokens) -> None:
    """Görünümü çalışırken değiştir: termik.restyle(theme="neon", density="ferah")."""
    _session().restyle(theme, look=look, density=density, **tokens)


def print(*objects: Any, sep: str = " ", end: str = "\n", markup: bool = True) -> None:  # noqa: A001
    """print() gibi yaz; yazılar markup'tır: termik.print("[green]✓[/] Bitti")."""
    _session().print(*objects, sep=sep, end=end, markup=markup)


def ok(*objects: Any, sep: str = " ") -> None:
    """✓ simgeli satır."""
    _session().ok(*objects, sep=sep)


def info(*objects: Any, sep: str = " ") -> None:
    """• simgeli satır."""
    _session().info(*objects, sep=sep)


def warn(*objects: Any, sep: str = " ") -> None:
    """⚠ simgeli satır."""
    _session().warn(*objects, sep=sep)


def error(*objects: Any, sep: str = " ") -> None:
    """✗ simgeli satır."""
    _session().error(*objects, sep=sep)


def rule(title: str = "") -> None:
    """Ayraç çizgisi: ── Başlık ──────────"""
    _session().rule(title)


def table(rows: Iterable, headers: Iterable | None = None) -> None:
    """Hizalı tablo; rows dizi ya da sözlük listesi."""
    _session().table(rows, headers)


def ask(label: str, *, default: Any = None, placeholder: str = "", password: bool = False,
        type: Callable[[str], Any] | None = None, validate: Callable[[Any], Any] | None = None) -> Any:
    """Yazı sor: termik.ask("Port", type=int, default=8080). Ayrıntı: Session.ask."""
    return _session().ask(label, default=default, placeholder=placeholder, password=password, type=type,
                          validate=validate)


def ask_path(label: str, *, default: str | os.PathLike | None = None, must_exist: bool = True,
             kind: str | None = None, validate: Callable[[Path], Any] | None = None) -> Path:
    """Yol sor: termik.ask_path("Kaynak", kind="dir"). Tab tamamlar, Ctrl+O ağaçtan seçtirir."""
    return _session().ask_path(label, default=default, must_exist=must_exist, kind=kind, validate=validate)


def choose(label: str, options: Iterable[T] | dict[str, T], *, default: Any = None) -> T:
    """Listeden seçtir: termik.choose("Mod", ["Tam", "Artımlı"]). Yazdıkça süzülür."""
    return _session().choose(label, options, default=default)


def choose_many(label: str, options: Iterable[T] | dict[str, T], *, default: Iterable = (),
                min: int = 0, max: int | None = None) -> list[T]:
    """Çoklu seçim: termik.choose_many("Uzantılar", [".jpg", ".png"], min=1)."""
    return _session().choose_many(label, options, default=default, min=min, max=max)


def confirm(label: str, *, default: bool = True, yes: str = "Evet", no: str = "Hayır") -> bool:
    """Evet/hayır sor: if termik.confirm("Silinsin mi?", default=False): …"""
    return _session().confirm(label, default=default, yes=yes, no=no)


def form(title: str = "", /, **fields: Any) -> dict[str, Any]:
    """Birkaç alanı tek seferde sor: termik.form("Bağlantı", sunucu="localhost", port=8080). Ayrıntı: Session.form."""
    return _session().form(title, **fields)


def track(iterable: Iterable[T], label: str = "", *, total: float | None = None,
          unit: str = "öğe") -> Iterator[T]:
    """Döngüyü ilerleme çubuğuyla sar: for f in termik.track(dosyalar, "Kopyalanıyor"): …"""
    return _session().track(iterable, label, total=total, unit=unit)


def progress(label: str = "", *, total: float | None = None, unit: str = "öğe") -> Progress:
    """Elle ilerletilen çubuk: with termik.progress("İndiriliyor", total=n, unit="B") as p: p.advance(k)"""
    return _session().progress(label, total=total, unit=unit)


def spinner(label: str = "") -> Progress:
    """Dönen işaret: with termik.spinner("Bağlanılıyor"): …"""
    return _session().spinner(label)
