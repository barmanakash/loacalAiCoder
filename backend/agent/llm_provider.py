"""
LLM Provider abstraction layer.
Supports Ollama (primary), llama.cpp, and OpenAI-compatible APIs.
All inference stays local — no cloud calls.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

import httpx

from models.schemas import LLMConfig

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def complete(self, prompt: str, system: str = "") -> str:
        pass

    @abstractmethod
    async def stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass


class OllamaProvider(BaseLLMProvider):
    """
    Ollama local inference provider.
    Supports Qwen2.5-Coder, DeepSeek-Coder, Llama, and any Ollama model.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    async def complete(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
                "num_ctx": self.config.context_window,
            }
        }

        try:
            resp = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error("Ollama HTTP error: %s", e)
            raise RuntimeError(f"LLM request failed: {e.response.status_code}")
        except Exception as e:
            logger.error("Ollama error: %s", e)
            raise RuntimeError(f"LLM unavailable: {e}")

    async def stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            }
        }

        async with self.client.stream(
            "POST", f"{self.base_url}/api/chat", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        if chunk := data.get("message", {}).get("content", ""):
                            yield chunk
                    except json.JSONDecodeError:
                        continue

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            resp = await self.client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            return [m["name"] for m in models]
        except Exception:
            return []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()


class LlamaCppProvider(BaseLLMProvider):
    """
    llama.cpp server provider (OpenAI-compatible endpoint).
    Run: `llama-server -m model.gguf --host 127.0.0.1 --port 8080`
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    async def complete(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }

        resp = await self.client.post(
            f"{self.base_url}/v1/chat/completions", json=payload
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def stream(self, prompt: str, system: str = "") -> AsyncIterator[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        async with self.client.stream(
            "POST", f"{self.base_url}/v1/chat/completions", json=payload
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and not line.endswith("[DONE]"):
                    try:
                        data = json.loads(line[6:])
                        if chunk := data["choices"][0]["delta"].get("content", ""):
                            yield chunk
                    except Exception:
                        continue

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get(f"{self.base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False


def create_llm_provider(config: LLMConfig) -> BaseLLMProvider:
    """Factory: return the right provider based on config."""
    if config.provider == "ollama":
        return OllamaProvider(config)
    elif config.provider == "llamacpp":
        return LlamaCppProvider(config)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
