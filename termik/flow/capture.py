"""Script'in kendi çıktısını ve girdisini pencereye taşır.

print() ve sys.stdout/sys.stderr'e yazılanlar dökümde de görünür; konsol varsa oraya da yazılmaya
devam eder (pythonw'da yalnızca pencerede). logging kayıtları dökümde simgeli satır olur (⚠ disk
dolu); std akışlara yazan logging işleyicileri kendi biçimleriyle konsola yazmayı sürdürür, yanlarına
pencereye yazan bir eş takılır. input() ve getpass.getpass() pencerede soru olarak sorulur. Pencere kapanınca ya da oturum terminale düşünce her şey eski haline döner.
Süreçte tek yakalama olur; setup(capture=False) onu kapatır.
"""

from __future__ import annotations

import builtins
import contextlib
import getpass
import io
import logging
import re
import sys
import threading

from ..markup import escape

# renk ve imleç kaçışları (CSI) ile başlık/bağlantı kaçışları (OSC): dökümde anlamsız
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_local = threading.local()  # muted: bu thread'in yazdıkları yalnızca eski akışa gider
_lock = threading.Lock()
_active: Capture | None = None


def install(session) -> None:
    """Oturum için yakalamayı aç; süreçte zaten bir yakalama varsa bir şey yapmaz.

    Oturum henüz açılmadıysa pencere ilk yazıda ya da ilk input()'ta açılır.
    """
    global _active
    with _lock:
        if _active is None:
            _active = Capture(session)
            _active.start()


def uninstall(session) -> None:
    global _active
    with _lock:
        if _active is not None and _active.session is session:
            _active.stop()
            _active = None


def active() -> Capture | None:
    return _active


@contextlib.contextmanager
def muted():
    """Bu blokta bu thread'in yazdıkları yalnızca eski akışa gider (excepthook izi çift basılmasın)."""
    old = getattr(_local, "muted", False)
    _local.muted = True
    try:
        yield
    finally:
        _local.muted = old


def _markup(text: str, style: str | None) -> str:
    """Ham yazıyı döküm markup'ına çevir: kaçışları at, köşeli parantezleri koru, \\r ve \\n'yi bırak."""
    text = _ANSI.sub("", text.replace("\r\n", "\n"))
    out = []
    for part in re.split(r"([\r\n])", text):
        if part in ("\r", "\n", ""):
            out.append(part)
        else:
            out.append(f"[{style}]{escape(part)}[/]" if style else escape(part))
    return "".join(out)


class _Stream(io.TextIOBase):
    """sys.stdout/sys.stderr yerine geçen akış: yazılanı eski akışa da, dökümde de yazar."""

    def __init__(self, capture: Capture, original, style: str | None) -> None:
        super().__init__()
        self.capture, self.original, self.style = capture, original, style

    @property
    def encoding(self) -> str:
        return getattr(self.original, "encoding", None) or "utf-8"

    @property
    def errors(self) -> str:
        return getattr(self.original, "errors", None) or "strict"

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False  # kütüphaneler renk kaçışı ve imleç hareketi göndermesin

    def fileno(self) -> int:
        if self.original is None:
            raise io.UnsupportedOperation("fileno")
        return self.original.fileno()

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError(f"write() argument must be str, not {type(text).__name__}")
        if self.original is not None:
            try:
                self.original.write(text)
            except (OSError, ValueError):
                pass
        self.capture.emit(_markup(text, self.style))
        return len(text)

    def flush(self) -> None:
        if self.original is not None:
            try:
                self.original.flush()
            except (OSError, ValueError):
                pass


class _Null:
    """Konsolu olmayan süreçte (pythonw) logging işleyicilerinin yazacağı boş akış."""

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        pass


