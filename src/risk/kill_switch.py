from __future__ import annotations

from pathlib import Path


def kill_switch_active(env_flag: int, file_path: Path) -> bool:
    return env_flag == 1 or file_path.exists()
