"""Точка входа FastAPI-приложения spec-reviewer.

Точки доступа (п.4 ТЗ):
  POST   /documents                 — создать документ
  GET    /documents                 — список документов
  POST   /documents/{id}/review     — создать рецензию (запуск ИИ-операции)
  GET    /reviews/{id}              — карточка рецензии
  GET    /reviews                   — список рецензий
  POST   /ai/review                 — ИИ-рецензия (цепочка A→B→C)
  GET    /health                    — проверка живости (для docker-compose)

Каждый вызов каждой точки пишет запись в audit_runs (п.4 ТЗ): при успехе —
status="ok", при HTTPException или бизнес-ошибке — status="error" с причиной.
Без GENAPI_KEY цепочка возвращает безопасный отчёт с needs_review=true и
error="NO_API_KEY" (сервис работает и без ключа).
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import schemas, services
from app.config import settings
from app.db import SessionLocal, get_db, init_db
from modules.error_handler import setup_error_handling
from modules.logger import get_logger

log = get_logger("main", level=settings.log_level_no)


# --------------------------------------------------------------------------- #
# Жизненный цикл приложения
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Старт: БД + глобальная обработка ошибок; stop: прощальный лог."""
    init_db()
    setup_error_handling()
    log.info("spec-reviewer started: host=%s port=%s db=%s",
             settings.app_host, settings.app_port, settings.database_path)
    yield
    log.info("spec-reviewer stopped")


app = FastAPI(title="spec-reviewer", version="1.0.0", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Аудит вызовов
# --------------------------------------------------------------------------- #
def audit_call(
    db: Session,
    action: str,
    input_data: Any,
    func: Callable[[], Any],
    *,
    business_error: Callable[[Any], Optional[str]] = None,
) -> Any:
    """Выполнить обработчик с записью в audit_runs (status, error, duration_ms).

    status в audit_runs = "error", если: HTTPException, исключение или
    бизнес-ошибка результата (например, error="INVALID_JSON" у рецензии) — ТЗ п.4.
    """
    start = time.monotonic()
    try:
        result = func()
        status = "ok"
        error: Optional[str] = None
        if business_error is not None:
            error = business_error(result)
            if error:
                status = "error"
        services.record_audit(
            db, action, input_data, result, status, error,
            duration_ms=(time.monotonic() - start) * 1000,
        )
        return result
    except HTTPException as exc:
        services.record_audit(
            db, action, input_data, None, "error",
            str(exc.detail) if isinstance(exc.detail, str) else "HTTP error",
            duration_ms=(time.monotonic() - start) * 1000,
        )
        raise

    except Exception as exc:  # непредвиденное — журналируем в audit и поднимаем (500)
        services.record_audit(
            db, action, input_data, None, "error",
            f"{type(exc).__name__}: {exc}",
            duration_ms=(time.monotonic() - start) * 1000,
        )
        raise


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Ошибки 422 тоже пишутся в audit_runs (сами входные проверки API)."""
    db = SessionLocal()
    try:
        body = None
        try:
            body = await request.body()
        except Exception:
            body = None
        services.record_audit(
            db,
            action=f"validation_error:{request.method} {request.url.path}",
            input_data=body.decode("utf-8", errors="replace") if body else None,
            output=None,
            status="error",
            error="VALIDATION_ERROR",
            duration_ms=0.0,
        )
    finally:
        db.close()
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})
# --------------------------------------------------------------------------- #
# Роуты API
# --------------------------------------------------------------------------- #
@app.post("/documents", response_model=schemas.DocumentCreateResponse)
def create_document(payload: schemas.DocumentCreate, db: Session = Depends(get_db)):
    """Создать документ. 422 при пустых/перегруженных полях (проверки Pydantic)."""

    def _handler() -> dict:
        document = services.create_document(db, payload.title, payload.text)
        return {"status": "ok", "document_id": document.id}

    return audit_call(db, "create_document", payload.model_dump(), _handler)


@app.get("/documents", response_model=schemas.DocumentListResponse)
def list_documents(db: Session = Depends(get_db)):
    """Список документов (id, title, created_at)."""

    def _handler() -> dict:
        return {
            "status": "ok",
            "documents": [
                {"id": d.id, "title": d.title, "created_at": d.created_at}
                for d in services.list_documents(db)
            ],
        }

    return audit_call(db, "list_documents", None, _handler)


@app.post("/documents/{document_id}/review", response_model=schemas.ReviewCreateResponse)
def create_document_review(document_id: int, db: Session = Depends(get_db)):
    """Запустить рецензирование документа (ИИ-операция A→B→C + сохранение)."""

    def _handler() -> dict:
        if services.get_document_or_404(db, document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found")
        review = services.create_review(db, document_id)
        return {"status": "ok", "review_id": review.id, "error": review.error}

    return audit_call(
        db, "create_review", {"document_id": document_id}, _handler,
        business_error=lambda r: r.get("error") if isinstance(r, dict) else None,
    )


@app.get("/reviews/{review_id}", response_model=schemas.ReviewOut)
def get_review(review_id: int, db: Session = Depends(get_db)):
    """Витрина рецензии: блоки отчёта + сырые JSON ввода/вывода."""

    def _handler() -> dict:
        review = services.get_review_or_404(db, review_id)
        if review is None:
            raise HTTPException(status_code=404, detail="Review not found")
        return services.review_to_full(review)

    return audit_call(db, "get_review", {"review_id": review_id}, _handler)


@app.get("/reviews", response_model=schemas.ReviewListResponse)
def list_reviews(db: Session = Depends(get_db)):
    """Список рецензий по времени (свежие сверху)."""

    def _handler() -> dict:
        reviews = services.list_reviews(db)
        return {
            "status": "ok",
            "total": len(reviews),
            "reviews": [services.review_to_short(r) for r in reviews],
        }

    return audit_call(db, "list_reviews", None, _handler)


@app.post("/ai/review", response_model=schemas.ReviewReport)
def ai_review(payload: schemas.AIReviewRequest):
    """ИИ-рецензия «в один клик» (цепочка A→B→C, без сохранения в БД)."""
    db = SessionLocal()
    try:
        return audit_call(
            db,
            "ai_review",
            {"text_length": len(payload.text)},
            lambda: services.run_ai_review(payload.text),
            business_error=lambda r: r.get("error") if isinstance(r, dict) else None,
        )
    finally:
        db.close()


@app.get("/health", response_model=schemas.HealthOut)
def health(db: Session = Depends(get_db)):
    """Проверка живости сервиса (для docker-compose healthcheck)."""

    def _handler() -> dict:
        return {
            "status": "ok",
            "service": "spec-reviewer",
            "version": "1.0.0",
            "llm_configured": settings.has_llm_key,
        }

    return audit_call(db, "health", None, _handler)


# --------------------------------------------------------------------------- #
# Статика (веб-панель) и корневая страница
# --------------------------------------------------------------------------- #
_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
def index():
    """Отдать веб-панель (index.html)."""
    index_file = _STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"status": "ok", "service": "spec-reviewer"})


if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# --------------------------------------------------------------------------- #
# Запуск
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=False)