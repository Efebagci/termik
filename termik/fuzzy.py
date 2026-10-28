"""Bulanık arama (fzf benzeri) ve Türkçe harf gevşetme."""

from __future__ import annotations

_FOLD = str.maketrans("İIıŞşĞğÇçÖöÜü", "iiissggccoouu")


def fold(text: str) -> str:
    """Türkçe harfleri gevşet: 'baslat' yazınca 'Başlat' da eşleşsin. Uzunluk değişmez."""
    return text.translate(_FOLD).lower()


def match(query: str, text: str) -> list[int] | None:
    """query'nin harfleri text'te sırayla geçiyorsa eşleşen konumlar, geçmiyorsa None."""
    q, t = fold(query).replace(" ", ""), fold(text)
    positions, i = [], 0
    for ch in q:
        i = t.find(ch, i)
        if i < 0:
            return None
        positions.append(i)
        i += 1
    return positions


def score(positions: list[int]) -> int:
    """Küçük olan önce gelir: bitişik ve başa yakın eşleşmeler kazanır."""
    if not positions:
        return 0
    return (positions[-1] - positions[0] - len(positions) + 1) * 2 + positions[0]
