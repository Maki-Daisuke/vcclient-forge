import logging
import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Duplicate Operation ID")


class CustomFormatter(logging.Formatter):
    def format(self, record):
        record.name = record.name.ljust(10)[:10]
        record.module = record.module.ljust(20)[:20]
        return super().format(record)


class LogSuppressFilter(logging.Filter):
    def filter(self, record):
        return False


class IgnoreConvertRequestFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return all(
            [
                "/api/voice-changer/convert_chunk" not in msg,
                "/api_voice-changer_convert_chunk" not in msg,
                "/api/voice-changer/convert_chunk_bulk" not in msg,
                "/api_voice-changer_convert_chunk_bulk" not in msg,
                "/vcclient.log" not in msg,
            ]
        )


def setup_logger(logger_name: str = None, filename: Path = None, level: int | None = None):
    if level is None:
        level_str = os.environ.get("LOG_LEVEL", os.environ.get("VCCLIENT_LOG_LEVEL", "WARNING")).upper()
        level = getattr(logging, level_str, logging.WARNING)

    if logger_name is None:
        from .const import LOGGER_NAME

        logger_name = LOGGER_NAME
    if filename is None:
        from .const import LOG_FILE

        filename = LOG_FILE

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False

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

    file_handler = logging.FileHandler(filename, mode="w", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fairseq.tasks.text_to_speech",
        "fairseq.tasks.hubert_pretraining",
        "fairseq.models.hubert.hubert",
    ):
        sub_logger = logging.getLogger(name)
        sub_logger.propagate = False
        sub_logger.addHandler(file_handler)

    logging.getLogger("uvicorn.access").addFilter(IgnoreConvertRequestFilter())
