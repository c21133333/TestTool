from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.core.observability import get_logger, log_event
from backend.app.schemas.ai_case_draft import (
    AiCaseDraftBatchRead,
    AiCaseDraftBatchSummary,
    AiCaseDraftPayload,
    AiCaseDraftPreviewRequest,
    AiCaseDraftRead,
    AiCaseDraftRerunRequest,
)
from backend.app.services.ai_provider_registry import AiProviderRegistry
from backend.app.services.ai_provider_registry import AiGenerationRuntimeConfig, AiProviderRegistry
from backend.app.services.ai_case_history_service import AiCaseHistoryService
from backend.app.services.llm_case_generation_service import LlmCaseGenerationService
from backend.app.services.markdown_endpoint_parser import MarkdownEndpointParser, MarkdownEndpointSection
from backend.app.services.workspace_service import WorkspaceService

logger = get_logger("ai_case")

_KNOWN_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
_PROMPT_PRESETS = {
    "balanced": "Generate a balanced set of main path, error path, and key validation cases.",
    "smoke": "Focus on smoke coverage and the most business-critical happy-path checks.",
    "negative": "Focus on invalid parameters, permission errors, and obvious failure paths.",
    "boundary": "Focus on empty values, required fields, min/max style boundaries, and enum edge cases.",
}


