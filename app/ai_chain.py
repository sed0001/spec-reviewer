"""ИИ-операция spec-reviewer — цепочка шагов A→B→C (п.5–6 ТЗ).

  Шаг A — «Разбор документа»   (LLM, temperature 0.1): строгий промежуточный JSON.
  Шаг B — «Формирование рецензии» (LLM, temperature 0.3): вход = текст + разбор A.
  Шаг C — «Решение о ручной проверке» (без LLM): детерминированные правила.

Гарантии (п.6 ТЗ):
- Ответы LLM парсятся и валидируются по схемам; невалидный → error="INVALID_JSON".
- needs_review=true при confidence="low" / противоречиях / сыром тексте / неверном JSON.
- При любой ошибке возвращается безопасный отчёт: поля могут быть пустыми,
  но не отсутствующими; вопросы добираются до минимума 3 шаблонными.
- Без GENAPI_KEY цепочка не вызывается: error="NO_API_KEY", безопасный отчёт.

LLM подключается через langchain_module (мост ``genapi`` поверх клиента modules.genapi).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.prompts import SYSTEM_PROMPT_STEP_A, SYSTEM_PROMPT_STEP_B
from modules.langchain_module.base import get_llm
from modules.logger import get_logger

log = get_logger("ai_chain", level=settings.log_level_no)

# Допустимые значения схем
SEVERITIES = ("low", "medium", "high")
CONFIDENCES = ("high", "medium", "low")
DOCUMENT_TYPES = ("spec", "brief", "other")

# Шаблонные вопросы ручной проверки (добор до минимума 3, п.6 ТЗ)
DEFAULT_REVIEW_QUESTIONS: List[str] = [
    "Уточните, пожалуйста, цель документа и ожидаемый результат.",
    "Уточните, пожалуйста, ключевые требования и критерии «готово».",
    "Уточните, пожалуйста, сроки, ограничения и ответственных.",
]


def _as_list(value: Any) -> List[Any]:
    """Защитный перевод значения в список (None / не-список → [])."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def safe_review(error: Optional[str] = None) -> Dict[str, Any]:
    """Безопасный отчёт: валидная структура рецензии при любой ошибке (п.6 ТЗ).

    Поля могут быть пустыми, но не отсутствующими. needs_review=true,
    вопросы добираются до минимума 3 шаблонными вопросами.
    """
    questions = list(DEFAULT_REVIEW_QUESTIONS)
    while len(questions) < 3:
        questions.append("Уточните, пожалуйста, детали документа.")
    result: Dict[str, Any] = {
        "summary": "",
        "risks": [],
        "missing_requirements": [
            "Требуется уточнить содержание документа (см. вопросы к заказчику)."
        ],
        "questions_to_client": questions,
        "acceptance_criteria": [],
        "confidence": "low",
        "needs_review": True,
    }
    if error:
        result["error"] = error
    return result


