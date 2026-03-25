from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import HTTPException

from backend.app.schemas.ai_copilot import AiChatMessage
from backend.app.services.ai_chat_context_service import AiChatContextService
from backend.app.services.ai_client_service import AiClientService
from backend.app.services.ai_provider_registry import AiProviderRegistry


class AiChatService:
    def __init__(
        self,
        *,
        context_service: AiChatContextService,
        client_service: AiClientService | None = None,
        provider_registry: AiProviderRegistry | None = None,
    ) -> None:
        self._context_service = context_service
        self._client_service = client_service or AiClientService()
        self._provider_registry = provider_registry or AiProviderRegistry()

    def stream_reply(
        self,
        *,
        chat_mode: str,
        project_id: int | None,
        page_path: str,
        page_title: str,
        messages: list[AiChatMessage],
    ) -> Iterator[str]:
        if not messages:
            raise HTTPException(status_code=400, detail="At least one chat message is required.")

        latest_user_message = next((item.content.strip() for item in reversed(messages) if item.role == "user" and item.content.strip()), "")
        if not latest_user_message:
            raise HTTPException(status_code=400, detail="The latest user question is required.")

        snapshot = self._build_snapshot(chat_mode=chat_mode, project_id=project_id)
        history_messages = self._build_history_messages(messages)
        system_prompt = self._build_system_prompt(chat_mode=chat_mode)
        user_prompt = self._build_user_prompt(
            chat_mode=chat_mode,
            page_path=page_path,
            page_title=page_title,
            latest_user_message=latest_user_message,
            snapshot=snapshot,
        )

        yield self._event(
            "meta",
            {
                "chat_mode": chat_mode,
                "project_id": project_id,
                "project_name": snapshot.get("project", {}).get("name") if isinstance(snapshot.get("project"), dict) else None,
                "warnings": snapshot.get("warnings", []),
                "redaction_applied": snapshot.get("redaction_applied", True),
            },
        )

        try:
            runtime = self._provider_registry.resolve_runtime()
            request_messages = [*history_messages, {"role": "user", "content": user_prompt}]
            stream, call_trace = self._client_service.stream_text(
                runtime=runtime,
                system_prompt=system_prompt,
                messages=request_messages,
            )
            streamed_chunk_count = 0
            for chunk in stream:
                if not chunk:
                    continue
                streamed_chunk_count += 1
                yield self._event("delta", {"content": chunk})
            if streamed_chunk_count == 0:
                fallback_text, fallback_trace = self._client_service.generate_text(
                    runtime=runtime,
                    system_prompt=system_prompt,
                    messages=request_messages,
                )
                for chunk in self._chunk_text(fallback_text or "当前模型未返回可显示内容。"):
                    yield self._event("delta", {"content": chunk})
                call_trace = {
                    **fallback_trace,
                    "trace_json": {
                        **(fallback_trace.get("trace_json") or {}),
                        "stream_fallback": "non_stream_chunked",
                    },
                }
            yield self._event("done", {"call_trace": call_trace})
        except HTTPException as exc:
            yield self._event(
                "error",
                {
                    "message": self._error_message(exc),
                    "status_code": exc.status_code,
                },
            )

    def _build_history_messages(self, messages: list[AiChatMessage]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for message in messages[-10:]:
            content = message.content.strip()
            if not content:
                continue
            normalized.append({"role": message.role, "content": content[:4000]})
        return normalized[:-1] if normalized and normalized[-1]["role"] == "user" else normalized

    def _build_system_prompt(self, *, chat_mode: str) -> str:
        mode_guidance = (
            "Use the provided project business snapshot when answering."
            if chat_mode == "project"
            else "This is free chat mode. Do not depend on project data unless the user later switches mode."
        )
        return (
            "You are Eazy Test AI copilot.\n"
            "Reply in Simplified Chinese unless the user clearly uses another language.\n"
            f"{mode_guidance}\n"
            "If evidence is insufficient, explicitly say: 当前项目证据不足。\n"
            "Never claim access to system tables, auth tables, user tables, audit tables, tokens, secrets, cookies, passwords, or hidden metadata.\n"
            "Never reveal redacted values.\n"
            "If the user asks for forbidden data, refuse briefly and offer a safe alternative.\n"
            "When citing facts, mention project/suite/case/execution/report ids or names when available."
        )

    def _build_user_prompt(
        self,
        *,
        chat_mode: str,
        page_path: str,
        page_title: str,
        latest_user_message: str,
        snapshot: dict[str, Any],
    ) -> str:
        return (
            f"Chat mode: {chat_mode}\n"
            f"Page title: {page_title or 'Unknown page'}\n"
            f"Page path: {page_path or '/'}\n"
            f"User question: {latest_user_message}\n"
            f"{self._context_heading(chat_mode)}\n"
            f"{self._build_context_outline(snapshot, chat_mode=chat_mode)}"
        )

    def _event(self, event: str, payload: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def _chunk_text(self, content: str) -> list[str]:
        text = content.strip()
        if not text:
            return []
        return [text[index:index + 24] for index in range(0, len(text), 24)]

    def _build_context_outline(self, snapshot: dict[str, Any], *, chat_mode: str) -> str:
        lines: list[str] = []
        lines.append(f"- scope: {snapshot.get('scope', 'global')}")
        lines.append(f"- summary: {snapshot.get('summary', '')}")

        project = snapshot.get("project")
        if isinstance(project, dict) and project:
            lines.append(
                f"- project: #{project.get('id', '')} {project.get('name', '')} | description={project.get('description', '')}"
            )

        warnings = snapshot.get("warnings")
        if isinstance(warnings, list) and warnings:
            lines.append(f"- warnings: {' | '.join(str(item) for item in warnings[:4])}")

        suites = snapshot.get("suites")
        if isinstance(suites, list) and suites:
            lines.append("- suites:")
            for suite in suites[:8]:
                if not isinstance(suite, dict):
                    continue
                lines.append(
                    f"  - #{suite.get('id', '')} {suite.get('name', '')} | case_count={suite.get('case_count', 0)} | description={suite.get('description', '')}"
                )

        cases = snapshot.get("cases")
        if isinstance(cases, list) and cases:
            lines.append("- cases:")
            for api_case in cases[:12]:
                if not isinstance(api_case, dict):
                    continue
                lines.append(
                    f"  - case #{api_case.get('id', '')} [{api_case.get('suite_name', '')}] {api_case.get('method', '')} {api_case.get('url', '')} | name={api_case.get('name', '')} | assertions={api_case.get('assertion_count', 0)}"
                )

        environments = snapshot.get("environments")
        if isinstance(environments, list) and environments:
            lines.append("- environments:")
            for environment in environments[:6]:
                if not isinstance(environment, dict):
                    continue
                lines.append(
                    f"  - env #{environment.get('id', '')} {environment.get('name', '')} | base_url={environment.get('base_url', '')}"
                )

        executions = snapshot.get("recent_executions")
        if isinstance(executions, list) and executions:
            lines.append("- recent_executions:")
            for execution in executions[:6]:
                if not isinstance(execution, dict):
                    continue
                lines.append(
                    f"  - execution #{execution.get('id', '')} status={execution.get('status', '')} scope={execution.get('scope', '')} target={execution.get('target_name', '')} error={execution.get('error_message', '')}"
                )

        reports = snapshot.get("recent_reports")
        if isinstance(reports, list) and reports:
            lines.append("- recent_reports:")
            for report in reports[:6]:
                if not isinstance(report, dict):
                    continue
                lines.append(
                    f"  - report #{report.get('id', '')} type={report.get('report_type', '')} execution=#{report.get('execution_id', '')} target={report.get('execution_target', '')}"
                )

        if chat_mode == "free":
            lines.append("- project_data_bound: false")

        return "\n".join(lines)

    def _build_snapshot(self, *, chat_mode: str, project_id: int | None) -> dict[str, Any]:
        if chat_mode == "free":
            return {
                "scope": "free",
                "summary": "当前为自由对话模式，不绑定任何项目业务资产。",
                "project": None,
                "warnings": ["自由对话不会引用项目、套件、用例、执行或报告快照。"],
                "redaction_applied": True,
            }
        return self._context_service.build_project_snapshot(project_id)

    def _context_heading(self, chat_mode: str) -> str:
        return "Free chat context:" if chat_mode == "free" else "Read-only project context:"

    def _error_message(self, error: HTTPException) -> str:
        detail = str(error.detail or "")
        if error.status_code == 504:
            return "AI 对话超时了，请稍后重试。"
        if "API key" in detail or "endpoint" in detail or "model" in detail or "provider" in detail:
            return "当前未配置可用的大模型对话能力。"
        if detail:
            return detail
        return "AI 对话暂时不可用。"
