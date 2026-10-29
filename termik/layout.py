"""Yerleşim: boyut tanımları ve esnek (flex) dizim.

Boyutlar CLI birimleriyle verilir: sayı genişlikte karakter, yükseklikte satır demektir
(width=30 → 30 karakter, height=2.5 → iki buçuk satır). Ayrıca "12px", "40%", "2fr" (kalan
alandan pay) ve "auto" (içeriği kadar) kullanılabilir.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Size:
    kind: str  # cells · px · percent · fr · auto
    value: float = 0.0


# Boyut yazımı: 30 (karakter ya da satır), "12px", "40%", "2fr", "auto"; None verilmedi demek
SizeSpec = int | float | str | Size | None
# İç boşluk: 1 (her yan) · (dikey, yatay) · (üst, sağ, alt, sol); dikey satır, yatay karakter
PaddingSpec = float | tuple[float, float] | tuple[float, float, float, float] | None

AUTO = Size("auto")
FILL = Size("fr", 1.0)


def parse_size(spec: SizeSpec) -> Size | None:
    """30 → 30 hücre, "12px", "40%", "2fr", "fr", "auto". None olduğu gibi döner."""
    if spec is None or isinstance(spec, Size):
        return spec
    if isinstance(spec, (int, float)):
        return Size("cells", float(spec))
    s = str(spec).strip().lower()
    if s == "auto":
        return AUTO
    for suffix, kind in (("px", "px"), ("fr", "fr"), ("%", "percent")):
        if s.endswith(suffix):
            number = s[: -len(suffix)].strip()
            return Size(kind, float(number) if number else 1.0)
    return Size("cells", float(s))


def resolve(size: Size, unit: int, available: int) -> int:
    """Sabit boyutu piksele çevir (fr ve auto için 0)."""
    if size.kind == "cells":
        return round(size.value * unit)
    if size.kind == "px":
        return round(size.value)
    if size.kind == "percent":
        return round(available * size.value / 100)
    return 0


def distribute(specs: list[Size], natural: list[int], available: int, unit: int) -> list[int]:
    """Ana eksende boyutları dağıt: önce sabitler ve auto, kalan alan fr payları oranında.

    Paylar birikimli yuvarlanır; böylece toplamları kalan alana pikseli pikseline eşit olur.
    """
    sizes = [0] * len(specs)
    used = 0
    fr_total = 0.0
    for i, (s, nat) in enumerate(zip(specs, natural)):
        if s.kind == "fr":
            fr_total += s.value
        else:
            sizes[i] = nat if s.kind == "auto" else resolve(s, unit, available)
            used += sizes[i]
    if fr_total > 0:
        remaining = max(0, available - used)
        acc, given = 0.0, 0
        for i, s in enumerate(specs):
            if s.kind == "fr":
                acc += s.value
                share = round(remaining * acc / fr_total) - given
                sizes[i] = share
                given += share
    return sizes


def parse_padding(spec: PaddingSpec) -> tuple[float, float, float, float]:
    """İç boşluk: 1 → her yan; (dikey, yatay); (üst, sağ, alt, sol). Dikey satır, yatay karakter."""
    if spec is None:
        return 0.0, 0.0, 0.0, 0.0
    if isinstance(spec, (int, float)):
        v = float(spec)
        return v, v, v, v
    values = tuple(float(v) for v in spec)
    if len(values) == 2:
        return values[0], values[1], values[0], values[1]
    if len(values) == 4:
        return values[0], values[1], values[2], values[3]
    raise ValueError(f"geçersiz iç boşluk: {spec!r}")
