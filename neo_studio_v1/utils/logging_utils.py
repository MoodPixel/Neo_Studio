import logging
from logging.handlers import RotatingFileHandler

from .config import LOGS_DIR

LOGS_DIR.mkdir(parents=True, exist_ok=True)
_LOG_PATH = LOGS_DIR / 'neo_studio.log'

def get_logger(name: str = 'neo_studio') -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')

    file_handler = RotatingFileHandler(_LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger
