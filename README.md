# spec-reviewer — ИИ-рецензент документов / технических заданий

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED)](docker-compose.yml)

> Превращает «сырой текст» ТЗ в структурированный отчёт: **summary, риски, чего не хватает, вопросы заказчику, критерии приёмки, confidence**.  
> Честная метка **«требует проверки»** (`needs_review=true`) когда модель не уверена — никаких выдумок.

---

## 🎯 Проблема и ценность

**Проблема:** без рецензии ТЗ команды уезжают в переработки — риски, пробелы и вопросы заказчику всплывают поздно.

**Решение:** сервис за минуты выдаёт рецензию с рисками (severity), вопросами (≥3 при неопределённости) и критериями приёмки.  
**Результат:** рецензия за 5 мин вместо 45 мин руками → **~66 700 ₽ экономии на 100 ТЗ** (системный аналитик 1000 ₽/ч).

---

## 🚀 Быстрый старт

```bash
# 1. Клонировать
git clone <repo-url>
cd spec-reviewer

# 2. Окружение
cp .env.example .env   # вставьте GENAPI_KEY
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Запуск
uvicorn app.main:app --port 8040
# или Docker (рекомендуется):
docker compose up --build
```

Откройте **http://localhost:8040** — веб-панель с 3 вкладками: Документы, Рецензии, Просмотр.

---

## 📦 Стек

- **Backend:** FastAPI, SQLAlchemy 2.x, SQLite
- **LLM:** GenAPI (`gpt-4o-mini`), LangChain-слой (`modules/langchain_module`)
- **Качество:** цепочка A→B→C (temp 0.1 → 0.3), строгая валидация JSON, детерминированный шаг C
- **Аудит:** каждый вызов → `audit_runs` (action, input, output, status, error, duration_ms)
- **UI:** Vanilla JS + CSS (статика в `app/static/`)

---

## 🔌 API (7 эндпоинтов)

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/documents` | Создать документ |
| `GET` | `/documents` | Список документов |
| `POST` | `/documents/{id}/review` | Запустить рецензию |
| `GET` | `/reviews/{id}` | Карточка рецензии (блоки + сырой JSON) |
| `GET` | `/reviews` | Список рецензий |
| `POST` | `/ai/review` | ИИ-рецензия без сохранения |
| `GET` | `/health` | Healthcheck (Docker) |

Примеры `curl` — в разделе «Примеры запросов» ниже.

---

## 🧪 Тесты и качество

```bash
# Полный прогон (18 non-LLM + 3 live LLM тестов)
python ../tests/run_api_tests.py --round 1
# → HWV/tests/data/results/round_1.json + HWV/tests/REPORT.md
```

**Набор:** 10 ТЗ в `tests/data/specs.jsonl` (6 нормальных, 2 сырых, 2 противоречивых).  
**Результат:** 10/10 PASS, 4 с `needs_review=true` (тесты 7–10).

---

## 📊 Архитектура

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Веб-панель │────▶│   FastAPI   │────▶│   SQLite    │
│  (3 таба)   │     │  (7 эндп.)  │     │  + audit    │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │ LLM Chain   │
                    │  A→B→C      │
                    │ (GenAPI)    │
                    └─────────────┘
```

---

## 📁 Структура репозитория

```
spec-reviewer/
├── app/                    # FastAPI приложение
│   ├── main.py             # 7 эндпоинтов + аудит
│   ├── ai_chain.py         # цепочка A→B→C
│   ├── prompts.py          # системные промпты
│   ├── services.py         # бизнес-логика + БД
│   ├── models.py           # SQLAlchemy модели
│   ├── schemas.py          # Pydantic схемы
│   ├── config.py           # настройки из .env
│   ├── db.py               # сессии БД
│   └── static/             # веб-панель (index.html, app.js, app.css)
├── modules/                # переиспользуемые модули
│   ├── logger.py           # ротация логов 6ч/3дня
│   ├── error_handler.py    # глобальный обработчик ошибок
│   ├── genapi/             # клиент GenAPI (единственная точка доступа к LLM)
│   └── langchain_module/   # LangChain-слой поверх genapi
├── tests/                  # тесты (ВНЕ проекта, в HWV/tests/)
│   ├── run_api_tests.py
│   ├── data/specs.jsonl
│   ├── REPORT.md           # отчёт по тестам
│   ├── REPORT2.md          # отчёт по шаблону курса
│   └── DELIVERY_CHECKLIST.md
├── demo/                   # сценарий демо + тестовые ТЗ
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md               # этот файл
```

---

## ⚙️ Переменные окружения (`.env`)

| Переменная | Обязательна | Описание |
|---|---|---|
| `GENAPI_KEY` | **Да** | Ключ GenAPI (только в `.env`, не в `.env.example`) |
| `APP_HOST` / `APP_PORT` | Нет | `0.0.0.0` / `8040` |
| `DATABASE_PATH` | Нет | `./app.db` |
| `MAX_DOC_TEXT_LENGTH` | Нет | `30000` |
| `LLM_TEMP_ANALYZE` / `LLM_TEMP_GENERATE` | Нет | `0.1` / `0.3` |
| `LLM_MAX_TOKENS` | Нет | `2048` |
| `LOG_LEVEL` | Нет | `INFO` |

---

## 📋 Примеры запросов (curl)

```bash
# 1. Создать документ
curl -X POST http://localhost:8040/documents \
  -H "Content-Type: application/json" \
  -d '{"title":"ТЗ на форму заявки","text":"Разработать форму заявки с полями имя и телефон. Срок — 2 недели."}'

# 2. Запустить рецензию
curl -X POST http://localhost:8040/documents/1/review

# 3. ИИ-рецензия без сохранения
curl -X POST http://localhost:8040/ai/review \
  -H "Content-Type: application/json" \
  -d '{"text":"Нужен сайт. Сделайте красиво."}'

# 4. Список рецензий и карточка
curl http://localhost:8040/reviews
curl http://localhost:8040/reviews/1

# 5. Healthcheck
curl http://localhost:8040/health
```

---

## 🔍 Аудит и логи

```bash
# Посмотреть audit_runs (последние 20)
python -c "
from app.db import SessionLocal
from app.models import AuditRun
db = SessionLocal()
for a in db.query(AuditRun).order_by(AuditRun.id.desc()).limit(20):
    print(a.id, a.action, a.status, a.error, a.duration_ms)
"

# Логи в logs/app.<YYYYMMDD-HH>.log (ротация 6ч, хранение 3 дня)
```

---

## 🛡 Безопасность

- `.env` и `*.db` в `.gitignore` / `.dockerignore`
- Секреты **только** в `.env` (не коммитятся)
- Работа без ключа: понятная ошибка `NO_API_KEY` + безопасный отчёт

---

## 🗺 План развития

- [ ] Подписка/лимиты и страница тарифов
- [ ] Загрузка `.docx/.pdf` вместо только текста
- [ ] Экспорт PDF, сравнение рецензий, чек-лист приёмки
- [ ] Аналитика: какие ТЗ чаще «требуют проверки»
- [ ] Выбор модели в UI (вторая модель через `LC_LLM_BACKEND`)
- [ ] Кэширование повторных рецензий

---