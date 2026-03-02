from __future__ import annotations

import logging

from rich.logging import RichHandler


_FORMAT = "%(message)s"


def setup_logger(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(
        level=level,
        format=_FORMAT,
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    return logging.getLogger("polymeteo")
