from __future__ import annotations

from fastapi import HTTPException, status

from backend.app.schemas.ai_case_draft import AiCaseDraftBatchRead
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.ai_artifact_lineage_service import AiArtifactLineageService
from backend.app.services.ai_case_draft_service import AiCaseDraftService
from backend.app.services.llm_case_generation_service import LlmCaseGenerationService
from backend.app.services.markdown_endpoint_parser import MarkdownEndpointParser


class AiTestPointDraftService:
    def __init__(
        self,
        session,
        *,
        artifact_service: AiArtifactService | None = None,
        lineage_service: AiArtifactLineageService | None = None,
        draft_service: AiCaseDraftService | None = None,
        llm_service: LlmCaseGenerationService | None = None,
        parser: MarkdownEndpointParser | None = None,
    ) -> None:
        self._artifact_service = artifact_service or AiArtifactService(session)
        self._lineage_service = lineage_service or AiArtifactLineageService(session)
        self._draft_service = draft_service or AiCaseDraftService(session)
        self._llm_service = llm_service or LlmCaseGenerationService()
        self._parser = parser or MarkdownEndpointParser()

    def generate_drafts_from_artifact(
        self,
        *,
        artifact_id: str,
        selected_point_ids: list[str],
        project_id: int,
        suite_name: str,
        provider: str = "",
        model: str = "",
        base_url: str = "",
        api_key: str = "",
        timeout_seconds: int | None = None,
    ) -> AiCaseDraftBatchRead:
        artifact = self._artifact_service.get_artifact_or_404(artifact_id)
        if artifact.capability != "test_point":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact is not a test point preview.")
        normalized_selected_ids = [item.strip() for item in selected_point_ids if str(item).strip()]
        if not normalized_selected_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one selected test point is required.")

        output_json = artifact.output_json if isinstance(artifact.output_json, dict) else {}
        raw_points = output_json.get("test_points") if isinstance(output_json.get("test_points"), list) else []
        selected_points = [
            point
            for point in raw_points
            if isinstance(point, dict) and str(point.get("id") or "").strip() in normalized_selected_ids
        ]
        if not selected_points:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected test point ids were not found in the artifact.")

        runtime = self._draft_service.resolve_runtime(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        prompt_hints = str(artifact.input_json.get("prompt_hints") or "")
        markdown_text = str(artifact.input_json.get("markdown_text") or "")
        effective_prompt_hints = self._draft_service._build_effective_prompt_hints("balanced", prompt_hints)

        warnings = [str(item) for item in artifact.warnings_json or []]
        drafts = []
        selected_endpoints: set[tuple[str, str]] = set()
        for index, point in enumerate(selected_points):
            section = self._build_test_point_section(point, index)
            method, path = self._extract_method_path(point)
            selected_endpoints.add((method, path))
            raw_drafts, section_warnings = self._llm_service.generate_drafts(
                section_title=str(point.get("title") or f"test point {index + 1}"),
                section_content=section.content,
                runtime=runtime,
                prompt_hints=effective_prompt_hints,
            )
            warnings.extend(section_warnings)
            for raw_draft in raw_drafts:
                drafts.append(
                    self._draft_service.normalize_generated_draft(
                        raw_draft=raw_draft,
                        section=section,
                        source_location_extra={
                            "test_point_id": str(point.get("id") or ""),
                            "test_point_title": str(point.get("title") or ""),
                            "test_point_category": str(point.get("category") or ""),
                            "test_point_risk_level": str(point.get("risk_level") or ""),
                        },
                    )
                )

        duplicate_warning_count = self._draft_service._mark_duplicates(drafts)
        if duplicate_warning_count:
            warnings.append(f"Detected {duplicate_warning_count} duplicate method+URL draft pair(s).")

        batch = self._draft_service.build_saved_batch(
            project_id=project_id,
            suite_name=suite_name,
            markdown_text=markdown_text,
            provider=runtime.provider,
            model=runtime.model,
            base_url=runtime.endpoint,
            prompt_preset="balanced",
            prompt_hints=prompt_hints,
            prompt_hints_effective=effective_prompt_hints,
            section_count=len(selected_points),
            endpoint_count=len(selected_endpoints),
            drafts=drafts,
            warnings=warnings,
        )
        self._lineage_service.link_artifact_to_resource(
            source_artifact_id=artifact.artifact_id,
            target_resource_type="ai_case_history",
            target_resource_key=batch.history_id,
            link_type="generated_history",
        )
        return batch

    def _build_test_point_section(self, point: dict, index: int):
        method, path = self._extract_method_path(point)
        category = str(point.get("category") or "").strip()
        reason = str(point.get("reason") or "").strip()
        section_title = str(point.get("title") or f"test point {index + 1}").strip()
        markdown_text = f"## {section_title}\n{method} {path}\n\nCategory: {category}\nReason: {reason}\n"
        parsed = self._parser.parse(markdown_text)
        if parsed.sections:
            return parsed.sections[0]
        return self._parser._build_section(title=section_title, content=markdown_text, chunk_index=index, line_start=1)  # type: ignore[attr-defined]

    def _extract_method_path(self, point: dict) -> tuple[str, str]:
        title = str(point.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test point title is missing.")
        parts = title.split(" ", 2)
        if len(parts) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test point title does not contain method and path.")
        method = parts[0].strip().upper()
        path = parts[1].strip()
        if not method or not path:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test point title does not contain method and path.")
        return method, path
