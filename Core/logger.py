"""Logging setup: rotating file log + console."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from .paths import LOG_DIR

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    if sys.stderr is not None:  # pythonw has no stderr
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
