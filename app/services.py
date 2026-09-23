"""Бизнес-логика spec-reviewer: документы, рецензии, аудит.

ИИ-операция выполнена цепочкой ai_chain (шаги A→B→C, п.5-6 ТЗ). Без
GENAPI_KEY цепочка возвращает безопасный отчёт с error="NO_API_KEY" —
сервис работает и без ключа (пауза пользователя, чекпоинт 12).
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app import ai_chain
from app.ai_chain import _as_list
from app.models import (
    AuditRun,
    Document,
    Review,
    ReviewAcceptanceCriterion,
    ReviewMissingRequirement,
    ReviewQuestion,
    ReviewRisk,
)


# --------------------------------------------------------------------------- #
# Аудит (каждый вызов каждой точки API → одна запись в audit_runs, п.4 ТЗ)
# --------------------------------------------------------------------------- #
def record_audit(
    db: Session,
    action: str,
    input_data: Any = None,
    output: Any = None,
    status: str = "ok",
    error: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """Записать событие в audit_runs (input/output — как JSON-строки)."""

    def _to_json(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)

    entry = AuditRun(
        action=action,
        input=_to_json(input_data),
        output=_to_json(output),
        status=status,
        error=error,
        duration_ms=duration_ms,
    )
    db.add(entry)
    db.commit()
# --------------------------------------------------------------------------- #
# Документы
# --------------------------------------------------------------------------- #
def create_document(db: Session, title: str, text: str) -> Document:
    """Создать документ и вернуть ORM-объект."""
    document = Document(title=title, text=text)
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session) -> List[Document]:
    """Список документов, свежие сверху."""
    return db.query(Document).order_by(Document.created_at.desc(), Document.id.desc()).all()


def get_document_or_404(db: Session, document_id: int) -> Optional[Document]:
    """Документ по id или None (404 обрабатывает слой API)."""
    return db.get(Document, document_id)


# --------------------------------------------------------------------------- #
# Рецензии
# --------------------------------------------------------------------------- #
def create_review(db: Session, document_id: int) -> Review:
    """Запустить рецензирование документа и сохранить результат.

    Сохраняет рецензию (review_json — каноничный архив отчёта, analysis_json —
    промежуточный разбор шага A) и разворачивает поля в дочерние нормализованные
    таблицы (риски, вопросы, критерии, чего не хватает).
    """
    document = db.get(Document, document_id)
    if document is None:
        raise ValueError(f"document {document_id} not found")

    start = time.monotonic()
    report, analysis, error = ai_chain.run_chain(document.text)
    duration_ms = (time.monotonic() - start) * 1000

    review = Review(
        document_id=document_id,
        review_json=json.dumps(report, ensure_ascii=False),
        analysis_json=json.dumps(analysis, ensure_ascii=False) if analysis else None,
        summary=report.get("summary") or None,
        confidence=report.get("confidence") or None,
        needs_review=bool(report.get("needs_review", False)),
        error=error,
        status="error" if error else "ok",
        duration_ms=duration_ms,
    )

    # Разворачиваем нормализованные блоки отчёта в дочерние таблицы
    for risk in _as_list(report.get("risks")):
        if isinstance(risk, dict) and risk.get("description"):
            review.risks.append(
                ReviewRisk(
                    severity=str(risk.get("severity", "low")),
                    description=str(risk["description"]),
                )
            )
    for text in _as_list(report.get("missing_requirements")):
        review.missing_requirements.append(ReviewMissingRequirement(requirement_text=str(text)))
    for text in _as_list(report.get("questions_to_client")):
        review.questions.append(ReviewQuestion(question_text=str(text)))
    for text in _as_list(report.get("acceptance_criteria")):
        review.acceptance_criteria.append(ReviewAcceptanceCriterion(criterion_text=str(text)))

    db.add(review)
    db.commit()
    db.refresh(review)
    return review
def get_review_or_404(db: Session, review_id: int) -> Optional[Review]:
    """Рецензия по id или None (404 обрабатывает слой API)."""
    return db.get(Review, review_id)


def list_reviews(db: Session) -> List[Review]:
    """Список рецензий по времени, свежие сверху."""
    return db.query(Review).order_by(Review.created_at.desc(), Review.id.desc()).all()


def review_to_short(review: Review) -> Dict[str, Any]:
    """Краткое представление рецензии для списка (GET /reviews)."""
    return {
        "id": review.id,
        "document_id": review.document_id,
        "created_at": review.created_at,
        "summary": review.summary,
        "confidence": review.confidence,
        "needs_review": review.needs_review,
        "error": review.error,
    }


def review_to_full(review: Review) -> Dict[str, Any]:
    """Полная карточка рецензии для витрины (GET /reviews/{id})."""
    return {
        "id": review.id,
        "document_id": review.document_id,
        "created_at": review.created_at,
        "summary": review.summary,
        "confidence": review.confidence,
        "needs_review": review.needs_review,
        "error": review.error,
        "status": review.status,
        "duration_ms": review.duration_ms,
        "risks": [
            {"severity": r.severity, "description": r.description} for r in review.risks
        ],
        "missing_requirements": [r.requirement_text for r in review.missing_requirements],
        "questions_to_client": [q.question_text for q in review.questions],
        "acceptance_criteria": [c.criterion_text for c in review.acceptance_criteria],
        "review_json": review.review_json,
        "analysis_json": review.analysis_json,
    }


# --------------------------------------------------------------------------- #
# ИИ-рецензия без сохранения (POST /ai/review)
# --------------------------------------------------------------------------- #
def run_ai_review(text: str) -> Dict[str, Any]:
    """Прямая ИИ-рецензия по схеме урока (цепочка A→B→C, п.5 ТЗ).

    До подключения цепочки (этап 9) возвращает безопасный отчёт. Результат не
    сохраняется в БД (аудит пишется на уровне API).
    """
    report, _analysis, _error = ai_chain.run_chain(text)
    return report