"""ORM-модели БД spec-reviewer (SQLAlchemy 2.x, схема из ТЗ п.7).

Таблицы нормализованы:
  documents 1—N reviews 1—N {review_risks, review_missing_requirements,
                             review_questions, review_acceptance_criteria}
  audit_runs — журнал всех вызовов точек API (каждый запрос → запись).
FK — ON DELETE CASCADE, индексы по внешним ключам и created_at (ТЗ п.7).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    """Текущее время UTC для created_at (SQLite хранит naive datetime)."""
    return datetime.utcnow()


class Base(DeclarativeBase):
    """Базовый класс всех декларативных моделей."""


class TimestampIdMixin:
    """Общие поля id (PK) и created_at для всех таблиц."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Document(TimestampIdMixin, Base):
    """Документ (текст ТЗ), вставленный пользователем."""

    __tablename__ = "documents"
    __table_args__ = (Index("idx_documents_created_at", "created_at"),)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Удаление документа удаляет и его рецензии
    reviews: Mapped[List["Review"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Review(TimestampIdMixin, Base):
    """Рецензия: полноценный отчёт ИИ-операции (цепочка A→B→C).

    review_json — каноничный JSON-ответ шага B (архив, требование урока);
    analysis_json — промежуточный JSON шага A (разбор документа);
    остальные поля — развёрнутая витрина для списков/фильтров/экспорта.
    """

    __tablename__ = "reviews"
    __table_args__ = (
        Index("idx_reviews_created_at", "created_at"),
        Index("idx_reviews_document_id", "document_id"),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    review_json: Mapped[Optional[str]] = mapped_column(Text)
    analysis_json: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[str]] = mapped_column(String(20))  # high|medium|low
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(String(100))  # код причины ручной проверки
    status: Mapped[Optional[str]] = mapped_column(String(30))  # ok | error
    duration_ms: Mapped[Optional[float]] = mapped_column(Float)

    document: Mapped["Document"] = relationship(back_populates="reviews")
    risks: Mapped[List["ReviewRisk"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    missing_requirements: Mapped[List["ReviewMissingRequirement"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    questions: Mapped[List["ReviewQuestion"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    acceptance_criteria: Mapped[List["ReviewAcceptanceCriterion"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
class ReviewRisk(TimestampIdMixin, Base):
    """Нормализованный риск из рецензии."""

    __tablename__ = "review_risks"
    __table_args__ = (Index("idx_review_risks_review_id", "review_id"),)

    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(10))  # low | medium | high
    description: Mapped[str] = mapped_column(Text)

    review: Mapped["Review"] = relationship(back_populates="risks")


class ReviewMissingRequirement(TimestampIdMixin, Base):
    """Чего не хватает в документе (из рецензии)."""

    __tablename__ = "review_missing_requirements"
    __table_args__ = (Index("idx_review_missing_requirements_review_id", "review_id"),)

    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    requirement_text: Mapped[str] = mapped_column(Text)

    review: Mapped["Review"] = relationship(back_populates="missing_requirements")


class ReviewQuestion(TimestampIdMixin, Base):
    """Вопрос заказчику (из рецензии; при ручной проверке — минимум 3)."""

    __tablename__ = "review_questions"
    __table_args__ = (Index("idx_review_questions_review_id", "review_id"),)

    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text)

    review: Mapped["Review"] = relationship(back_populates="questions")


class ReviewAcceptanceCriterion(TimestampIdMixin, Base):
    """Критерий приёмки (из рецензии)."""

    __tablename__ = "review_acceptance_criteria"
    __table_args__ = (Index("idx_review_acceptance_criteria_review_id", "review_id"),)

    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    criterion_text: Mapped[str] = mapped_column(Text)

    review: Mapped["Review"] = relationship(back_populates="acceptance_criteria")


class AuditRun(TimestampIdMixin, Base):
    """Журнал аудита: каждый вызов каждой точки API пишет одну запись (ТЗ п.4)."""

    __tablename__ = "audit_runs"
    __table_args__ = (Index("idx_audit_runs_created_at", "created_at"),)

    action: Mapped[str] = mapped_column(String(120), nullable=False)
    input: Mapped[Optional[str]] = mapped_column(Text)  # JSON-строка входа
    output: Mapped[Optional[str]] = mapped_column(Text)  # JSON-строка выхода
    status: Mapped[Optional[str]] = mapped_column(String(30))  # ok | error
    error: Mapped[Optional[str]] = mapped_column(Text)  # причина (код/текст)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float)