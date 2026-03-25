from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from backend.app.schemas.ai_copilot import AiTestDataResult, AiTestDataVariantRead


@dataclass(frozen=True)
class _LeafField:
    path: tuple[str, ...]
    value: Any


class AiTestDataSeedService:
    def build_result(self, case_context: dict[str, Any]) -> AiTestDataResult:
        baseline_payload = self._resolve_baseline_payload(case_context)
        leaf_fields = self._collect_leaf_fields(baseline_payload)

        variants: list[AiTestDataVariantRead] = []
        first_string_field = next((field for field in leaf_fields if isinstance(field.value, str) and field.value), None)
        first_numeric_field = next(
            (field for field in leaf_fields if isinstance(field.value, (int, float)) and not isinstance(field.value, bool)),
            None,
        )

        if first_string_field is not None:
            variants.append(
                self._build_variant(
                    name="required_field_missing",
                    category="negative_path",
                    baseline_payload=baseline_payload,
                    target_field=first_string_field,
                    replacement=None,
                    reason="required field should be removed or null to verify validation",
                )
            )
            variants.append(
                self._build_variant(
                    name="empty_string",
                    category="boundary_path",
                    baseline_payload=baseline_payload,
                    target_field=first_string_field,
                    replacement="",
                    reason="string field should be tested with empty input",
                )
            )

        if first_numeric_field is not None:
            numeric_value = first_numeric_field.value
            boundary_value = numeric_value + 1 if isinstance(numeric_value, int) else round(numeric_value + 0.1, 2)
            variants.append(
                self._build_variant(
                    name="numeric_boundary",
                    category="boundary_path",
                    baseline_payload=baseline_payload,
                    target_field=first_numeric_field,
                    replacement=boundary_value,
                    reason="numeric field should be checked around a nearby boundary",
                )
            )
            variants.append(
                self._build_variant(
                    name="invalid_type",
                    category="negative_path",
                    baseline_payload=baseline_payload,
                    target_field=first_numeric_field,
                    replacement="invalid_type",
                    reason="numeric field should be checked with an obvious invalid type",
                )
            )

        first_list_field = next((field for field in leaf_fields if isinstance(field.value, list) and field.value), None)
        if first_list_field is not None:
            variants.append(
                self._build_variant(
                    name="enum_mismatch",
                    category="negative_path",
                    baseline_payload=baseline_payload,
                    target_field=first_list_field,
                    replacement=["__unexpected__"],
                    reason="enumerated/list-like field should be checked with an unsupported member",
                )
            )

        return AiTestDataResult(data_variants=variants)

    def _resolve_baseline_payload(self, case_context: dict[str, Any]) -> dict[str, Any]:
        recent_success = case_context.get("recent_success_sample")
        if isinstance(recent_success, dict):
            request = recent_success.get("request")
            if isinstance(request, dict):
                body = request.get("body")
                if isinstance(body, dict):
                    return deepcopy(body)

        body_json = case_context.get("body_json")
        if isinstance(body_json, dict):
            return deepcopy(body_json)
        return {}

    def _build_variant(
        self,
        *,
        name: str,
        category: str,
        baseline_payload: dict[str, Any],
        target_field: _LeafField,
        replacement: Any,
        reason: str,
    ) -> AiTestDataVariantRead:
        payload_patch = deepcopy(baseline_payload)
        self._set_path_value(payload_patch, target_field.path, replacement)
        target_path = ".".join(target_field.path)
        return AiTestDataVariantRead(
            variant_id=f"tv_{target_path.replace('.', '_')}_{name}",
            name=name,
            category=category,
            payload_patch=payload_patch,
            target_fields=[target_path],
            reason=reason,
            suggested_assertions=[{"type": "status_code", "operator": "==", "expected": 400, "enabled": True}],
        )

    def _collect_leaf_fields(self, payload: dict[str, Any]) -> list[_LeafField]:
        return self._collect_value_fields(payload, prefix=())

    def _collect_value_fields(self, value: Any, *, prefix: tuple[str, ...]) -> list[_LeafField]:
        if isinstance(value, dict):
            collected: list[_LeafField] = []
            for key, item in value.items():
                collected.extend(self._collect_value_fields(item, prefix=(*prefix, str(key))))
            return collected
        if isinstance(value, list):
            if value and all(not isinstance(item, (dict, list)) for item in value):
                return [_LeafField(path=prefix, value=value)]
            collected: list[_LeafField] = []
            for index, item in enumerate(value):
                collected.extend(self._collect_value_fields(item, prefix=(*prefix, str(index))))
            return collected
        return [_LeafField(path=prefix, value=value)] if prefix else []

    def _set_path_value(self, payload: dict[str, Any], path: tuple[str, ...], replacement: Any) -> None:
        current: Any = payload
        for segment in path[:-1]:
            if isinstance(current, dict):
                current = current.setdefault(segment, {})
            elif isinstance(current, list):
                current = current[int(segment)]
        last_segment = path[-1]
        if isinstance(current, dict):
            current[last_segment] = replacement
        elif isinstance(current, list):
            current[int(last_segment)] = replacement
