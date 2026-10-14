import logging
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Duplicate Operation ID")


class CustomFormatter(logging.Formatter):
    def format(self=None, record=None):

        record.name = record.name.ljust(10)[:10]

        record.module = record.module.ljust(20)[:20]

        return super().format(record)


class LogSuppressFilter(logging.Filter):
    def filter(self, record):

        return False


class IgnoreConvertRequestFilter(logging.Filter):
    def filter(self, record):

        convert_chunk = "/api/voice-changer/convert_chunk" not in record.getMessage()

        convert_chunk_f = "/api_voice-changer_convert_chunk" not in record.getMessage()

        convert_chunk_bulk = "/api/voice-changer/convert_chunk_bulk" not in record.getMessage()

        convert_chunk_bukl_f = "/api_voice-changer_convert_chunk_bulk" not in record.getMessage()

        vcclient = "/vcclient.log" not in record.getMessage()

        return all([convert_chunk, convert_chunk_f, convert_chunk_bulk, convert_chunk_bukl_f, vcclient])


def setup_logger(logger_name: str = None, filename: Path = None, level=logging.DEBUG):
    if logger_name is None:
        from .const import LOGGER_NAME

        logger_name = LOGGER_NAME
    if filename is None:
        from .const import LOG_FILE

        filename = LOG_FILE

    logger = logging.getLogger(logger_name)

    logger.setLevel(logging.DEBUG)

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

    file_handler.setLevel(logging.DEBUG)

    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    for logger_name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fairseq.tasks.text_to_speech",
        "fairseq.tasks.hubert_pretraining",
        "fairseq.models.hubert.hubert",
    ):
        logger = logging.getLogger(logger_name)

        logger.propagate = False

        logger.addHandler(file_handler)

    logging.getLogger("uvicorn.access").addFilter(IgnoreConvertRequestFilter())
