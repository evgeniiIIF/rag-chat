"""Единый логгер. Отдельный Filter-класс (не lambda)."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Final

from .config import get_settings

_CONFIGURED: Final[str] = "_ragchat_configured"
_LOGGER_NAME: Final[str] = "ragchat"


class _HealthPathFilter(logging.Filter):
    """Отсекает access-логи по /health и /health/readiness."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "/health" not in msg


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if getattr(logger, _CONFIGURED, False):
        return logger

    settings = get_settings()
    logger.setLevel(settings.log_level)

    console = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = RotatingFileHandler("ragchat.log", maxBytes=10 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logging.getLogger("uvicorn.access").addFilter(_HealthPathFilter())
    setattr(logger, _CONFIGURED, True)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)
