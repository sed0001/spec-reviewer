"""
Модуль логирования проекта — универсальный, для копирования в другие проекты.

Требования:
- Несколько типов логов, каждый тип — свой файл;
- error.log — отдельным файлом (легко искать ошибки);
- Новый файл каждые 6 часов (ротация);
- Хранение не более 3 дней (старые файлы удаляются автоматически).

Использование:
    from logger import get_logger

    logger = get_logger("my_module")
    logger.info("сообщение")
    logger.error("ошибка")

Структура логов (папка logs/ в корне проекта, рядом с app/ и modules/):
    logs/
    ├── app.YYYYMMDD-HH.log      — общие логи (INFO, DEBUG, WARNING)
    └── error.YYYYMMDD-HH.log    — ошибки (ERROR)
"""

import os
import logging
import logging.handlers
from datetime import datetime


# ---------------------------------------------------------------------------
# Пути — логи пишутся в папку logs/ в корне проекта (этот файл лежит в modules/)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOGS_DIR = os.path.join(_PROJECT_ROOT, "logs")

# Создаём папку логов, если нет
os.makedirs(_LOGS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Форматтер — единый для всех логов
# ---------------------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)


# ---------------------------------------------------------------------------
# Фабрика логгеров
# ---------------------------------------------------------------------------
def get_logger(
    name: str,
    level: int = logging.INFO,
    rotate_hours: int = 6,
    keep_days: int = 3,
) -> logging.Logger:
    """Создать и настроить логгер для модуля.

    Args:
        name: имя логгера (обычно __name__ модуля).
        level: базовый уровень логирования.
        rotate_hours: через сколько часов создавать новый файл (по умолчанию 6).
        keep_days: сколько дней хранить логи (по умолчанию 3).

    Returns:
        Настроенный logging.Logger.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger  # уже настроен

    now = datetime.now()

    # --- INFO / DEBUG / WARNING ---
    _add_timed_file_handler(
        logger,
        filename=f"app.{now.strftime('%Y%m%d-%H')}.log",
        level=level,
        rotate_hours=rotate_hours,
        keep_days=keep_days,
        propagate=False,
    )

    # --- ERROR (отдельный файл) ---
    _add_timed_file_handler(
        logger,
        filename=f"error.{now.strftime('%Y%m%d-%H')}.log",
        level=logging.ERROR,
        rotate_hours=rotate_hours,
        keep_days=keep_days,
        propagate=False,
    )

    # --- Console handler (человек читает в терминале) ---
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(_formatter)
    logger.addHandler(console)

    return logger


# ---------------------------------------------------------------------------
# Внутренние helpers
# ---------------------------------------------------------------------------
def _add_timed_file_handler(
    logger: logging.Logger,
    filename: str,
    level: int,
    rotate_hours: int,
    keep_days: int,
    propagate: bool,
) -> None:
    """Добавить TimedRotatingFileHandler к логгеру."""
    path = os.path.join(_LOGS_DIR, filename)

    handler = logging.handlers.TimedRotatingFileHandler(
        filename=path,
        when="H",
        interval=rotate_hours,
        backupCount=keep_days * (24 // rotate_hours),  # = keep_days * 4 при 6ч
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(_formatter)
    logger.addHandler(handler)
    logger.propagate = propagate
