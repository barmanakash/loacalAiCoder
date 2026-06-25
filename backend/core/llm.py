"""
LocalCoder — LLM abstraction layer.
Supports: Ollama, llama.cpp (via OpenAI-compat endpoint).
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

import httpx

from backend.core.config import LLMProvider, settings
from backend.core.logging import get_logger
from backend.models.types import Message

log = get_logger(__name__)


class LLMBase(ABC):
    """Abstract LLM interface."""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str: ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        system: str = "",
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    async def is_available(self) -> bool: ...


# ── Ollama ────────────────────────────────────────────────────────────────────

class OllamaLLM(LLMBase):
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model    = settings.OLLAMA_MODEL
        self.embed_model = settings.EMBEDDING_MODEL
        self._client  = httpx.AsyncClient(timeout=settings.LLM_TIMEOUT)

    def _build_messages(self, messages: list[Message], system: str) -> list[dict]:
        out: list[dict] = []
        if system:
            out.append({"role": "system", "content": system})
        for m in messages:
            out.append({"role": m.role, "content": m.content})
        return out

    async def chat(
        self,
        messages: list[Message],
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages, system),
            "stream": False,
            "options": {
                "temperature": temperature or settings.LLM_TEMPERATURE,
                "num_predict": max_tokens or settings.LLM_MAX_TOKENS,
                "num_ctx": settings.LLM_CONTEXT_WINDOW,
            },
        }
        try:
            resp = await self._client.post(
                f"{self.base_url}/api/chat", json=payload
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as exc:
            log.error("ollama.chat.error", error=str(exc))
            raise

    async def stream(
        self,
        messages: list[Message],
        system: str = "",
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages, system),
            "stream": True,
            "options": {
                "temperature": temperature or settings.LLM_TEMPERATURE,
                "num_ctx": settings.LLM_CONTEXT_WINDOW,
            },
        }
        async with self._client.stream(
            "POST", f"{self.base_url}/api/chat", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if token := data.get("message", {}).get("content", ""):
                            yield token
                    except json.JSONDecodeError:
                        pass

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.embed_model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    async def is_available(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


# ── llama.cpp / OpenAI-compat ─────────────────────────────────────────────────

class LlamaCppLLM(LLMBase):
    """Works with llama.cpp server (--server flag) or any OpenAI-compat endpoint."""

    def __init__(self, base_url: str = "http://localhost:8080") -> None:
        self.base_url = base_url.rstrip("/")
        self._client  = httpx.AsyncClient(timeout=settings.LLM_TIMEOUT)

    def _build_messages(self, messages: list[Message], system: str) -> list[dict]:
        out = []
        if system:
            out.append({"role": "system", "content": system})
        for m in messages:
            out.append({"role": m.role, "content": m.content})
        return out

    async def chat(
        self,
        messages: list[Message],
        system: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        payload = {
            "messages": self._build_messages(messages, system),
            "temperature": temperature or settings.LLM_TEMPERATURE,
            "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
            "stream": False,
        }
        resp = await self._client.post(
            f"{self.base_url}/v1/chat/completions", json=payload
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def stream(
        self,
        messages: list[Message],
        system: str = "",
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "messages": self._build_messages(messages, system),
            "temperature": temperature or settings.LLM_TEMPERATURE,
            "stream": True,
        }
        async with self._client.stream(
            "POST", f"{self.base_url}/v1/chat/completions", json=payload
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                        if token := chunk["choices"][0]["delta"].get("content", ""):
                            yield token
                    except Exception:
                        pass

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.post(
            f"{self.base_url}/v1/embeddings",
            json={"input": text, "model": "text-embedding-ada-002"},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

    async def is_available(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}/v1/models", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


# ── Factory ───────────────────────────────────────────────────────────────────

def create_llm() -> LLMBase:
    if settings.LLM_PROVIDER == LLMProvider.OLLAMA:
        return OllamaLLM()
    if settings.LLM_PROVIDER == LLMProvider.LLAMA_CPP:
        return LlamaCppLLM()
    raise ValueError(f"Unknown LLM provider: {settings.LLM_PROVIDER}")


# Singleton
_llm_instance: LLMBase | None = None


def get_llm() -> LLMBase:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = create_llm()
    return _llm_instance
