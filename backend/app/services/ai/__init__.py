"""Optional AI layer with strict guardrails.

Providers: none (default) | openai_compat (OpenAI/DeepSeek/Qwen endpoints) | ollama.
The AI can ONLY: summarize, suggest extra slot extractions (needs_confirmation),
polish reply drafts, explain matches. It can NEVER: invent SKUs/prices/stock/
certs/dates, alter deterministic quotes, bypass hard filters, override locked
fields, or send messages. All outputs pass schema/whitelist validation with
deterministic fallback on any error.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ...config import settings


class AIUnavailable(Exception):
    pass


class BaseAI:
    name = "base"

    def available(self) -> bool:
        return False

    def chat_json(self, system: str, user: str, schema_hint: dict | None = None,
                  max_tokens: int = 1200) -> dict:
        raise AIUnavailable


class NoneAI(BaseAI):
    name = "none"


class OpenAICompatAI(BaseAI):
    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def chat_json(self, system: str, user: str, schema_hint: dict | None = None,
                  max_tokens: int = 1200) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system + (
                    "\nRespond with STRICT JSON only matching this shape:\n"
                    + json.dumps(schema_hint, ensure_ascii=False) if schema_hint else
                    "\nRespond with STRICT JSON only.")},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        last_err = None
        for _ in range(settings.ai_max_retries + 1):
            try:
                r = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload, timeout=settings.ai_timeout_seconds)
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                return _extract_json(content)
            except Exception as exc:  # noqa: BLE001
                last_err = exc
        raise AIUnavailable(str(last_err))


class OllamaAI(BaseAI):
    name = "ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def available(self) -> bool:
        return bool(self.base_url)

    def chat_json(self, system: str, user: str, schema_hint: dict | None = None,
                  max_tokens: int = 1200) -> dict:
        prompt = (system + "\nRespond with STRICT JSON only"
                  + (f" matching: {json.dumps(schema_hint, ensure_ascii=False)}" if schema_hint else "")
                  + f"\n\n{user}")
        try:
            r = httpx.post(f"{self.base_url}/api/generate",
                           json={"model": self.model, "prompt": prompt, "stream": False,
                                 "format": "json", "options": {"temperature": 0.2}},
                           timeout=settings.ai_timeout_seconds)
            r.raise_for_status()
            return _extract_json(r.json().get("response", "{}"))
        except Exception as exc:  # noqa: BLE001
            raise AIUnavailable(str(exc)) from exc


_JSON_RE = re.compile(r"\{.*\}", re.S)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError("model output contains no JSON object")
    return json.loads(m.group(0))


def get_ai() -> BaseAI:
    provider = (settings.ai_provider or "none").lower()
    if provider == "openai_compat" and settings.openai_base_url and settings.openai_api_key:
        return OpenAICompatAI(settings.openai_base_url, settings.openai_api_key, settings.openai_model)
    if provider == "ollama" and settings.ollama_base_url:
        return OllamaAI(settings.ollama_base_url, settings.ollama_model)
    return NoneAI()


# ------------------------------------------------------------- guarded helpers
EXTRA_SLOTS_SCHEMA = {
    "type": "object",
    "properties": {
        "extra_fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["field", "value"],
            },
        },
    },
    "required": ["extra_fields"],
}


def ai_suggest_extra_slots(text: str, known_fields: list[str]) -> list[dict]:
    """AI-proposed extra slots. Whitelisted fields only; caller stores as
    needs_confirmation so a human validates before they become active."""
    ai = get_ai()
    if not ai.available():
        return []
    allowed = ["product", "material", "color", "spec", "quantity", "target_price",
               "destination_country", "destination_port", "incoterm", "packaging",
               "customization", "certification", "lead_time", "payment_terms",
               "sample", "shipping_method"]
    allowed = [f for f in allowed if f not in known_fields]
    if not allowed:
        return []
    try:
        out = ai.chat_json(
            system="You extract structured purchasing-requirement fields from trade inquiries. "
                   f"Allowed fields: {allowed}. Only extract what the text clearly states.",
            user=text, schema_hint=EXTRA_SLOTS_SCHEMA)
        results = []
        for item in out.get("extra_fields", [])[:6]:
            fld = str(item.get("field", "")).strip()
            val = str(item.get("value", "")).strip()
            if fld in allowed and val:
                results.append({"field": fld, "value": val, "status_hint": "needs_confirmation"})
        return results
    except Exception:  # noqa: BLE001 — deterministic fallback
        return []


def ai_polish_reply(kind: str, body_en: str) -> str | None:
    """Optional polishing. Returns None (use template as-is) on any failure."""
    ai = get_ai()
    if not ai.available():
        return None
    try:
        out = ai.chat_json(
            system="You polish business English emails for foreign-trade sales replies. "
                   "Keep ALL facts, numbers and commitments exactly unchanged. "
                   'Return JSON {"body_en": "..."}',
            user=f"Reply kind: {kind}\n\n{body_en}",
            schema_hint={"type": "object", "properties": {"body_en": {"type": "string"}},
                         "required": ["body_en"]})
        polished = out.get("body_en")
        return polished if isinstance(polished, str) and polished.strip() else None
    except Exception:  # noqa: BLE001
        return None
