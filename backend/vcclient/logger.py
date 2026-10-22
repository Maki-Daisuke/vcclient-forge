from __future__ import annotations

import logging
import os
import warnings

from vcclient.const import LOG_FILE, LOGGER_NAME

warnings.filterwarnings("ignore", message="Duplicate Operation ID")


class CustomFormatter(logging.Formatter):
    def format(self, record):
        record.name = record.name.ljust(10)[:10]
        record.module = record.module.ljust(20)[:20]
        return super().format(record)


class IgnoreConvertRequestFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return all(
            [
                "/api/voice-changer/convert_chunk" not in msg,
                "/api/voice-changer/convert_chunk_bulk" not in msg,
                "/vcclient.log" not in msg,
            ]
        )


def _init_logger() -> logging.Logger:
    level_str = os.environ.get("LOG_LEVEL", os.environ.get("VCCLIENT_LOG_LEVEL", "WARNING")).upper()
    level = getattr(logging, level_str, logging.WARNING)

    log = logging.getLogger(LOGGER_NAME)
    log.setLevel(level)
    log.propagate = False

    custom_datefmt = "%H:%M:%S"
    if level == logging.DEBUG:
        formatter = CustomFormatter(
            "%(asctime)s - %(name)s - %(module)s - %(levelname)s - %(message)s - %(pathname)s - %(lineno)s"
        )
    else:
        formatter = CustomFormatter(
            "%(asctime)s - %(name)s - %(module)s - %(levelname)s - %(message)s - %(module)s - %(lineno)s",
            datefmt=custom_datefmt,
        )

    file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)

    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
    ):
        sub_logger = logging.getLogger(name)
        sub_logger.propagate = False
        sub_logger.addHandler(file_handler)

    logging.getLogger("uvicorn.access").addFilter(IgnoreConvertRequestFilter())
    return log


logger: logging.Logger = _init_logger()
