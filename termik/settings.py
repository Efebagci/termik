"""Kullanıcı ayarları: görünüm ve kip tercihleri koda dokunmadan seçilir.

Öncelik: kodda verilen değer > ortam değişkeni > ayar dosyası > varsayılan.

Ayar dosyası TOML'dur. Yeri TERMIK_CONFIG ile değiştirilebilir; yoksa
    Windows      %APPDATA%\\termik\\ayarlar.toml
    diğerleri    $XDG_CONFIG_HOME/termik/ayarlar.toml (yoksa ~/.config/termik/ayarlar.toml)

    theme = "orman"          # renk teması
    look = "terminal"        # terminal · modern
    density = "dengeli"      # sıkı · dengeli · rahat · ferah
    mode = "auto"            # akış API'si: auto · window · terminal
    dialogs = "native"       # dosya diyalogları: native (işletim sisteminin) · builtin (termik'in)
    font = "C:/Fonts/Iosevka.ttf"
    bar = "segment"          # herhangi bir biçim belirteci
    accent = "#ff8800"       # renkler de ezilebilir

Ortam değişkenleri aynı adların TERMIK_ önekli büyük harflisidir: TERMIK_THEME, TERMIK_DENSITY,
TERMIK_BAR… Geçersiz bir değer programı durdurmaz: bir kez uyarı yazılır, değer yok sayılır.
`termik ayarlar` komutu bu dosyayı pencerede düzenler.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any

from .theme import _COLOR_FIELDS, CHOICES, DENSITIES, LOOKS, THEMES, Theme, hex_color

MODES = {"auto": "auto", "window": "window", "pencere": "window", "gui": "window",
         "terminal": "terminal", "tty": "terminal"}
DIALOGS = {"native": "native", "yerel": "native", "sistem": "native", "os": "native",
           "builtin": "builtin", "yerleşik": "builtin", "termik": "builtin"}

# biçim belirteçleri ve varsayılanları; renklerin varsayılanı yok (temadan gelir)
TOKENS: dict[str, Any] = {f.name: f.default for f in fields(Theme) if f.name != "name"}
KEYS = ("theme", "look", "density", "mode", "dialogs", "font", "font_bold", *TOKENS)

_HEADER = """\
# termik ayarları
# Öncelik: koddaki değer > ortam değişkeni (TERMIK_THEME…) > bu dosya > varsayılan.
# Ayarlanabilenler: theme, look, density, mode, dialogs, font, font_bold ve biçim belirteçleri
# (title, focus, button, bar, selection, shadow, radio, tabs, slider, select, image, spin,
# split, form_label, chart, radius, panel_fill, font_size, line_height, pad_x, pad_y) ile renkler (accent = "#ff8800" gibi).
"""

_warned: set[str] = set()
_cache: tuple[Path, float, dict] | None = None


def _warn(message: str) -> None:
    if message in _warned:
        return
    _warned.add(message)
    if sys.stderr is not None:
        try:
            sys.stderr.write(f"termik ayarları: {message}\n")
        except (OSError, ValueError):
            pass


def config_path() -> Path:
    """Ayar dosyasının yeri (dosya olmayabilir)."""
    env = os.environ.get("TERMIK_CONFIG")
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "termik" / "ayarlar.toml"


def read_file(path: Path | None = None) -> dict[str, Any]:
    """Ayar dosyasındaki değerler, denetlenmeden; dosya yoksa ya da okunamazsa boş."""
    global _cache
    path = path or config_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if _cache is not None and _cache[0] == path and _cache[1] == mtime:
        return dict(_cache[2])
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        _warn(f"{path} okunamadı ({exc}); yok sayılıyor")
        data = {}
    _cache = (path, mtime, data)
    return dict(data)


def _convert(key: str, raw: Any) -> Any:
    """Değeri denetle ve çevir; geçersizse ValueError."""
    if key in ("theme", "look", "density"):
        known = {"theme": THEMES, "look": LOOKS, "density": DENSITIES}[key]
        if raw not in known:
            raise ValueError(", ".join(known))
        return raw
    if key == "mode":
        mode = MODES.get(str(raw).strip().lower())
        if mode is None:
            raise ValueError("auto, window, terminal")
        return mode
    if key == "dialogs":
        kind = DIALOGS.get(str(raw).strip().lower())
        if kind is None:
            raise ValueError("native, builtin")
        return kind
    if key in ("font", "font_bold"):
        path = os.path.expanduser(str(raw))
        if not os.path.isfile(path):
            raise ValueError("dosya bulunamadı")
        return path
    if key in _COLOR_FIELDS:
        return hex_color(str(raw))
    default = TOKENS[key]
    if isinstance(default, bool):
        if isinstance(raw, bool):
            return raw
        word = str(raw).strip().lower()
        if word in ("1", "true", "evet", "açık", "on", "yes"):
            return True
        if word in ("0", "false", "hayır", "hayir", "kapalı", "off", "no"):
            return False
        raise ValueError("true ya da false")
    if isinstance(default, int):
        if isinstance(raw, bool):
            raise ValueError("tam sayı")
        return int(raw)
    if isinstance(default, float):
        if isinstance(raw, bool):
            raise ValueError("sayı")
        return float(raw)
    if key in CHOICES and raw not in CHOICES[key]:
        raise ValueError(", ".join(CHOICES[key]))
    return str(raw)


def preferences() -> dict[str, Any]:
    """Ortam değişkenleri ve ayar dosyasından gelen, denetlenmiş tercihler.

    {"theme": …, "look": …, "density": …, "mode": …, "dialogs": …, "font": …, "font_bold": …,
    "tokens": {…}};
    yalnızca ayarlanmış anahtarlar bulunur ("tokens" hep vardır). Ortam değişkeni dosyadakini ezer.
    """
    path = config_path()
    env = {key: os.environ[name] for key in KEYS
           if (name := "TERMIK_" + key.upper()) in os.environ and os.environ[name].strip()}
    out: dict[str, Any] = {"tokens": {}}
    for data, source in ((read_file(path), str(path)), (env, "ortam değişkeni")):
        for key, raw in data.items():
            if key not in KEYS:
                _warn(f"bilinmeyen ayar {key!r} ({source})")
                continue
            try:
                value = _convert(key, raw)
            except (TypeError, ValueError) as exc:
                _warn(f"geçersiz değer {key} = {raw!r} ({source}); geçerliler: {exc}")
                continue
            if key in TOKENS:
                out["tokens"][key] = value
            else:
                out[key] = value
    return out


def check_names(*, theme: str | None = None, look: str | None = None, density: str | None = None,
                dialogs: str | None = None) -> None:
    """Kodda verilen adları denetle: yanlışsa (ayarlardaki gibi yok sayılmaz) ValueError."""
    for value, known, what in ((theme, THEMES, "tema"), (look, LOOKS, "görünüm"), (density, DENSITIES, "yoğunluk"),
                               (dialogs, ("native", "builtin"), "diyalog türü")):
        if value is not None and value not in known:
            raise ValueError(f"bilinmeyen {what}: {value!r} ({', '.join(known)})")


def _toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, tuple) and len(value) == 3:  # renk
        return '"#{:02x}{:02x}{:02x}"'.format(*value)
    return json.dumps(str(value), ensure_ascii=False)  # JSON yazısı geçerli bir TOML yazısıdır


def save(values: dict[str, Any], path: Path | None = None) -> Path:
    """Değerleri ayar dosyasına yaz; dosyadaki diğer satırlar ve yorumlar korunur. None anahtarı siler."""
    global _cache
    path = path or config_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = _HEADER.splitlines()
    # yalnızca en üst düzeydeki anahtarlar: ilk [tablo] satırından öncesi
    end = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
    for key, value in values.items():
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        found = next((i for i in range(end) if pattern.match(lines[i])), None)
        if value is None:
            if found is not None:
                del lines[found]
                end -= 1
        elif found is not None:
            lines[found] = f"{key} = {_toml(value)}"
        else:
            lines.insert(end, f"{key} = {_toml(value)}")
            end += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _cache = None
    return path


__all__ = ["KEYS", "MODES", "TOKENS", "check_names", "config_path", "preferences", "read_file", "save"]
