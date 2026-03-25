from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from backend.app.schemas.ai_copilot import AiCoverageResult
from backend.app.services.ai_client_service import AiClientService
from backend.app.services.ai_provider_registry import AiGenerationRuntimeConfig, AiProviderRegistry


class AiCoverageLlmService:
    def __init__(
        self,
        *,
        ai_client: AiClientService | None = None,
        provider_registry: AiProviderRegistry | None = None,
    ) -> None:
        self._ai_client = ai_client or AiClientService()
        self._provider_registry = provider_registry or AiProviderRegistry()
        self.last_call_trace: dict[str, Any] = {"call_mode": "deterministic", "trace_json": {}}

    def resolve_runtime(self) -> AiGenerationRuntimeConfig:
        return self._provider_registry.resolve_runtime()

    def analyze_coverage(
        self,
        *,
        runtime: AiGenerationRuntimeConfig,
        target_type: str,
        target_id: int,
        input_snapshot: dict[str, Any],
        scan_result: AiCoverageResult,
    ) -> tuple[AiCoverageResult, list[str]]:
        payload, trace = self._ai_client.generate_json(
            runtime=runtime,
            system_prompt=self._build_system_prompt(),
            user_prompt=self._build_user_prompt(
                target_type=target_type,
                target_id=target_id,
                input_snapshot=input_snapshot,
                scan_result=scan_result,
            ),
        )
        self.last_call_trace = dict(trace or {})

        normalized = self._normalize_payload(payload)
        warnings = [str(item) for item in normalized.get("warnings") or []]
        result_payload = {
            "coverage_score": normalized.get("coverage_score"),
            "missing_dimensions": normalized.get("missing_dimensions"),
            "suggested_points": normalized.get("suggested_points"),
        }
        return AiCoverageResult.model_validate(result_payload), warnings

    def _build_system_prompt(self) -> str:
        return (
            "你是 API 测试覆盖率分析助手。"
            "请基于现有已保存的测试用例与 deterministic baseline scan 做分析。"
            "必须只返回 JSON，不要 markdown，不要额外解释。"
            "coverage_score 必须与 baseline 保持一致。"
            "不要虚构未出现在提供用例清单中的 endpoint。"
            "顶层对象必须包含 coverage_score、missing_dimensions、suggested_points、warnings。"
            "missing_dimensions 的每一项必须包含 endpoint、dimension、reason。"
            "suggested_points 的每一项必须包含 title、category、priority、reason。"
            "其中 category 必须使用既有机器值：happy_path、negative_path、boundary_path、auth、idempotent、pagination、assertion_hardening。"
            "priority 必须使用机器值：high、medium、low。"
            "所有面向人的文案字段必须使用简体中文，包括 title、reason、warnings。"
            "建议点必须可执行，且紧扣当前测试资产缺口。"
        )

    def _build_user_prompt(
        self,
        *,
        target_type: str,
        target_id: int,
        input_snapshot: dict[str, Any],
        scan_result: AiCoverageResult,
    ) -> str:
        serialized_snapshot = json.dumps(input_snapshot, ensure_ascii=False, indent=2)
        serialized_baseline = json.dumps(scan_result.model_dump(), ensure_ascii=False, indent=2)
        return (
            "请分析下面这个 API 覆盖率目标。\n\n"
            f"目标类型: {target_type}\n"
            f"目标 ID: {target_id}\n\n"
            "要求：\n"
            "1. 以 deterministic baseline 为准，不要修改 coverage_score，也不要新增或删除 baseline 中已有的 endpoint/dimension 缺口对。\n"
            "2. 可以把缺口 reason 改写得更适合人读。\n"
            "3. 请生成优先级明确的 suggested_points。\n"
            "4. warnings 仅在确有必要提醒时返回，否则返回空数组。\n\n"
            "响应 schema 示例：\n"
            '{'
            '"coverage_score":55,'
            '"missing_dimensions":[{"endpoint":"GET /profile","dimension":"negative_path","reason":"缺少失败路径覆盖"}],'
            '"suggested_points":[{"title":"补充 GET /profile 失败路径用例","category":"negative_path","priority":"high","reason":"当前未覆盖鉴权失败或非法输入场景"}],'
            '"warnings":["如某些维度对当前开放接口不适用，请结合接口能力人工确认"]'
            '}\n\n'
            "当前已保存的用例清单与摘要：\n"
            f"{serialized_snapshot}\n\n"
            "deterministic baseline 覆盖率扫描结果：\n"
            f"{serialized_baseline}"
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._looks_like_result_payload(payload):
            return payload
        content = self._extract_message_content(payload)
        parsed = self._load_json_payload(content)
        if not self._looks_like_result_payload(parsed):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的 coverage 数据结构不合法。")
        return parsed

    def _looks_like_result_payload(self, payload: dict[str, Any]) -> bool:
        return isinstance(payload, dict) and "coverage_score" in payload and "missing_dimensions" in payload and "suggested_points" in payload

    def _extract_message_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 响应中缺少 choices。")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 响应中缺少合法的 message。")
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
            return "".join(text_parts).strip()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 响应内容为空。")

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
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI 没有返回合法 JSON：{exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 返回的 JSON 顶层必须是对象。")
        return parsed
