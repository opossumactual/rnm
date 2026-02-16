"""Structured logging setup for RNM."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rnm.config.schema import LoggingConfig

LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"


def setup_logging(config: LoggingConfig) -> logging.Logger:
    """Configure the root rnm logger based on config."""
    logger = logging.getLogger("rnm")
    logger.setLevel(getattr(logging, config.level.upper()))
    logger.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Always log to stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    # Optionally log to file with rotation
    if config.file:
        log_path = Path(config.file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=config.max_size_mb * 1024 * 1024,
            backupCount=config.backup_count,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
