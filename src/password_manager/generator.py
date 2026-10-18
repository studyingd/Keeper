"""Password generation and strength estimation.

Pure functions, no Qt: the home generator panel, the credential dialog and the
tests all share one implementation. A password is generated from a "+"-joined
set of charset keys (e.g. ``digits+letters``); strength is the Shannon
entropy of the actual character pool times the length, mapped onto four
levels (<36 weak, <60 fair, <90 strong, >=90 excellent).
"""

from __future__ import annotations

import math
import secrets
import string
from collections.abc import Iterable

PASSWORD_CHARSETS: dict[str, str] = {
    "digits": string.digits,
    "letters": string.ascii_letters,
    "symbols": "!#$%&()*+,-./:;<=>?@[]^_{|}~",
}

GENERATED_PASSWORD_LENGTH = 12
MIN_PASSWORD_LENGTH = 1
MAX_PASSWORD_LENGTH = 128

STRENGTH_THRESHOLDS = (36.0, 60.0, 90.0)
STRENGTH_LABELS = ("弱", "中", "强", "极强")


def parse_charset_mode(mode: str) -> list[str]:
    """Split a '+'-joined mode into validated charset keys."""
    keys = [key for key in mode.split("+") if key]
    if not keys or any(key not in PASSWORD_CHARSETS for key in keys):
        raise ValueError("不支持的密码字符集。")
    return keys


def generate_password(mode: str, length: int) -> str:
    """Generate a password with cryptographically secure randomness."""
    keys = parse_charset_mode(mode)
    if not MIN_PASSWORD_LENGTH <= length <= MAX_PASSWORD_LENGTH:
        raise ValueError(f"密码长度必须在 {MIN_PASSWORD_LENGTH} 到 {MAX_PASSWORD_LENGTH} 之间。")
    characters = "".join(PASSWORD_CHARSETS[key] for key in keys)
    return "".join(secrets.choice(characters) for _ in range(length))


def pool_size(keys: Iterable[str]) -> int:
    return len({char for key in keys for char in PASSWORD_CHARSETS[key]})


def entropy_bits(length: int, keys: Iterable[str]) -> float:
    """Shannon entropy of ``length`` draws from the union of the given sets."""
    size = pool_size(keys)
    return length * math.log2(size) if size else 0.0


def strength_level(bits: float) -> int:
    """Map entropy onto 1..4; 0 means "nothing generated yet"."""
    if bits <= 0:
        return 0
    for index, threshold in enumerate(STRENGTH_THRESHOLDS):
        if bits < threshold:
            return index + 1
    return 4


def strength_label(level: int) -> str:
    return STRENGTH_LABELS[level - 1] if 1 <= level <= 4 else "—"
