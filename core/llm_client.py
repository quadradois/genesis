import json
import sys
import time
import logging
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("llm_client")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MOONSHOT_URL = "https://api.moonshot.ai/v1/chat/completions"

OPENROUTER_MODELS = [
    "openai/gpt-4o-mini",
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemma-4-31b-it",
    "qwen/qwen3-coder",
    "mistralai/mistral-7b-instruct",
]

DEFAULT_MOONSHOT_MODEL = "kimi-k2.6"

TIMEOUT = 20


def _load_keys() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


class LLMClient:
    def __init__(self):
        self._keys = _load_keys()
        self._or_key = self._keys.get("openrouter_api_key", "")
        self._or_enabled = self._keys.get("openrouter_enabled", True)
        self._ms_key = self._keys.get("moonshot_api_key", "")
        self._ms_model = self._keys.get("moonshot_model", DEFAULT_MOONSHOT_MODEL)
        self._or_failed = not self._or_enabled
        self._ms_failed = False

    def _call_openrouter(self, messages: list[dict], max_tokens: int, temperature: float) -> Optional[str]:
        if not self._or_key or self._or_failed:
            return None
        for model in OPENROUTER_MODELS:
            try:
                resp = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self._or_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
                    timeout=TIMEOUT,
                )
                if resp.status_code == 200:
                    logger.info(f"[LLM] OpenRouter OK: {model}")
                    return resp.json()["choices"][0]["message"]["content"]
                if resp.status_code == 401:
                    logger.warning(f"[LLM] OpenRouter 401 no modelo {model} — tentando proximo")
                    continue
                if resp.status_code == 429:
                    logger.info(f"[LLM] OpenRouter rate limit: {model}")
                    continue
                logger.warning(f"[LLM] OpenRouter {model} → HTTP {resp.status_code}")
            except Exception as e:
                logger.warning(f"[LLM] OpenRouter {model} → {e}")
                continue
        logger.warning("[LLM] OpenRouter: todos os modelos falharam")
        self._or_failed = True
        return None

    def _call_moonshot(self, messages: list[dict], max_tokens: int, temperature: float) -> Optional[str]:
        if not self._ms_key or self._ms_failed:
            return None
        model = self._ms_model
        body = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if model == "kimi-k2.6":
            body["temperature"] = 1.0
        else:
            body["temperature"] = temperature
        try:
            resp = requests.post(
                MOONSHOT_URL,
                headers={
                    "Authorization": f"Bearer {self._ms_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                msg = resp.json()["choices"][0]["message"]
                return msg.get("content") or msg.get("reasoning_content", "")
            if resp.status_code == 401:
                logger.warning(f"[LLM] Moonshot 401 — desabilitando")
                self._ms_failed = True
                return None
            logger.warning(f"[LLM] Moonshot {model} → HTTP {resp.status_code}")
            return None
        except Exception as e:
            logger.warning(f"[LLM] Moonshot {model} → {e}")
            return None

    def chat(
        self,
        prompt: str,
        system: str = "You are a helpful assistant.",
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        result = self._call_openrouter(messages, max_tokens, temperature)
        if result:
            return result
        result = self._call_moonshot(messages, max_tokens, temperature)
        if result:
            return result
        if not self._or_key and not self._ms_key:
            raise RuntimeError("Nenhuma chave de API configurada (OpenRouter ou Moonshot)")
        raise RuntimeError("Todos os provedores LLM falharam")

    def chat_json(
        self,
        prompt: str,
        system: str = "Return ONLY valid JSON. No markdown, no explanation.",
        max_tokens: int = 1024,
    ) -> dict:
        raw = self.chat(prompt, system=system, max_tokens=max_tokens, temperature=0.1)
        clean = raw.strip()
        if clean.startswith("```"):
            parts = clean.split("```")
            clean = parts[1] if len(parts) > 1 else clean
            clean = clean[4:] if clean.startswith("json") else clean
        clean = clean.strip().rstrip("`").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logger.error(f"[LLM] JSON parse failed: {e}")
            raise ValueError(f"Modelo retornou JSON invalido: {raw[:200]}")

    @property
    def ms_model(self) -> str:
        return self._ms_model

    @ms_model.setter
    def ms_model(self, value: str):
        self._ms_model = value

    def reset_failures(self):
        self._or_failed = not self._or_enabled
        self._ms_failed = False

    @property
    def has_any_key(self) -> bool:
        return bool(self._or_key) or bool(self._ms_key)


llm = LLMClient()
