from __future__ import annotations

import json
from typing import Any
from fastapi import HTTPException, status

from backend.app.services.ai_client_service import AiClientService
from backend.app.services.ai_provider_registry import AiGenerationRuntimeConfig, AiProviderRegistry


class LlmCaseGenerationService:
    def __init__(
        self,
        *,
        ai_client: AiClientService | None = None,
        provider_registry: AiProviderRegistry | None = None,
    ) -> None:
        self._ai_client = ai_client or AiClientService()
        self._provider_registry = provider_registry or AiProviderRegistry()
        self.last_call_trace: dict[str, Any] = {"call_mode": "deterministic", "trace_json": {}}

    def resolve_runtime(
        self,
        *,
        provider: str = "",
        model: str = "",
        base_url: str = "",
        api_key: str = "",
        timeout_seconds: int | None = None,
    ) -> AiGenerationRuntimeConfig:
        return self._provider_registry.resolve_runtime(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

    def generate_drafts(
        self,
        *,
        section_title: str,
        section_content: str,
        runtime: AiGenerationRuntimeConfig,
        prompt_hints: str = "",
    ) -> tuple[list[dict[str, Any]], list[str]]:
        payload, trace = self._ai_client.generate_json(
            runtime=runtime,
            system_prompt=self._build_system_prompt(),
            user_prompt=self._build_user_prompt(
                section_title=section_title,
                section_content=section_content,
                prompt_hints=prompt_hints,
            ),
        )
        self.last_call_trace = dict(trace or {})
        if isinstance(payload, dict) and isinstance(payload.get("drafts"), list):
            normalized = payload
        else:
            content = self._extract_message_content(payload)
            normalized = self._load_json_payload(content)
        drafts = normalized.get("drafts")
        warnings = normalized.get("warnings")
        if not isinstance(drafts, list):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI returned invalid drafts payload.")
        return [item for item in drafts if isinstance(item, dict)], [str(item) for item in warnings or []]

    def _build_system_prompt(self) -> str:
        return (
            "You generate API test case drafts for an existing test platform. "
            "Return JSON only. No markdown fences. No commentary. "
            "The top-level object must contain keys 'drafts' and 'warnings'. "
            "Each draft must include: name, method, url, description, headers_json, body_json, assertions_json, metadata_json. "
            "Do not invent undocumented business contracts. "
            "Prefer main path, validation failure path, and obvious boundary path cases."
        )

    def _build_user_prompt(self, *, section_title: str, section_content: str, prompt_hints: str) -> str:
        hints = prompt_hints.strip() or "Generate a compact but useful set of cases."
        return (
            "Generate API case drafts from the following Markdown section.\n\n"
            f"Section title: {section_title}\n"
            f"Additional hints: {hints}\n\n"
            "Output schema example:\n"
            '{'
            '"drafts": ['
            '{"name":"case name","method":"POST","url":"/api/demo","description":"",'
            '"headers_json":{"Content-Type":"application/json"},'
            '"body_json":{},'
            '"assertions_json":[{"type":"status_code","operator":"==","expected":200,"enabled":true}],'
            '"metadata_json":{"category":"demo","priority":"P1","precondition":""}}'
            '],'
            '"warnings":["optional warning"]'
            '}\n\n'
            "Markdown section:\n"
            f"{section_content}"
        )

    def _extract_message_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI response did not contain choices.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI response did not contain a valid message.")
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
            return "".join(text_parts).strip()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI response content was empty.")

    def _load_json_payload(self, content: str) -> dict[str, Any]:
        normalized = content.strip()
        if normalized.startswith("```"):
            normalized = normalized.strip("`")
            if normalized.startswith("json"):
                normalized = normalized[4:]
            normalized = normalized.strip()
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI did not return valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI response JSON must be an object.")
        return parsed
