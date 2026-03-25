from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import requests
from fastapi import HTTPException, status

from backend.app.services.ai_provider_registry import AiGenerationRuntimeConfig


class AiClientService:
    def generate_json(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            session = requests.Session()
            session.trust_env = runtime.use_env_proxy
            response = session.post(
                self._build_chat_completions_url(runtime.endpoint),
                headers={
                    "Authorization": f"Bearer {runtime.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": runtime.model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=runtime.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="AI generation timed out.") from exc
        except requests.RequestException as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI generation request failed: {exc}") from exc
        finally:
            session.close()

        payload = response.json()
        return payload, {
            "call_mode": "llm",
            "provider": {
                "provider": runtime.provider,
                "model": runtime.model,
                "base_url": runtime.endpoint,
                "timeout_seconds": runtime.timeout_seconds,
            },
            "latency_ms": int(getattr(response, "elapsed", 0).total_seconds() * 1000) if getattr(response, "elapsed", None) else None,
            "failure_category": "",
            "trace_json": {},
        }

    def _build_chat_completions_url(self, endpoint: str) -> str:
        from urllib.parse import urlsplit, urlunsplit

        normalized = endpoint.strip().rstrip("/")
        if not normalized:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI endpoint is required.")
        if normalized.endswith("/chat/completions"):
            return normalized
        parsed = urlsplit(normalized)
        path = parsed.path.rstrip("/")
        if path.endswith("/v1"):
            path = f"{path}/chat/completions"
        else:
            path = f"{path}/v1/chat/completions"
        return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))

    def _extract_message_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return ""
        message = first_choice.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
            return "".join(text_parts)
        return ""

    def stream_text(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> tuple[Iterator[str], dict[str, Any]]:
        session = requests.Session()
        session.trust_env = runtime.use_env_proxy
        response: requests.Response | None = None
        try:
            response = session.post(
                self._build_chat_completions_url(runtime.endpoint),
                headers={
                    "Authorization": f"Bearer {runtime.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": runtime.model,
                    "temperature": 0.3,
                    "stream": True,
                    "messages": [{"role": "system", "content": system_prompt}, *messages],
                },
                stream=True,
                timeout=runtime.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            session.close()
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="AI generation timed out.") from exc
        except requests.RequestException as exc:
            session.close()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI generation request failed: {exc}") from exc

        def _iter_chunks() -> Iterator[str]:
            try:
                for raw_line in response.iter_lines(decode_unicode=False):
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    payload_text = line[5:].strip()
                    if payload_text == "[DONE]":
                        break
                    try:
                        payload = json.loads(payload_text)
                    except json.JSONDecodeError:
                        continue
                    choices = payload.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    delta = choices[0].get("delta") if isinstance(choices[0], dict) else {}
                    if not isinstance(delta, dict):
                        continue
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield content
                    elif isinstance(content, list):
                        for item in content:
                            if not isinstance(item, dict):
                                continue
                            if item.get("type") == "text" and isinstance(item.get("text"), str) and item["text"]:
                                yield item["text"]
            finally:
                response.close()
                session.close()

        return _iter_chunks(), {
            "call_mode": "llm",
            "provider": {
                "provider": runtime.provider,
                "model": runtime.model,
                "base_url": runtime.endpoint,
                "timeout_seconds": runtime.timeout_seconds,
            },
            "latency_ms": None,
            "failure_category": "",
            "trace_json": {},
        }

    def generate_text(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> tuple[str, dict[str, Any]]:
        try:
            session = requests.Session()
            session.trust_env = runtime.use_env_proxy
            response = session.post(
                self._build_chat_completions_url(runtime.endpoint),
                headers={
                    "Authorization": f"Bearer {runtime.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": runtime.model,
                    "temperature": 0.3,
                    "messages": [{"role": "system", "content": system_prompt}, *messages],
                },
                timeout=runtime.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="AI generation timed out.") from exc
        except requests.RequestException as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI generation request failed: {exc}") from exc
        finally:
            session.close()

        payload = response.json()
        return self._extract_message_content(payload), {
            "call_mode": "llm",
            "provider": {
                "provider": runtime.provider,
                "model": runtime.model,
                "base_url": runtime.endpoint,
                "timeout_seconds": runtime.timeout_seconds,
            },
            "latency_ms": int(getattr(response, "elapsed", 0).total_seconds() * 1000) if getattr(response, "elapsed", None) else None,
            "failure_category": "",
            "trace_json": {},
        }
