# -*- coding: utf-8 -*-
"""Универсальный клиент GenAPI (нативный API, агрегатор 180+ нейросетей).

Код на английском, комментарии — на русском. Кодировка UTF-8.

Модуль прячет за собой всю работу с HTTP, очередью (poll) и SSE-стримом.
Управляется через env-переменные (см. корневой .env проекта).

Используется ТОЛЬКО нативный API:  https://api.gen-api.ru
Прокси (proxy.gen-api.ru) не применяется как основной — он лишь OpenAI-совместимая
обёртка для IDE/плагинов. Чат идёт через нативный POST /networks/{slug} с полем
`messages`. Webhook не используется — только надёжный опрос через wait().
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterator, List, Optional, Union

import requests

# Базовый URL нативного API (можно переопределить через env GENAPI_BASE_URL)
DEFAULT_BASE_URL = "https://api.gen-api.ru"
# Только для опционального list_models() (read-only)
DEFAULT_PROXY_URL = "https://proxy.gen-api.ru"

# Маппинг задачи на env-переменную с моделью по умолчанию
TASK_ENV = {
    "CHAT": "GENAPI_MODEL_CHAT",
    "IMAGE": "GENAPI_MODEL_IMAGE",
    "VIDEO": "GENAPI_MODEL_VIDEO",
    "AUDIO": "GENAPI_MODEL_AUDIO",
    "FILE": "GENAPI_MODEL_FILE",
    "3D": "GENAPI_MODEL_3D",
    "EMBEDDING": "GENAPI_MODEL_EMBEDDING",
}


# Параметры по задачам, которые модуль читает из env и подставляет в тело запроса
# по умолчанию (их можно переопределить явно через **params).
# Формат: задача -> список (ENV_VAR, ключ_в_теле_API, тип: float|int|str|bool)
# Полное описание каждого параметра и какие провайдеры его принимают — в manual §12.
TASK_ENV_PARAMS = {
    "CHAT": [
        ("GENAPI_CHAT_TEMPERATURE", "temperature", "float"),
        ("GENAPI_CHAT_MAX_TOKENS", "max_tokens", "int"),
        ("GENAPI_CHAT_TOP_P", "top_p", "float"),
        ("GENAPI_CHAT_FREQUENCY_PENALTY", "frequency_penalty", "float"),
        ("GENAPI_CHAT_PRESENCE_PENALTY", "presence_penalty", "float"),
        ("GENAPI_CHAT_REASONING_EFFORT", "reasoning_effort", "str"),
        ("GENAPI_CHAT_N", "n", "int"),
    ],
    "IMAGE": [
        ("GENAPI_IMAGE_SIZE", "size", "str"),
        ("GENAPI_IMAGE_QUALITY", "quality", "str"),
        ("GENAPI_IMAGE_N", "n", "int"),
        ("GENAPI_IMAGE_STYLE", "style", "str"),
        ("GENAPI_IMAGE_OUTPUT_FORMAT", "output_format", "str"),
        ("GENAPI_IMAGE_SEED", "seed", "int"),
        ("GENAPI_IMAGE_GUIDANCE", "guidance", "float"),
    ],
    "VIDEO": [
        ("GENAPI_VIDEO_DURATION", "duration", "int"),
        ("GENAPI_VIDEO_RESOLUTION", "resolution", "str"),
        ("GENAPI_VIDEO_ASPECT_RATIO", "aspect_ratio", "str"),
        ("GENAPI_VIDEO_SEED", "seed", "int"),
        ("GENAPI_VIDEO_NEGATIVE_PROMPT", "negative_prompt", "str"),
    ],
    "TTS": [
        ("GENAPI_TTS_VOICE", "voice", "str"),
        ("GENAPI_TTS_SPEED", "speed", "float"),
        ("GENAPI_TTS_INSTRUCTIONS", "instructions", "str"),
        ("GENAPI_TTS_RESPONSE_FORMAT", "response_format", "str"),
    ],
    "STT": [
        ("GENAPI_STT_LANGUAGE", "language", "str"),
        ("GENAPI_STT_RESPONSE_FORMAT", "response_format", "str"),
        ("GENAPI_STT_PROMPT", "prompt", "str"),
    ],
    "EMBEDDING": [
        ("GENAPI_EMBEDDING_DIMENSIONS", "dimensions", "int"),
        ("GENAPI_EMBEDDING_ENCODING_FORMAT", "encoding_format", "str"),
    ],
    "FILE": [],
    "3D": [],
}


# Каталог ИИ-функций GenAPI (https://gen-api.ru/functions).
# function_id для call_function() = slug (подтверждено на страницах /function/<slug>/api).
# implementation — выбор варианта модели (если пусто, сервер берёт дефолт).
# kind — тип входа: image | text | audio | file.
FUNCTIONS = {
    # --- Изображения ---
    "remove-background": {"desc": "Удаление фона", "kind": "image", "required": ["image"],
                          "implementations": ["modnet", "birefnet", "bria"]},
    "replace-background": {"desc": "Смена фона по prompt", "kind": "image", "required": ["image", "prompt"],
                           "implementations": ["sdxl-controlnet", "bria"]},
    "remove-object": {"desc": "Удаление объекта (нужна mask)", "kind": "image", "required": ["image", "mask"],
                      "implementations": ["lama", "bria"]},
    "outpainting": {"desc": "Расширение за границы (outpainting)", "kind": "image", "required": ["image", "prompt"],
                    "implementations": ["outpainting-v1"]},
    "sketch-to-image": {"desc": "Эскиз в изображение", "kind": "image", "required": ["image", "prompt"],
                        "implementations": ["sdxl-lora"]},
    "retoucher": {"desc": "Ретушь фото", "kind": "image", "required": ["image"],
                  "implementations": ["retoucher-v1"]},
    "blend": {"desc": "Смешение картинок", "kind": "image", "required": ["image"],
              "implementations": ["blend-v1"]},
    "product-shot": {"desc": "Фото товара", "kind": "image", "required": ["image"],
                     "implementations": ["bria"]},
    "replace-item": {"desc": "Замена предмета", "kind": "image", "required": ["image", "prompt"],
                     "implementations": ["bria"]},
    "describe": {"desc": "Картинка -> промпт", "kind": "image", "required": ["image"],
                 "implementations": ["describe-v1"]},
    "advertisement-by-picture": {"desc": "Объявление по картинке", "kind": "image", "required": ["image"],
                                 "implementations": ["chat-gpt-4-turbo"]},
    "advertising-text-by-picture": {"desc": "Рекламный текст по картинке", "kind": "image", "required": ["image"],
                                    "implementations": ["chat-gpt-4-turbo"]},
    "product-description-by-picture": {"desc": "Описание товара по картинке", "kind": "image", "required": ["image"],
                                       "implementations": ["chat-gpt-4-turbo"]},
    # --- Текст ---
    "rewrite": {"desc": "Рерайт текста", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-article": {"desc": "Генерация статьи", "kind": "text", "required": ["title"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "expand-text": {"desc": "Расширение текста", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-advertisement": {"desc": "Генерация объявления", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-advertising-text": {"desc": "Рекламный текст", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-analogy": {"desc": "Генератор аналогий", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-business-plan": {"desc": "Бизнес-план", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-content-plan": {"desc": "Контент-план", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-contents": {"desc": "Оглавление по заголовку", "kind": "text", "required": ["title"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-email": {"desc": "Email-письма", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-felicitation": {"desc": "Поздравления", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-ideas": {"desc": "Генератор идей", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-name": {"desc": "Креативное название", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-paragraph": {"desc": "Параграф текста", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-post": {"desc": "Пост для соцсетей", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-product-description": {"desc": "Описание товара", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-resume": {"desc": "Резюме/биография", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-review": {"desc": "Отзывы", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-seo-description": {"desc": "SEO-description", "kind": "text", "required": ["title"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-song-text": {"desc": "Текст песен", "kind": "text", "required": ["song_name", "style", "add_chords"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-story": {"desc": "Рассказы", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-tests": {"desc": "Генератор тестов", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "generate-verse": {"desc": "Стихотворения", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "improve-text": {"desc": "Улучшить текст", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    "shorten-text": {"desc": "Сжатие текста", "kind": "text", "required": ["text"], "implementations": ["chat-gpt-4-turbo", "claude"]},
    # --- Аудио ---
    "analyze-call": {"desc": "Анализ звонка", "kind": "audio", "required": ["audio"], "implementations": ["claude"]},
    # --- Файлы (нужен PPTX; в тестах не гоняем) ---
    "generate-presentation": {"desc": "Генерация презентации (PPTX)", "kind": "file", "required": ["file"], "implementations": ["premium"]},
    "edit-presentation-slide": {"desc": "Редактирование слайда (PPTX)", "kind": "file", "required": ["file"], "implementations": ["premium"]},
}


class GenAPIError(Exception):
    """Базовая ошибка клиента GenAPI."""


class GenAPIRequestError(GenAPIError):
    """Ошибка HTTP-запроса к API (невалидный ответ, 401, 404 и т.п.)."""


class GenAPIGenerationError(GenAPIError):
    """Генерация завершилась со статусом error."""


class GenAPI:
    """Клиент GenAPI.

    Пример:
        from modules.genapi import GenAPI
        g = GenAPI()                      # читает GENAPI_KEY из env
        print(g.chat([{"role": "user", "content": "Привет!"}]))
        g.image("закат на море", model="flux-2")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        proxy_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        # Ключ: явно переданный > env
        self.api_key = api_key or os.environ.get("GENAPI_KEY")
        if not self.api_key:
            raise GenAPIError(
                "Не задан GENAPI_KEY (передайте api_key=... или положите в env GENAPI_KEY)"
            )
        self.base_url = (base_url or os.environ.get("GENAPI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.proxy_url = (proxy_url or os.environ.get("GENAPI_PROXY_URL") or DEFAULT_PROXY_URL).rstrip("/")
        # Таймаут сетевого запроса (не путать с poll-timeout)
        self.http_timeout = timeout or self._int("GENAPI_HTTP_TIMEOUT", 60)

    # ------------------------------------------------------------------ #
    # Внутренние хелперы чтения env
    # ------------------------------------------------------------------ #
    @staticmethod
    def _is_off(value: Optional[str]) -> bool:
        """Считаем 'off'/'false'/'0'/пусто — выключенным."""
        return value is None or str(value).strip().lower() in ("", "off", "false", "0", "none")

    def _env(self, name: str, default: Optional[str] = None) -> Optional[str]:
        return os.environ.get(name, default)

    def _int(self, name: str, default: int) -> int:
        v = os.environ.get(name)
        if v is None or v == "":
            return default
        try:
            return int(v)
        except ValueError:
            return default

    def _float(self, name: str, default: float) -> float:
        v = os.environ.get(name)
        if v is None or v == "":
            return default
        try:
            return float(v)
        except ValueError:
            return default

    def _flag(self, name: str, default: bool = False) -> bool:
        v = os.environ.get(name)
        if v is None:
            return default
        return not self._is_off(v)

    def _model_for(self, task: str) -> str:
        """Возвращает slug модели из env для задачи, либо кидает понятную ошибку."""
        env_name = TASK_ENV.get(task.upper(), task)
        model = os.environ.get(env_name)
        if self._is_off(model):
            raise GenAPIError(
                f"Для задачи '{task}' не задана модель: положите slug в env {env_name} "
                f"(или передайте model=... явно)"
            )
        return model  # type: ignore[return-value]

    def _merge_env(self, task: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Подставляет в payload параметры задачи из env (если заданы и не выключены).

        Явные **params, переданные в метод, имеют приоритет (уже лежат в payload).
        Модуль не знает про конкретные модели — он честно шлёт задокументированные
        в manual §12 параметры; какие из них примет конкретная модель, решает сервер.
        """
        for env, key, kind in TASK_ENV_PARAMS.get(task, []):
            if key in payload:
                continue
            raw = os.environ.get(env)
            if raw is None or self._is_off(raw):
                continue
            if kind == "int":
                payload[key] = self._int(env, 0)
            elif kind == "float":
                payload[key] = self._float(env, 0.0)
            elif kind == "bool":
                payload[key] = self._flag(env)
            else:
                payload[key] = raw
        return payload

    # ------------------------------------------------------------------ #
    # Низкоуровневые HTTP-методы
    # ------------------------------------------------------------------ #
    def _headers(self, content_type_json: bool = True) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if content_type_json:
            headers["Content-Type"] = "application/json"
        return headers

    def _post_network(self, network_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Сырой POST на /networks/{slug}. Возвращает JSON ответа (с полем id)."""
        url = f"{self.base_url}/api/v1/networks/{network_id}"
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=self.http_timeout)
        except requests.RequestException as exc:
            raise GenAPIRequestError(f"Сетевая ошибка при POST {url}: {exc}") from exc
        return self._parse(resp)

    def _post_function(self, function_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Сырой POST на /functions/{id}."""
        url = f"{self.base_url}/api/v1/functions/{function_id}"
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=self.http_timeout)
        except requests.RequestException as exc:
            raise GenAPIRequestError(f"Сетевая ошибка при POST {url}: {exc}") from exc
        return self._parse(resp)

    def _get_result(self, request_id: Union[int, str]) -> Dict[str, Any]:
        """Сырой GET результата генерации по id (поллинг)."""
        url = f"{self.base_url}/api/v1/request/get/{request_id}"
        try:
            resp = requests.get(url, headers=self._headers(content_type_json=False), timeout=self.http_timeout)
        except requests.RequestException as exc:
            raise GenAPIRequestError(f"Сетевая ошибка при GET {url}: {exc}") from exc
        return self._parse(resp)

    @staticmethod
    def _parse(resp: "requests.Response") -> Dict[str, Any]:
        if resp.status_code == 401:
            raise GenAPIRequestError("401 — неавторизован (неверный GENAPI_KEY)")
        if resp.status_code == 404:
            raise GenAPIRequestError("404 — генерация/модель не найдена")
        if not resp.ok:
            raise GenAPIRequestError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise GenAPIRequestError(f"Невалидный JSON в ответе: {resp.text[:500]}") from exc

    # ------------------------------------------------------------------ #
    # Опрос результата (poll)
    # ------------------------------------------------------------------ #
    def wait(
        self,
        request_id: Union[int, str],
        *,
        timeout: Optional[int] = None,
        interval: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Опрашивает GET /request/get/{id} до success/error.

        timeout — макс. секунд ожидания (env GENAPI_POLL_TIMEOUT, по умолч. 300).
        interval — секунды между опросами (env GENAPI_POLL_INTERVAL, по умолч. 2).
        Возвращает финальный JSON результата.
        """
        if timeout is None:
            timeout = self._int("GENAPI_POLL_TIMEOUT", 300)
        if interval is None:
            interval = self._int("GENAPI_POLL_INTERVAL", 2)

        deadline = time.monotonic() + timeout
        last: Dict[str, Any] = {}
        while True:
            last = self._get_result(request_id)
            status = last.get("status")
            if status == "success":
                return last
            if status == "error":
                raise GenAPIGenerationError(
                    f"Генерация {request_id} завершилась ошибкой: {last.get('full_response') or last.get('result')}"
                )
            if time.monotonic() >= deadline:
                raise GenAPIError(f"Таймаут ожидания генерации {request_id} (>{timeout}s), статус: {status}")
            time.sleep(interval)

    # ------------------------------------------------------------------ #
    # Отправка и «подай-и-жди»
    # ------------------------------------------------------------------ #
    def generate(self, network_id: str, *, task: Optional[str] = None, **params: Any) -> Dict[str, Any]:
        """Отправляет генерацию на /networks/{slug} и возвращает сырой ответ (с id).

        Не дожидается результата (для синхронного/стрим-режимов ответ уже внутри).
        Для ожидания используйте run() или wait(ответ['id']).
        """
        resp = self._post_network(network_id, params)
        # GenAPI у асинхронных сетей возвращает request_id, а не id — нормализуем.
        if "id" not in resp and "request_id" in resp:
            resp["id"] = resp["request_id"]
        return resp

    def run(self, network_id: str, *, task: Optional[str] = None, **params: Any) -> Dict[str, Any]:
        """Удобное «подай и дождись»: generate + poll через wait().

        Если в params стоит is_sync=True и сервер вернул success — возвращает сразу.
        """
        resp = self._post_network(network_id, params)
        # GenAPI у асинхронных сетей возвращает request_id, а не id — нормализуем.
        if "id" not in resp and "request_id" in resp:
            resp["id"] = resp["request_id"]
        status = resp.get("status")
        if status in ("success", "error"):
            if status == "error":
                raise GenAPIGenerationError(f"Генерация {resp.get('id')} завершилась ошибкой")
            return resp
        request_id = resp.get("id")
        if request_id is None:
            raise GenAPIError(f"В ответе нет id генерации: {resp}")
        return self.wait(request_id)

    # ------------------------------------------------------------------ #
    # Чат (нативный /networks/{slug} с messages)
    # ------------------------------------------------------------------ #
    def _chat_payload(self, messages: List[Dict[str, Any]], **params: Any) -> Dict[str, Any]:
        """Собирает тело чата: env-параметры по умолчанию + явные params (приоритет)."""
        payload: Dict[str, Any] = {"messages": messages}

        # Общие чат-параметры из env (temperature, max_tokens, top_p, ...)
        self._merge_env("CHAT", payload)

        # Специфичные флаги чата (вкл/выкл и бюджеты рассуждений)
        if "translate_input" not in params and self._flag("GENAPI_TRANSLATE_INPUT", False):
            payload["translate_input"] = True
        if "thinking" not in params and self._flag("GENAPI_CHAT_THINKING", False):
            payload["thinking"] = True
        if "thinking_budget" not in params:
            tb = os.environ.get("GENAPI_CHAT_THINKING_BUDGET")
            if tb and not self._is_off(tb):
                payload["thinking_budget"] = self._int("GENAPI_CHAT_THINKING_BUDGET", 0)
        # stream по умолчанию из env (только если не задан явно)
        if "stream" not in params and self._flag("GENAPI_CHAT_STREAM", False):
            payload["stream"] = True

        payload.update(params)
        return payload

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        task: str = "CHAT",
        **params: Any,
    ) -> Union[Dict[str, Any], Iterator[str]]:
        """Нативный чат через POST /networks/{slug} с полем messages.

        model — slug модели (по умолч. из env GENAPI_MODEL_CHAT).
        Поддерживает vision/files/tools/reasoning как параметры.
        Если stream=True — возвращает генератор текстовых кусков (SSE),
        иначе — финальный JSON результата (как run()).
        """
        network_id = model or self._model_for(task)
        payload = self._chat_payload(messages, **params)

        if payload.get("stream"):
            return self._stream_chat(network_id, payload)

        return self.run(network_id, task=task, **payload)

    def _stream_chat(self, network_id: str, payload: Dict[str, Any]) -> Iterator[str]:
        """SSE-стрим чата: yield-ит текстовые дельты по мере поступления."""
        url = f"{self.base_url}/api/v1/networks/{network_id}"
        try:
            with requests.post(
                url, headers=self._headers(), json=payload, stream=True, timeout=self.http_timeout
            ) as resp:
                if resp.status_code == 401:
                    raise GenAPIRequestError("401 — неавторизован (неверный GENAPI_KEY)")
                if not resp.ok:
                    raise GenAPIRequestError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_raw = line[len("data:"):].strip()
                    if data_raw == "[DONE]":
                        break
                    try:
                        data = json.loads(data_raw)
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
        except requests.RequestException as exc:
            raise GenAPIRequestError(f"Сетевая ошибка при stream POST {url}: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Обёртки по типам генераций (каждый резолвит модель из env)
    # ------------------------------------------------------------------ #
    def image(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        **params: Any,
    ) -> Dict[str, Any]:
        """Генерация изображения. model по умолч. из env GENAPI_MODEL_IMAGE."""
        network_id = model or self._model_for("IMAGE")
        payload: Dict[str, Any] = {"prompt": prompt}
        if negative_prompt is not None:
            payload["negative_prompt"] = negative_prompt
        self._merge_env("IMAGE", payload)
        # quality/style/output_format — специфичны для DALL·E. У Midjourney quality=1/2/4
        # (1 — самый дешёвый) и нет style; у Flux/NanoBanana другие правила. Чтобы не
        # слать несовместимые параметры:
        #   - DALL·E:      оставляем quality/style/output_format
        #   - Midjourney:  оставляем только quality (число 1/2/4), style/output_format убираем
        #   - остальные (Flux, Nano Banana, ...): убираем все три
        fam = network_id.lower()
        if "dall" in fam:
            drop = []
        elif "midjourney" in fam:
            drop = ["style", "output_format"]
        else:
            drop = ["quality", "style", "output_format"]
        for k in drop:
            payload.pop(k, None)
        payload.update(params)
        return self.run(network_id, task="IMAGE", **payload)

    def video(self, prompt: Optional[str] = None, *, model: Optional[str] = None, **params: Any) -> Dict[str, Any]:
        """Генерация видео. model по умолч. из env GENAPI_MODEL_VIDEO.

        Поле запроса (чаще `prompt`, но у конкретной модели может быть другое,
        напр. `text`) передаётся через prompt= или **params — ничего не придумывается,
        шлём только то, что дал вызывающий.
        """
        network_id = model or self._model_for("VIDEO")
        payload: Dict[str, Any] = {}
        if prompt is not None:
            payload["prompt"] = prompt
        self._merge_env("VIDEO", payload)
        payload.update(params)
        return self.run(network_id, task="VIDEO", **payload)

    def audio(self, prompt: Optional[str] = None, *, model: Optional[str] = None, **params: Any) -> Dict[str, Any]:
        """Генерация аудио (TTS/музыка/речь). model по умолч. из env GENAPI_MODEL_AUDIO.

        Поле запроса передаётся через prompt= или **params (напр. text= для TTS).
        """
        network_id = model or self._model_for("AUDIO")
        # TTS (есть prompt) и STT (передан файл) используют разные наборы env-параметров
        sub = "TTS" if prompt is not None else "STT"
        payload: Dict[str, Any] = {}
        if prompt is not None:
            payload["prompt"] = prompt
        self._merge_env(sub, payload)
        payload.update(params)
        return self.run(network_id, task="AUDIO", **payload)

    def file_gen(self, prompt: Optional[str] = None, *, model: Optional[str] = None, **params: Any) -> Dict[str, Any]:
        """Генерация файла. model по умолч. из env GENAPI_MODEL_FILE.

        Поле запроса передаётся через prompt= или **params.
        """
        network_id = model or self._model_for("FILE")
        payload: Dict[str, Any] = {}
        if prompt is not None:
            payload["prompt"] = prompt
        self._merge_env("FILE", payload)
        payload.update(params)
        return self.run(network_id, task="FILE", **payload)

    def gen_3d(self, prompt: Optional[str] = None, *, model: Optional[str] = None, **params: Any) -> Dict[str, Any]:
        """Генерация 3D. model по умолч. из env GENAPI_MODEL_3D.

        Поле запроса передаётся через prompt= или **params.
        """
        network_id = model or self._model_for("3D")
        payload: Dict[str, Any] = {}
        if prompt is not None:
            payload["prompt"] = prompt
        self._merge_env("3D", payload)
        payload.update(params)
        return self.run(network_id, task="3D", **payload)

    def embedding(self, text: str, *, model: Optional[str] = None, **params: Any) -> Dict[str, Any]:
        """Эмбеддинг текста. model по умолч. из env GENAPI_MODEL_EMBEDDING
        (иначе реальный slug 'text-embedding-3-small' — универсальный 'embeddings'
        GenAPI не отдаёт, отсюда 404 при использовании заглушки)."""
        network_id = model or os.environ.get("GENAPI_MODEL_EMBEDDING") or "text-embedding-3-small"
        payload: Dict[str, Any] = {"input": text}
        self._merge_env("EMBEDDING", payload)
        payload.update(params)
        return self.run(network_id, task="EMBEDDING", **payload)

    # ------------------------------------------------------------------ #
    # ИИ-функции
    # ------------------------------------------------------------------ #
    @staticmethod
    def _impl_env_name(function_id: str) -> str:
        """Имя per-function env-переменной для выбора реализации, напр. GENAPI_IMPL_REMOVE_BACKGROUND."""
        return "GENAPI_IMPL_" + function_id.upper().replace("-", "_")

    def available_implementations(self, function_id: str) -> List[str]:
        """Возвращает список допустимых реализаций (slug моделей) для функции.

        Пустой список => выбор модели не задокументирован (сервер выберет сам при
        implementation="default"). Список берётся из FUNCTIONS (реальные slug со страниц gen-api.ru).
        """
        spec = FUNCTIONS.get(function_id)
        return list(spec.get("implementations", [])) if spec else []

    def selectable_functions(self) -> List[str]:
        """Функции, у которых есть выбор модели (implementation не пуст)."""
        return [fid for fid, spec in FUNCTIONS.items() if spec.get("implementations")]

    def list_functions(self) -> Dict[str, Dict[str, Any]]:
        """Каталог функций (slug -> desc/kind/required/implementations) для справки."""
        return {fid: {
            "desc": spec.get("desc"),
            "kind": spec.get("kind"),
            "required": spec.get("required", []),
            "implementations": list(spec.get("implementations", [])),
        } for fid, spec in FUNCTIONS.items()}

    def _impl_for(self, function_id: str, implementation: Optional[str]) -> str:
        """Резолвит, какую реализацию (модель) передать в API, с валидацией.

        Приоритет:
          1. явный аргумент implementation= (кроме "default"/None)
          2. env GENAPI_IMPL_<FUNCTION> (per-function)
          3. первая известная реализация из FUNCTIONS (если задокументирована)
          4. "default" — сервер выберет сам

        Если реализация не входит в известный список FUNCTIONS — кидает понятную ошибку
        (регуляция: нельзя передать случайный/невалидный slug модели).
        """
        known = self.available_implementations(function_id)
        chosen = None
        if implementation and implementation != "default":
            chosen = implementation
        else:
            env_val = os.environ.get(self._impl_env_name(function_id))
            if env_val and not self._is_off(env_val):
                chosen = env_val
        if chosen is None:
            return known[0] if known else "default"
        if known and chosen not in known:
            raise GenAPIError(
                f"Функция '{function_id}': implementation '{chosen}' недопустим. "
                f"Допустимые: {known} (либо задайте валидный через env "
                f"{self._impl_env_name(function_id)}, либо implementation=)"
            )
        return chosen

    def call_function(
        self,
        function_id: str,
        *,
        implementation: Optional[str] = None,
        **params: Any,
    ) -> Dict[str, Any]:
        """Вызов ИИ-функции: POST /functions/{id} + ожидание результата.

        implementation — slug модели (реализации). Если не задан, резолвится через
        _impl_for(): явный аргумент > env GENAPI_IMPL_<FUNCTION> > первая из FUNCTIONS > "default".
        Все допустимые варианты — в available_implementations(function_id).
        """
        impl = self._impl_for(function_id, implementation)
        payload: Dict[str, Any] = {"implementation": impl}
        payload.update(params)
        resp = self._post_function(function_id, payload)
        status = resp.get("status")
        if status in ("success", "error"):
            if status == "error":
                raise GenAPIGenerationError(f"Функция {function_id} завершилась ошибкой")
            return resp
        request_id = resp.get("id")
        if request_id is None:
            raise GenAPIError(f"В ответе функции нет id: {resp}")
        return self.wait(request_id)

    def function(self, function_id: str, *, implementation: Optional[str] = None, **params: Any) -> Dict[str, Any]:
        """Псевдоним для call_function() (читается понятнее: g.function('remove-background', ...)).

        function_id — slug функции из FUNCTIONS (совпадает с API-идентификатором).
        """
        return self.call_function(function_id, implementation=implementation, **params)

    # ------------------------------------------------------------------ #
    # Опционально: список моделей (read-only через прокси)
    # ------------------------------------------------------------------ #
    def list_models(self) -> List[Dict[str, Any]]:
        """Возвращает список моделей (OpenAI-формат) через proxy.gen-api.ru/v1/models.

        Только read-only, для справки. Основной код прокси не использует.
        """
        url = f"{self.proxy_url}/v1/models"
        try:
            resp = requests.get(url, headers=self._headers(content_type_json=False), timeout=self.http_timeout)
        except requests.RequestException as exc:
            raise GenAPIRequestError(f"Сетевая ошибка при GET {url}: {exc}") from exc
        data = self._parse(resp)
        return data.get("data", [])


__all__ = ["GenAPI", "GenAPIError", "GenAPIRequestError", "GenAPIGenerationError"]
