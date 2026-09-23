"""
Error handler — универсальный перехватчик и обработка ошибок.

Использует modules/logger.py для записи ошибок (отдельный error-лог).

Использование:
    from modules.error_handler import setup_error_handling

    # Подключить глобальные обработчики (один раз при старте)
    setup_error_handling()

    # Или зарегистрировать кастомный обработчик
    from modules.error_handler import register_handler

    def my_handler(exc_type, exc_value, exc_traceback):
        # обработка конкретной ошибки
        pass

    register_handler(ValueError, my_handler)
"""

import sys
import asyncio
import functools
import traceback

from modules.logger import get_logger

log = get_logger("error_handler")


# ---------------------------------------------------------------------------
# Глобальные обработчики
# ---------------------------------------------------------------------------
def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """Глобальный обработчик непредвиденных исключений."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Ctrl+C — не логировать как ошибку
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Логируем полный трейс
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log.error("Uncaught exception:\n%s", error_msg)


def _async_error_handler(loop, context):
    """Обработчик ошибок для asyncio (Python 3.8+)."""
    # Если это KeyboardInterrupt — не логировать
    if isinstance(context.get("exception"), KeyboardInterrupt):
        return

    # Логируем ошибку
    message = context.get("message", "Unknown async error")
    exception = context.get("exception")

    if exception:
        error_msg = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        log.error("Async error: %s\n%s", message, error_msg)
    else:
        log.error("Async error: %s", message)


# ---------------------------------------------------------------------------
# Регистрация кастомных обработчиков
# ---------------------------------------------------------------------------
_handlers = {}


def register_handler(exc_type, handler):
    """Зарегистрировать кастомный обработчик для типа исключения.

    Args:
        exc_type: класс исключения (например, ValueError).
        handler: функция handler(exc_type, exc_value, exc_traceback).
    """
    _handlers[exc_type] = handler
    log.debug("Registered handler for %s", exc_type.__name__)


def _dispatch_handler(exc_type, exc_value, exc_traceback):
    """Передать ошибку в кастомный обработчик или в глобальный."""
    for exc_class, handler in _handlers.items():
        if issubclass(exc_type, exc_class):
            handler(exc_type, exc_value, exc_traceback)
            return
    # Если кастомного нет — используем глобальный
    _global_exception_handler(exc_type, exc_value, exc_traceback)


# ---------------------------------------------------------------------------
# Подключение
# ---------------------------------------------------------------------------
def setup_error_handling():
    """Подключить все обработчики ошибок (вызвать один раз при старте приложения)."""
    # Глобальный перехват
    sys.excepthook = _global_exception_handler

    # Asyncio перехват
    try:
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop and loop.is_running():
            loop.set_exception_handler(_async_error_handler)
    except ImportError:
        pass  # asyncio недоступен

    log.info("Error handling setup complete")


# ---------------------------------------------------------------------------
# Декоратор для обработки ошибок функций
# ---------------------------------------------------------------------------
def handle_errors(func=None, *, message=None):
    """Декоратор: логировать ошибку и пробросить её дальше.

    Использование:
        @handle_errors
        def my_function():
            ...

        # Или с кастомным сообщением
        @handle_errors("Failed to process request")
        def my_function():
            ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                text = message if message is not None else f"Error in {fn.__name__}"
                log.error("%s: %s\n%s", text, exc, traceback.format_exc())
                raise
        return inner

    # Поддержка и @handle_errors, и @handle_errors("message")
    if func is not None:
        return decorator(func)
    return decorator
