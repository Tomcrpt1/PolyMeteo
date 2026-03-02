from __future__ import annotations

from typing import Final

BUCKETS: Final[list[str]] = ["<=12", "13", "14", "15", "16", "17", "18", "19", ">=20"]


def map_temp_to_bucket(temp_c: int) -> str:
    if temp_c <= 12:
        return "<=12"
    if temp_c >= 20:
        return ">=20"
    return str(temp_c)
