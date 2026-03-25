from __future__ import annotations

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
