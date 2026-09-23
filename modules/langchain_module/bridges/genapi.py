"""GenAPI bridge: адаптирует готовый клиент GenAPI к LangChain (BaseChatModel).

Готовый клиент живёт в ``modules.genapi`` (общий для всех частей проекта — не
только для LangChain). Импортируется напрямую; НЕ копируется внутрь
langchain_module.

Ответ GenAPI чата: ``{"status": "success", "full_response": [{"role": "assistant",
"content": "..."}, ...], ...}`` — текст берём из последнего элемента
``full_response``. Все дополнительные параметры (в т.ч. ``response_format`` для
строгого JSON) пробрасываются в ``chat(**params)``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult


def _to_dict_messages(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Конвертация LangChain-сообщений в dict-формат GenAPI (role/content)."""
    out: List[Dict[str, Any]] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            role = "system"
        elif isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        elif isinstance(m, ChatMessage):
            role = m.role
        else:
            role = "user"
        content = m.content
        if isinstance(content, list):
            text = ""
            for part in content:
                if isinstance(part, dict):
                    text += part.get("text", "")
                else:
                    text += str(part)
            content = text
        out.append({"role": role, "content": content})
    return out


def _genapi_client_class():
    """Готовый GenAPI-клиент проекта — единственный в ``modules.genapi``."""
    from modules.genapi import GenAPI

    return GenAPI


def _extract_text(result: Dict[str, Any]) -> str:
    """Последнее текстовое содержание полного ответа модели.

    Формат GenAPI: full_response = [{"index", "message": {"role", "content"}, ...}].
    Для совместимости поддерживаем и плоский формат [{"role", "content"}].
    """
    full = result.get("full_response") or []
    text = ""
    if isinstance(full, list):
        for item in full:
            if not isinstance(item, dict):
                continue
            # Вложенный формат OpenAI-style: item["message"]["content"]
            message = item.get("message")
            content = None
            if isinstance(message, dict):
                content = message.get("content")
            if not content:
                # Плоский формат: item["content"]
                content = item.get("content")
            if content:
                text = content
    return text


class GenAPIChatModel(BaseChatModel):
    """LangChain-чат-модель на базе готового GenAPI-клиента."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: int = 2048
    genapi_key: Optional[str] = None
    extra_params: Dict[str, Any] = {}

    @property
    def _llm_type(self) -> str:
        return "genapi"

    def _client(self):
        return _genapi_client_class()(api_key=self.genapi_key)

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        conv = _to_dict_messages(messages)
        params: Dict[str, Any] = dict(self.extra_params)
        params.setdefault("temperature", self.temperature)
        params.setdefault("max_tokens", self.max_tokens)
        if stop:
            params["stop"] = stop

        resp = self._client().chat(conv, task="CHAT", model=self.model, **params)
        if not isinstance(resp, dict):
            raise RuntimeError("GenAPI вернул поток вместо JSON (стриминг не используется)")
        text = _extract_text(resp)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    def with_params(self, **kwargs: Any) -> "GenAPIChatModel":
        """Возвращает копию с переопределёнными параметрами (self не меняется)."""
        import copy

        new = copy.copy(self)
        new.extra_params = {**self.extra_params, **kwargs}
        for key in ("model", "temperature", "max_tokens", "genapi_key"):
            if key in kwargs:
                setattr(new, key, kwargs[key])
        return new


class GenAPIEmbeddings(Embeddings):
    """Заглушка: эмбеддинги через GenAPI в этом проекте не используются (RAG выключен).

    Оставлена для полноты интерфейса langchain_module (get_embeddings). При
    расширении (если понадобится RAG) — реализовать через нативный API GenAPI.
    """

    model: str = "text-embedding-3-small"
    genapi_key: Optional[str] = None
    extra_params: Dict[str, Any] = {}

    def __init__(
        self,
        model: Optional[str] = None,
        genapi_key: Optional[str] = None,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Явный конструктор (в этой версии langchain_core Embeddings не генерирует __init__)."""
        if model is not None:
            self.model = model
        if genapi_key is not None:
            self.genapi_key = genapi_key
        if extra_params is not None:
            self.extra_params = extra_params

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError(
            "GenAPI embeddings не используются в spec-reviewer (RAG не требуется по ТЗ)."
        )

    def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError(
            "GenAPI embeddings не используются в spec-reviewer (RAG не требуется по ТЗ)."
        )