class _LogHandler(logging.Handler):
    """logging kayıtlarını dökümde simgeli satır olarak gösterir. console=True ise (lastResort yerine
    geçtiğinde) varsayılan biçimde konsola da yazar."""

    LEVELS = ((logging.CRITICAL, "✗", "bold red"), (logging.ERROR, "✗", "red"), (logging.WARNING, "⚠", "yellow"),
              (logging.INFO, "•", "blue"), (logging.NOTSET, "·", "faint"))

    def __init__(self, capture: Capture, *, console: bool = False, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self.capture, self.console = capture, console

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _, icon, color = next(level for level in self.LEVELS if record.levelno >= level[0])
            name = "" if record.name == "root" else f"[faint]{escape(record.name)}:[/] "
            text = f"[{color}]{icon}[/] {name}{escape(record.getMessage())}\n"
            if record.exc_info:
                trace = logging.Formatter().formatException(record.exc_info)
                text += "".join(f"[faint]{escape(line)}[/]\n" for line in trace.splitlines())
            self.capture.emit(text)
            original = self.capture.saved["stderr"]
            if self.console and original is not None:
                original.write(logging.Formatter().format(record) + "\n")  # varsayılan lastResort'un yazdığı
        except Exception:
            self.handleError(record)


def _loggers() -> list[logging.Logger]:
    return [logging.getLogger(), *(lg for lg in logging.Logger.manager.loggerDict.values()
                                   if isinstance(lg, logging.Logger))]


class Capture:
    """Bir oturumun yakalaması: takılan akışlar ve kancalar, sökülürken geri konacak eski halleri."""

    def __init__(self, session) -> None:
        self.session = session
        self.saved: dict = {}
        self.twins: list[tuple[logging.Logger, _LogHandler]] = []

    def start(self) -> None:
        self.saved = {"stdout": sys.stdout, "stderr": sys.stderr, "input": builtins.input,
                      "getpass": getpass.getpass, "last_resort": logging.lastResort,
                      "basic_config": logging.basicConfig}
        sys.stdout = _Stream(self, sys.stdout, None)
        sys.stderr = _Stream(self, sys.stderr, "red")
        builtins.input = self.input
        getpass.getpass = self.getpass
        logging.lastResort = _LogHandler(self, console=True, level=logging.WARNING)  # yapılandırılmamışlar
        logging.basicConfig = self._basic_config  # logging.warning() de kendiliğinden bunu çağırır
        self._adopt()

    def _basic_config(self, *args, **kwargs) -> None:
        self.saved["basic_config"](*args, **kwargs)
        self._adopt()

    def _adopt(self) -> None:
        """std akışlara yazan logging işleyicileri kendi biçimleriyle konsola yazmayı sürdürsün;
        yanlarına dökümde simgeli satır gösteren bir eş takılır."""
        std = (self.saved["stdout"], self.saved["stderr"])
        twinned = {id(logger) for logger, _ in self.twins}
        for logger in _loggers():
            if id(logger) in twinned:
                continue
            for handler in logger.handlers:
                if not isinstance(handler, logging.StreamHandler) or isinstance(handler, logging.FileHandler):
                    continue
                stream = handler.stream
                if isinstance(stream, _Stream) and stream.capture is self:  # sonradan kurulan: eski akışa çevir
                    handler.setStream(stream.original if stream.original is not None else _Null())
                elif not any(stream is s for s in std if s is not None):
                    continue
                twin = _LogHandler(self, level=handler.level)
                logger.addHandler(twin)
                self.twins.append((logger, twin))
                break

    def stop(self) -> None:
        """Eski hallerini geri koy; araya başkası kendi kancasını taktıysa ona dokunma."""
        for name in ("stdout", "stderr"):
            stream = getattr(sys, name)
            if isinstance(stream, _Stream) and stream.capture is self:
                setattr(sys, name, self.saved[name])
        if builtins.input == self.input:
            builtins.input = self.saved["input"]
        if getpass.getpass == self.getpass:
            getpass.getpass = self.saved["getpass"]
        if isinstance(logging.lastResort, _LogHandler) and logging.lastResort.capture is self:
            logging.lastResort = self.saved["last_resort"]
        if logging.basicConfig == self._basic_config:
            logging.basicConfig = self.saved["basic_config"]
        for logger, twin in self.twins:
            logger.removeHandler(twin)
        self.twins.clear()

    def backend(self):
        """Pencere arka ucu; oturum açılmadıysa açar. Pencere değilse (terminal) yakalama sökülür, None."""
        session = self.session
        if session._backend is None:
            if session._opening:  # açılırken yazılanlar (uyarılar) yalnızca eski akışa; kilit tutuluyor
                return None
            try:
                session._io()
            except Exception:
                uninstall(session)
                return None
        backend = session._backend
        if backend is None or backend.kind != "window":
            uninstall(session)
            return None
        return backend

    def emit(self, markup: str) -> None:
        if not markup or getattr(_local, "muted", False):
            return
        backend = self.backend()
        if backend is not None:
            backend.write(markup)

    def input(self, prompt: object = "") -> str:
        """input() yerine: pencerede soru. Pencere yoksa eski input()."""
        if self.backend() is None:
            return self.saved["input"](prompt)
        label = str(prompt).strip()
        if label.endswith(":"):
            label = label[:-1].rstrip()
        return self.session.ask(escape(label) or "Girdi")

    def getpass(self, prompt: str = "Password: ", stream=None) -> str:
        """getpass.getpass() yerine: pencerede gizli soru."""
        if self.backend() is None:
            return self.saved["getpass"](prompt, stream)
        label = str(prompt).strip().rstrip(":").strip()
        return self.session.ask(escape("Parola" if label in ("", "Password") else label), password=True)