class AiCaseDraftService:
    def __init__(
        self,
        session: Session,
        *,
        parser: MarkdownEndpointParser | None = None,
        llm_service: LlmCaseGenerationService | None = None,
        history_service: AiCaseHistoryService | None = None,
    ) -> None:
        self._session = session
        self._workspace = WorkspaceService(session)
        self._parser = parser or MarkdownEndpointParser()
        self._llm_service = llm_service or LlmCaseGenerationService()
        self._history = history_service or AiCaseHistoryService(session)
        self._provider_registry = AiProviderRegistry()

    def preview_drafts(self, payload: AiCaseDraftPreviewRequest) -> AiCaseDraftBatchRead:
        self._workspace.get_project(payload.project_id)
        runtime = self._resolve_runtime(payload)
        log_event(logger, "ai_case.preview.started", project_id=payload.project_id, suite_name=payload.suite_name, provider=runtime.provider, model=runtime.model)

        parsed = self._parser.parse(payload.markdown_text)
        warnings = list(parsed.warnings)
        drafts: list[AiCaseDraftRead] = []
        effective_prompt_hints = self._build_effective_prompt_hints(payload.prompt_preset, payload.prompt_hints)

        for section in parsed.sections:
            section_drafts, section_warnings = self._llm_service.generate_drafts(
                section_title=section.title,
                section_content=section.content,
                runtime=runtime,
                prompt_hints=effective_prompt_hints,
            )
            warnings.extend(section_warnings)
            for raw_draft in section_drafts:
                drafts.append(self._normalize_draft(raw_draft=raw_draft, section=section))

        if not drafts:
            warnings.append("AI did not return any case drafts.")

        duplicate_warning_count = self._mark_duplicates(drafts)
        if duplicate_warning_count:
            warnings.append(f"Detected {duplicate_warning_count} duplicate method+URL draft pair(s).")

        valid_count = len([draft for draft in drafts if draft.validation_status == "valid"])
        invalid_count = len([draft for draft in drafts if draft.validation_status == "invalid"])
        log_event(
            logger,
            "ai_case.preview.completed",
            level=logging.WARNING if invalid_count else logging.INFO,
            project_id=payload.project_id,
            suite_name=payload.suite_name,
            provider=runtime.provider,
            model=runtime.model,
            draft_count=len(drafts),
            valid_count=valid_count,
            invalid_count=invalid_count,
        )

        batch = AiCaseDraftBatchRead(
            suite_name=payload.suite_name,
            doc_summary=AiCaseDraftBatchSummary(section_count=parsed.section_count, endpoint_count=parsed.endpoint_count),
            drafts=drafts,
            warnings=warnings,
            prompt_preset=payload.prompt_preset or "balanced",
            prompt_hints_effective=effective_prompt_hints,
        )
        return self._history.save_batch(
            project_id=payload.project_id,
            suite_name=payload.suite_name,
            provider=runtime.provider,
            model=runtime.model,
            base_url=runtime.endpoint,
            prompt_preset=payload.prompt_preset or "balanced",
            prompt_hints=payload.prompt_hints,
            prompt_hints_effective=effective_prompt_hints,
            markdown_text=payload.markdown_text,
            batch=batch,
        )

    def rerun_from_history(self, history_id: str, payload: AiCaseDraftRerunRequest) -> AiCaseDraftBatchRead:
        history_payload, history_batch = self._history.get_history_batch(history_id)
        preview_payload = AiCaseDraftPreviewRequest(
            project_id=int(history_payload.get("project_id") or 0),
            suite_name=str(history_payload.get("suite_name") or history_batch.suite_name),
            markdown_text=str(history_payload.get("markdown_text") or ""),
            provider=payload.provider or str(history_payload.get("provider") or ""),
            model=payload.model or str(history_payload.get("model") or ""),
            base_url=payload.base_url or str(history_payload.get("base_url") or ""),
            api_key=payload.api_key,
            timeout_seconds=payload.timeout_seconds,
            prompt_preset=str(history_payload.get("prompt_preset") or history_batch.prompt_preset or "balanced"),
            prompt_hints=str(history_payload.get("prompt_hints") or ""),
        )
        return self.preview_drafts(preview_payload)

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

    def normalize_generated_draft(
        self,
        *,
        raw_draft: dict[str, Any],
        section: MarkdownEndpointSection,
        source_location_extra: dict[str, Any] | None = None,
    ) -> AiCaseDraftRead:
        draft = self._normalize_draft(raw_draft=raw_draft, section=section)
        if source_location_extra:
            draft = draft.model_copy(update={"source_location": {**draft.source_location, **dict(source_location_extra)}})
        return draft

    def build_saved_batch(
        self,
        *,
        project_id: int,
        suite_name: str,
        markdown_text: str,
        provider: str,
        model: str,
        base_url: str,
        prompt_preset: str,
        prompt_hints: str,
        prompt_hints_effective: str,
        section_count: int,
        endpoint_count: int,
        drafts: list[AiCaseDraftRead],
        warnings: list[str],
    ) -> AiCaseDraftBatchRead:
        batch = AiCaseDraftBatchRead(
            suite_name=suite_name,
            doc_summary=AiCaseDraftBatchSummary(section_count=section_count, endpoint_count=endpoint_count),
            drafts=drafts,
            warnings=warnings,
            prompt_preset=prompt_preset or "balanced",
            prompt_hints_effective=prompt_hints_effective,
        )
        return self._history.save_batch(
            project_id=project_id,
            suite_name=suite_name,
            provider=provider,
            model=model,
            base_url=base_url,
            prompt_preset=prompt_preset or "balanced",
            prompt_hints=prompt_hints,
            prompt_hints_effective=prompt_hints_effective,
            markdown_text=markdown_text,
            batch=batch,
        )

    def _build_effective_prompt_hints(self, prompt_preset: str, prompt_hints: str) -> str:
        preset_key = prompt_preset if prompt_preset in _PROMPT_PRESETS else "balanced"
        preset_hint = _PROMPT_PRESETS[preset_key]
        extra_hint = prompt_hints.strip()
        return preset_hint if not extra_hint else f"{preset_hint} {extra_hint}"

    def _resolve_runtime(self, payload: AiCaseDraftPreviewRequest) -> AiGenerationRuntimeConfig:
        return self.resolve_runtime(
            provider=payload.provider,
            model=payload.model,
            base_url=payload.base_url,
            api_key=payload.api_key,
            timeout_seconds=payload.timeout_seconds,
        )

    def _normalize_draft(self, *, raw_draft: dict[str, Any], section: MarkdownEndpointSection) -> AiCaseDraftRead:
        case_payload = raw_draft.get("case") if isinstance(raw_draft.get("case"), dict) else raw_draft
        metadata_source = case_payload.get("metadata_json") if isinstance(case_payload, dict) else {}
        if not isinstance(metadata_source, dict):
            metadata_source = {}
        metadata = dict(metadata_source)
        for source_key, metadata_key in (("category", "category"), ("precondition", "precondition"), ("priority", "priority")):
            value = raw_draft.get(source_key)
            if value not in (None, "") and metadata_key not in metadata:
                metadata[metadata_key] = str(value).strip()
        metadata.setdefault("ai_generated", True)
        metadata.setdefault("source_type", "markdown_ai")

        payload = AiCaseDraftPayload.model_validate(
            {
                "name": case_payload.get("name") if isinstance(case_payload, dict) else "",
                "method": case_payload.get("method") if isinstance(case_payload, dict) else "GET",
                "url": case_payload.get("url") if isinstance(case_payload, dict) else "",
                "description": case_payload.get("description") if isinstance(case_payload, dict) else "",
                "headers_json": case_payload.get("headers_json") if isinstance(case_payload, dict) else {},
                "body_json": case_payload.get("body_json") if isinstance(case_payload, dict) else None,
                "assertions_json": case_payload.get("assertions_json") if isinstance(case_payload, dict) else [],
                "metadata_json": metadata,
            }
        )

        validation_errors = self._validate_case_payload(payload)
        review_warnings: list[str] = []
        validation_status = "invalid" if validation_errors else "valid"
        if not validation_errors and not payload.assertions_json:
            validation_status = "warning"
            review_warnings.append("No assertions were generated for this case.")

        source_excerpt, source_location = self._build_source_mapping(
            section=section,
            method=payload.method,
            url=payload.url,
            raw_source_excerpt=str(raw_draft.get("source_excerpt") or "").strip(),
        )
        return AiCaseDraftRead(
            draft_id=str(raw_draft.get("draft_id") or uuid4().hex),
            selected=bool(raw_draft.get("selected", True)),
            validation_status=validation_status,
            validation_errors=validation_errors,
            review_warnings=review_warnings,
            case=payload,
            source_excerpt=source_excerpt,
            source_location=source_location,
        )

    def _build_source_mapping(self, *, section: MarkdownEndpointSection, method: str, url: str, raw_source_excerpt: str) -> tuple[str, dict[str, Any]]:
        matched_endpoint = None
        normalized_url = url.strip()
        for endpoint_match in section.endpoint_matches:
            if endpoint_match.method != method:
                continue
            if normalized_url == endpoint_match.path or normalized_url.endswith(endpoint_match.path) or endpoint_match.path.endswith(normalized_url):
                matched_endpoint = endpoint_match
                break

        source_excerpt = raw_source_excerpt
        if not source_excerpt:
            if matched_endpoint is not None:
                source_excerpt = self._build_endpoint_excerpt(section.content, matched_endpoint.char_start, matched_endpoint.char_end)
            else:
                source_excerpt = self._build_excerpt(section.content)

        source_location = {
            "section_title": section.title,
            "chunk_index": section.chunk_index,
            "endpoints": section.endpoints,
            "line_start": section.line_start,
            "line_end": section.line_end,
        }
        if matched_endpoint is not None:
            source_location["matched_endpoint"] = {
                "method": matched_endpoint.method,
                "path": matched_endpoint.path,
                "line_number": matched_endpoint.line_number,
            }
        return source_excerpt, source_location

    def _validate_case_payload(self, payload: AiCaseDraftPayload) -> list[str]:
        errors: list[str] = []
        if not payload.name:
            errors.append("Case name is required.")
        if not payload.url:
            errors.append("URL is required.")
        if payload.method not in _KNOWN_HTTP_METHODS:
            errors.append(f"Unsupported HTTP method: {payload.method}.")
        return errors

    def _build_excerpt(self, section_content: str) -> str:
        lines = [line.strip() for line in section_content.splitlines() if line.strip()]
        return "\n".join(lines[:6])[:500]

    def _build_endpoint_excerpt(self, section_content: str, char_start: int, char_end: int) -> str:
        start = max(0, char_start - 120)
        end = min(len(section_content), char_end + 260)
        excerpt = section_content[start:end].strip()
        return excerpt[:500]

    def _mark_duplicates(self, drafts: list[AiCaseDraftRead]) -> int:
        duplicate_map: dict[tuple[str, str], list[AiCaseDraftRead]] = {}
        for draft in drafts:
            key = (draft.case.method.strip().upper(), draft.case.url.strip())
            if not key[1]:
                continue
            duplicate_map.setdefault(key, []).append(draft)

        duplicate_pair_count = 0
        for (method, url), grouped in duplicate_map.items():
            if len(grouped) < 2:
                continue
            duplicate_pair_count += len(grouped) - 1
            for draft in grouped:
                warning = f"Duplicate draft detected for {method} {url}."
                if warning not in draft.review_warnings:
                    draft.review_warnings.append(warning)
                if draft.validation_status == "valid":
                    draft.validation_status = "warning"
        return duplicate_pair_count
