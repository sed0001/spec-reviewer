"""Конфигурация приложения: все настройки — только через переменные окружения.

Значения по умолчанию — из ТЗ п.12.1 (шпаргалка DATABASE_PATH=./app.db,
PORT=8040, MAX_DOC_TEXT_LENGTH=30000 и т.д.). Секреты (GENAPI_KEY) клиент GenAPI
читает сам из env (.env-файл подгружается здесь, один раз, при старте).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Корень проекта spec-reviewer (папка, где лежат app/, modules/, .env)
BASE_DIR = Path(__file__).resolve().parent.parent

# Подгружаем .env один раз при импорте конфига
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    """Значение env-переменной или default (пустое значение = не задано)."""
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value


def _int_env(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Все настройки приложения, собранные из .env / окружения."""

    # Сервер
    app_host: str
    app_port: int
    # БД
    database_path: str
    # Валидация входов
    max_doc_text_length: int
    # Логи
    log_level: str
    # LLM-цепочка (шаги A/B/C)
    llm_provider: str
    llm_model: str
    llm_temp_analyze: float
    llm_temp_generate: float
    llm_max_tokens: int
    llm_timeout_seconds: int
    llm_retries: int
    llm_json_mode: bool

    @property
    def log_level_no(self) -> int:
        """LOG_LEVEL числом для logging (неизвестное значение → INFO)."""
        import logging

        return getattr(logging, self.log_level.upper(), logging.INFO)

    @property
    def has_llm_key(self) -> bool:
        """Есть ли ключ GenAPI (для «честной» работы без ключа на этапе 11)."""
        return bool(_env("GENAPI_KEY"))


def get_settings() -> Settings:
    """Собрать настройки из env (вызывается один раз при старте приложения)."""
    db_path = _env("DATABASE_PATH", "./app.db")
    if not os.path.isabs(db_path):
        # Относительный путь — относительно корня проекта (не текущей папки запуска)
        db_path = str(BASE_DIR / db_path)

    return Settings(
        app_host=_env("APP_HOST", "0.0.0.0"),
        app_port=_int_env("APP_PORT", 8040),
        database_path=db_path,
        max_doc_text_length=_int_env("MAX_DOC_TEXT_LENGTH", 30000),
        log_level=_env("LOG_LEVEL", "INFO"),
        llm_provider=_env("LLM_PROVIDER", "genai"),
        llm_model=_env("LLM_MODEL", "gpt-4o-mini"),
        llm_temp_analyze=_float_env("LLM_TEMP_ANALYZE", 0.1),
        llm_temp_generate=_float_env("LLM_TEMP_GENERATE", 0.3),
        llm_max_tokens=_int_env("LLM_MAX_TOKENS", 2048),
        llm_timeout_seconds=_int_env("LLM_TIMEOUT_SECONDS", 60),
        llm_retries=_int_env("LLM_RETRIES", 2),
        llm_json_mode=_env("LLM_JSON_MODE", "0").lower() in ("1", "true", "yes", "on"),
    )


# Единый экземпляр настроек для всего приложения
settings = get_settings()