"""Pydantic-схемы (DTO) для API spec-reviewer (п.4 ТЗ).

Входы валидируются на уровне схемы: непустые title/text, лимит длины
MAX_DOC_TEXT_LENGTH (30 000) → FastAPI отдаёт 422 при нарушении.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.config import settings


def _verify_text_length(value: str) -> str:
    """Общая проверка лимита длины документа (применяется к полю text)."""
    limit = settings.max_doc_text_length
    if len(value) > limit:
        raise ValueError(f"text превышает лимит {limit} символов")
    return value


# --------------------------------------------------------------------------- #
# Входы
# --------------------------------------------------------------------------- #
class DocumentCreate(BaseModel):
    """Вход POST /documents: title + text (вход — только обычный текст, без файлов)."""

    title: str = Field(..., min_length=1, max_length=500)
    text: str = Field(..., min_length=1)

    @field_validator("text")
    @classmethod
    def text_not_too_long(cls, value: str) -> str:
        return _verify_text_length(value)


class AIReviewRequest(BaseModel):
    """Вход POST /ai/review: сам текст документа."""

    text: str = Field(..., min_length=1)

    @field_validator("text")
    @classmethod
    def text_not_too_long(cls, value: str) -> str:
        return _verify_text_length(value)


# --------------------------------------------------------------------------- #
# Структурные блоки рецензии
# --------------------------------------------------------------------------- #
class RiskOut(BaseModel):
    """Один риск: тяжесть + описание."""

    severity: str  # low | medium | high
    description: str


class ReviewReport(BaseModel):
    """Итоговый отчёт рецензии (схема урока, п.5 ТЗ + needs_review)."""

    summary: str
    risks: List[RiskOut]
    missing_requirements: List[str]
    questions_to_client: List[str]
    acceptance_criteria: List[str]
    confidence: str  # high | medium | low
    needs_review: bool


# --------------------------------------------------------------------------- #
# Ответы
# --------------------------------------------------------------------------- #
class DocumentCreateResponse(BaseModel):
    """Ответ POST /documents (по уроку)."""

    status: str
    document_id: int


class DocumentListItem(BaseModel):
    """Строка списка документов (раздел «Документы»)."""

    id: int
    title: str
    created_at: datetime


class DocumentListResponse(BaseModel):
    """Список документов (GET /documents)."""

    status: str
    documents: List[DocumentListItem]


class ReviewCreateResponse(BaseModel):
    """Ответ POST /documents/{id}/review (по уроку)."""

    status: str
    review_id: int


class ReviewShortOut(BaseModel):
    """Строка списка рецензий (GET /reviews) для раздела «Рецензии»."""

    id: int
    document_id: int
    created_at: datetime
    summary: Optional[str]
    confidence: Optional[str]
    needs_review: bool
    error: Optional[str]


class ReviewListResponse(BaseModel):
    """Список рецензий по времени (свежие сверху)."""

    status: str
    total: int
    reviews: List[ReviewShortOut]


class ReviewOut(BaseModel):
    """Полная карточка рецензии (GET /reviews/{id}).

    Содержит блоки отчёта для витрины, сырые JSON'ы (review_json,
    analysis_json — ввод/вывод шагов) и служебные поля.
    """

    id: int
    document_id: int
    created_at: datetime
    summary: Optional[str]
    confidence: Optional[str]
    needs_review: bool
    error: Optional[str]
    status: Optional[str]
    duration_ms: Optional[float]
    risks: List[RiskOut]
    missing_requirements: List[str]
    questions_to_client: List[str]
    acceptance_criteria: List[str]
    review_json: Optional[str]
    analysis_json: Optional[str]


class HealthOut(BaseModel):
    """Ответ GET /health (живость сервиса, для docker-compose)."""

    status: str
    service: str
    version: str
    llm_configured: bool