"""Готовый клиент GenAPI (нативный API).

Пример:
    from modules.genapi import GenAPI
    g = GenAPI()                      # читает GENAPI_KEY из env
    out = g.chat([{"role": "user", "content": "Привет!"}])
    print(out["full_response"][-1]["content"])

env-переменные клиента читаются из общего окружения проекта (корневой .env).
"""

from .genapi_client import (
    GenAPI,
    GenAPIError,
    GenAPIGenerationError,
    GenAPIRequestError,
)

__all__ = ["GenAPI", "GenAPIError", "GenAPIGenerationError", "GenAPIRequestError"]