# spec-reviewer — образ для запуска в контейнере (Python 3.12)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Зависимости — отдельным слоем (кэшируется при пересборке)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код проекта (секреты и БД исключены — см. .dockerignore)
COPY . .

# Порт сервиса (ТЗ: 8040)
EXPOSE 8040

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8040"]