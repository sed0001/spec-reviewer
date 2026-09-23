"""Подключение к БД SQLite через SQLAlchemy 2.x.

Файл БД — из config.settings.database_path (env DATABASE_PATH, по умолчанию
./app.db относительно корня проекта). init_db() вызывается при старте
приложения, get_db() — FastAPI-зависимость (одна сессия на запрос).
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Импортируем модели, чтобы все таблицы зарегистрировались в Base.metadata
from app import models  # noqa: F401
from app.config import settings
from app.models import Base

# SQLite + FastAPI: check_same_thread=False, т.к. запросы могут приходить
# сразу из нескольких потоков (uvicorn).
engine = create_engine(
    f"sqlite:///{settings.database_path}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Создать все таблицы, если их ещё нет (идемпотентно)."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI-зависимость: сессия БД на время одного запроса."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()