# --------------------------------------------------------------------------- #
# Парсинг и валидация строгого JSON
# --------------------------------------------------------------------------- #
def parse_json_response(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Достать JSON-объект из ответа LLM (убирает ```json-обёртки и мусор).

    Возвращает (parsed_dict, None) или (None, "INVALID_JSON").
    """
    if not isinstance(text, str) or not text.strip():
        return None, "INVALID_JSON"

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    # Вырезаем первую { и последнюю } — в ответе может быть мусор вокруг JSON
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, "INVALID_JSON"

    candidate = cleaned[start:end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None, "INVALID_JSON"

    if not isinstance(data, dict):
        return None, "INVALID_JSON"
    return data, None


def _str_list(value: Any) -> List[str]:
    """Нормализация списка строк (строки лишних символов чисел отсекаются)."""
    items = _as_list(value)
    result: List[str] = []
    for item in items:
        if isinstance(item, str):
            item = item.strip()
        if item not in (None, ""):
            result.append(str(item))
    return result


def _empty_analysis(lines_count: int = 0) -> Dict[str, Any]:
    """Анализ «по умолчанию» на случай ошибки LLM (схема шага A)."""
    return {
        "document_type": "other",
        "purpose": "",
        "key_requirements": [],
        "detected_contradictions": [],
        "too_vague": False,
        "lines_count": lines_count,
    }


def _empty_report() -> Dict[str, Any]:
    """Рецензия «по умолчанию» на случай ошибки LLM (схема шага B)."""
    return {
        "summary": "",
        "risks": [],
        "missing_requirements": [],
        "questions_to_client": [],
        "acceptance_criteria": [],
        "confidence": "low",
    }
def validate_analysis(data: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Проверка схемы шага A (п.5 ТЗ) и нормализация под наши типы.

    Возвращает (normalized_analysis, errors). Ошибки не блокируют цепочку:
    невалидный ответ целиком → анализ по умолчанию + ["INVALID_JSON"].
    """
    errors: List[str] = []
    if not isinstance(data, dict):
        return _empty_analysis(), ["INVALID_JSON"]

    doc_type = data.get("document_type")
    if doc_type not in DOCUMENT_TYPES:
        doc_type = "other"

    purpose = data.get("purpose")
    purpose = purpose if isinstance(purpose, str) else ""

    too_vague_raw = data.get("too_vague")
    too_vague = bool(too_vague_raw) if isinstance(too_vague_raw, bool) else False

    try:
        lines_count = int(data.get("lines_count") or 0)
    except (TypeError, ValueError):
        lines_count = 0

    return {
        "document_type": doc_type,
        "purpose": purpose,
        "key_requirements": _str_list(data.get("key_requirements")),
        "detected_contradictions": _str_list(data.get("detected_contradictions")),
        "too_vague": too_vague,
        "lines_count": lines_count,
    }, errors


def validate_report(data: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Проверка схемы шага B (п.5 ТЗ) и нормализация.

    Невалидные/лишние элементы списков отбрасываются; критично лишь то, что
    data — это dict. При поломке — рецензия по умолчанию + ["INVALID_JSON"].
    """
    errors: List[str] = []
    if not isinstance(data, dict):
        return _empty_report(), ["INVALID_JSON"]

    summary = data.get("summary")
    summary = summary if isinstance(summary, str) else ""

    risks: List[Dict[str, str]] = []
    for item in _as_list(data.get("risks")):
        if not isinstance(item, dict):
            continue
        description = item.get("description")
        if not isinstance(description, str) or not description.strip():
            continue
        severity = item.get("severity") if item.get("severity") in SEVERITIES else "low"
        risks.append({"severity": severity, "description": description.strip()})

    confidence = data.get("confidence")
    if confidence not in CONFIDENCES:
        confidence = "low"

    return {
        "summary": summary.strip(),
        "risks": risks,
        "missing_requirements": _str_list(data.get("missing_requirements")),
        "questions_to_client": _str_list(data.get("questions_to_client")),
        "acceptance_criteria": _str_list(data.get("acceptance_criteria")),
        "confidence": confidence,
    }, errors
# --------------------------------------------------------------------------- #
# Вызовы LLM через langchain_module (мост genapi)
# --------------------------------------------------------------------------- #
def _invoke(llm: Any, system: str, user: str) -> str:
    """Одиночный вызов моделя (system + user) через LangChain-интерфейс."""
    from langchain_core.messages import HumanMessage, SystemMessage

    result = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return getattr(result, "content", str(result))


def build_llm(temperature: float):
    """LangChain-модель GenAPI: ``get_llm`` из langchain_module (мост ``genapi``).

    Настройки берутся из env (LLM_MODEL, LLM_MAX_TOKENS). Строгий JSON
    (response_format) включается опционально через LLM_JSON_MODE=1 — по
    умолчанию выключен: надёжность обеспечивают промпты и валидация в коде.
    """
    extra: Dict[str, Any] = {"max_tokens": settings.llm_max_tokens}
    if settings.llm_json_mode:
        extra["response_format"] = {"type": "json_object"}
    return get_llm(
        backend="genapi",
        model=settings.llm_model,
        temperature=temperature,
        **extra,
    )


# --------------------------------------------------------------------------- #
# Шаги A → B → C
# --------------------------------------------------------------------------- #
def run_step_a(llm: Any, text: str) -> Tuple[Dict[str, Any], List[str]]:
    """Шаг A — «Разбор документа»: строгий промежуточный JSON."""
    try:
        raw = _invoke(llm, SYSTEM_PROMPT_STEP_A, text)
    except Exception as exc:  # сеть/ключ/таймаут — не роняем сервис
        log.error("Шаг A: ошибка вызова LLM: %s", exc)
        return _empty_analysis(len(text.splitlines())), ["LLM_ERROR"]

    data, parse_error = parse_json_response(raw)
    if parse_error:
        log.warning("Шаг A: невалидный JSON от LLM: %r", raw[:400])
        return _empty_analysis(len(text.splitlines())), [parse_error]

    analysis, errors = validate_analysis(data)
    return analysis, errors


def run_step_b(llm: Any, text: str, analysis: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Шаг B — «Формирование рецензии»: вход = текст документа + разбор A."""
    context = json.dumps(analysis, ensure_ascii=False)
    user_prompt = (
        f"ТЕКСТ ДОКУМЕНТА:\n{text}\n\n"
        f"РАЗБОР ДОКУМЕНТА (JSON):\n{context}\n\n"
        f"Составь рецензию и верни строгий JSON по описанной схеме."
    )
    try:
        raw = _invoke(llm, SYSTEM_PROMPT_STEP_B, user_prompt)
    except Exception as exc:
        log.error("Шаг B: ошибка вызова LLM: %s", exc)
        return _empty_report(), ["LLM_ERROR"]

    data, parse_error = parse_json_response(raw)
    if parse_error:
        log.warning("Шаг B: невалидный JSON от LLM: %r", raw[:400])
        return _empty_report(), [parse_error]

    report, errors = validate_report(data)
    return report, errors


def decide_manual_review(
    analysis: Dict[str, Any],
    report: Dict[str, Any],
    errors: List[str],
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Шаг C — «Решение о ручной проверке» (детерминированные правила, п.6 ТЗ).

    Возвращает (report с needs_review, error_code). Приоритет причины:
    INVALID_JSON > CONTRADICTORY_INPUT > TOO_VAGUE_INPUT > LOW_CONFIDENCE.
    Вопросы добираются до минимума 3 шаблонными вопросами.
    """
    needs_review = False
    error: Optional[str] = None

    if errors:
        needs_review = True
        error = "INVALID_JSON" if "INVALID_JSON" in errors else errors[0]
    elif _as_list(analysis.get("detected_contradictions")):
        needs_review = True
        error = "CONTRADICTORY_INPUT"
    elif analysis.get("too_vague"):
        needs_review = True
        error = "TOO_VAGUE_INPUT"
    elif report.get("confidence") == "low":
        needs_review = True
        error = "LOW_CONFIDENCE"

    # Добор вопросов заказчику до минимума 3 (п.6 ТЗ)
    questions = list(_as_list(report.get("questions_to_client")))
    idx = 0
    while len(questions) < 3 and idx < len(DEFAULT_REVIEW_QUESTIONS):
        question = DEFAULT_REVIEW_QUESTIONS[idx]
        if question not in questions:
            questions.append(question)
        idx += 1

    report = dict(report)
    report["questions_to_client"] = questions
    report["needs_review"] = needs_review
    return report, error


# --------------------------------------------------------------------------- #
# Главная точка входа цепочки
# --------------------------------------------------------------------------- #
def run_chain(text: str) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[str]]:
    """Запуск цепочки A→B→C. Возвращает (report, analysis, error).

    Без GENAPI_KEY (или при ошибке инициализации) — безопасный отчёт с
    needs_review=true, чтобы сервис никогда не возвращал невалидный JSON.
    """
    if not settings.has_llm_key:
        return safe_review("NO_API_KEY"), {}, "NO_API_KEY"

    try:
        llm_a = build_llm(settings.llm_temp_analyze)
        llm_b = build_llm(settings.llm_temp_generate)
    except Exception as exc:
        log.error("Ошибка создания LLM: %s", exc)
        return safe_review("LLM_ERROR"), {}, "LLM_ERROR"

    # Шаг A — разбор документа
    analysis, errors_a = run_step_a(llm_a, text)

    # Шаг B — формирование рецензии (вход: текст + разбор A)
    report, errors_b = run_step_b(llm_b, text, analysis)

    # Шаг C — решение о ручной проверке и добор вопросов
    final_report, error = decide_manual_review(analysis, report, errors_a + errors_b)
    return final_report, analysis, error