# AI Copilot Phase 3 Implementation Plan

> Status Update (2026-03-25): Phase 3 is complete. Delivered capabilities include case-centric context expansion, deterministic `test_data` and `mock` seed builders, unified `preview/history/apply/export` routes, and `WorkspacePage` panels for preview, replay, apply, and JSON export.
> Known deviations: `test_data` still persists curated variants into `api_cases.metadata_json.ai_test_data_variants`, `mock` still persists curated templates into `api_cases.metadata_json.ai_mock_templates`, no runtime mock platform was introduced, and `ai_case_histories` remains separate from `ai_artifacts`.
> Verification completed on 2026-03-25: `pytest tests/test_ai_copilot_phase1.py tests/test_ai_copilot_phase2.py tests/test_ai_copilot_phase3.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q` and `npm run build`.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Phase 3 pre-execution preparation loop by shipping `test_data` and `mock` capabilities on top of the existing unified AI Copilot workflow.

**Architecture:** Reuse the shipped `AI Copilot` backbone from Phases 1 and 2 and extend it with two new case-centric capabilities: `test_data` and `mock`. Both capabilities must remain artifact-first preview flows; deterministic apply may persist curated outputs into case metadata and support JSON export, but must not introduce a runtime mock platform or a second data-persistence universe in this phase.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, React 19, TypeScript, Ant Design, pytest.

---

## 审计结论

1. `Phase 1 + Phase 2` 的主链已经稳定：`context -> preview -> ai_artifacts -> review -> deterministic apply/export`。`Phase 3` 只能继续加 capability，不能另起炉灶。
2. `WorkspacePage` 里的 case editor 已经是最合适的 `test_data / mock` 入口，因为它天然拥有 `case body / assertions / metadata / environment` 这些事实源。
3. 当前代码里没有独立的 dataset model，也没有 mock rule/runtime 平台。`Phase 3` 必须先做“建议 + metadata apply + JSON export”，不能顺手做成完整的 mock 平台。
4. 现有可复用事实源已经够用：
   - `ApiCase.body_json / headers_json / metadata_json`
   - `Environment.variables_json`
   - 最近成功/失败 `execution item` 的 request/response 样本
5. `ai_case_histories` 仍未并轨到 `ai_artifacts`。`Phase 3` 不处理历史迁移，只沿用统一 artifact 体系承接 `test_data / mock` 产物。

## Phase 3 范围

### 本期只做

- `test_data` capability
- `mock` capability
- case 级上下文增强
- 结构化 preview / history / apply / export
- Case 编辑区前端接入

### 本期不做

- 运行时 mock 平台
- 拦截器、scenario 切换、suite 级 mock profile
- 新建 dataset 专用表
- `ai_case_histories -> ai_artifacts` 历史迁移
- 多 provider / 多 runtime 平台化

## 落位决策

### `test_data` 放哪

- capability schema: `backend/app/schemas/ai_copilot.py`
- capability runner: `backend/app/services/ai_test_data_service.py`
- deterministic seed builder: `backend/app/services/ai_test_data_seed_service.py`
- route: `backend/app/api/routes/ai_copilot.py`
- apply target: `api_cases.metadata_json.ai_test_data_variants`

原因：
- `test_data` 是标准的 case-centric preview artifact。
- 当前没有 dataset model，最稳的 Phase 3 解法是先把“已确认的数据变体”挂到 case metadata，保证可追溯、可回看、可导出。
- 真正执行时仍由人选择怎么把 variant 带入请求体，不做自动重写执行链。

### `mock` 放哪

- capability schema: `backend/app/schemas/ai_copilot.py`
- capability runner: `backend/app/services/ai_mock_service.py`
- deterministic seed builder: `backend/app/services/ai_mock_template_seed_service.py`
- route: `backend/app/api/routes/ai_copilot.py`
- apply target: `api_cases.metadata_json.ai_mock_templates`

原因：
- roadmap 明确要求 Phase 3 先做“mock 内容建议器”，而不是完整 mock 平台。
- 当前系统没有 mock rule 持久化对象，先把已确认模板保存到 case metadata，并支持 JSON 导出，范围最稳。
- 这样后续如果真要做 mock runtime，也能复用 Phase 3 的 artifact 和 schema，不会推翻重来。

### 前端入口放哪

- 容器仍放在 `frontend/src/pages/WorkspacePage.tsx`
- Case 编辑区新增 `AI 测试数据` 和 `AI Mock` 面板
- 复用 `frontend/src/components/ai-copilot/` 共享展示组件

原因：
- `test_data / mock` 的输入天然依赖当前 case 编辑上下文。
- 不需要再做新的页面或全局工作台，避免把 Phase 3 做成第二套 UI 骨架。

## 数据与 Apply 决策

### `test_data` 结构化输出

最小输出结构：

```json
{
  "data_variants": [
    {
      "variant_id": "tv_required_field_missing",
      "name": "required_field_missing",
      "category": "negative_path",
      "payload_patch": {
        "username": "",
        "password": "demo123"
      },
      "target_fields": ["username"],
      "reason": "required field should be blank to verify validation",
      "suggested_assertions": [
        {"type": "status_code", "operator": "==", "expected": 400, "enabled": true}
      ]
    }
  ]
}
```

apply 语义：

- 只允许把选中的 variants 保存到 `api_cases.metadata_json.ai_test_data_variants`
- 默认 `append`
- 显式 `override_existing=true` 才覆盖旧 variants
- 同时支持导出 JSON bundle，不直接改 `body_json`

### `mock` 结构化输出

最小输出结构：

```json
{
  "mock_templates": [
    {
      "template_id": "mt_login_permission_denied",
      "scenario_name": "login_permission_denied",
      "status_code": 403,
      "response_template": {
        "code": 40301,
        "message": "permission denied"
      },
      "mock_rules": [
        {"method": "POST", "path": "/login", "status_code": 403}
      ],
      "reason": "permission branch is hard to reproduce against unstable downstreams"
    }
  ]
}
```

apply 语义：

- 只允许把选中的 templates 保存到 `api_cases.metadata_json.ai_mock_templates`
- 支持导出 JSON 文件，供外部 mock 平台或手工调试使用
- 不做运行时拦截、不做环境级激活开关

## Task 1: 冻结 Phase 3 contract

**Files:**
- Modify: `backend/app/schemas/ai_copilot.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/services.ts`
- Create: `tests/test_ai_copilot_phase3.py`

**Step 1: 写失败测试，锁定 capability 与 schema contract**

- 先写：
  - `test_ai_copilot_capability_enum_includes_test_data_and_mock`
  - `test_ai_test_data_preview_response_contract`
  - `test_ai_mock_preview_response_contract`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py -q
```

Expected:

- FAIL，提示 capability / request / result schema 缺失

**Step 3: 定义最小 schema**

- 扩展 `AiArtifactCapability`:
  - `test_data`
  - `mock`
- 新增 request:
  - `AiTestDataPreviewRequest`
  - `AiTestDataApplyRequest`
  - `AiMockPreviewRequest`
  - `AiMockApplyRequest`
- 新增 result:
  - `AiTestDataResult`
  - `AiTestDataVariantRead`
  - `AiMockResult`
  - `AiMockTemplateRead`

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py -q
```

Expected:

- PASS contract 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase3.py backend/app/schemas/ai_copilot.py frontend/src/api/types.ts frontend/src/api/services.ts
git commit -m "feat: add phase3 ai copilot contracts"
```

## Task 2: 扩展 case-centric AI 上下文

**Files:**
- Modify: `backend/app/services/ai_context_assembler.py`
- Modify: `backend/app/services/workspace_service.py`
- Test: `tests/test_ai_copilot_phase3.py`

**Step 1: 写失败测试，锁定 Phase 3 事实集**

- 先写：
  - `test_case_context_contains_environment_variables_and_recent_execution_samples`
  - `test_case_context_extracts_request_shape_for_test_data`
  - `test_case_context_extracts_response_shape_for_mock`
  - `test_case_context_sanitizes_sensitive_fields_before_ai`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py -q
```

Expected:

- FAIL，提示 case context 事实不足

**Step 3: 实现最小上下文增强**

- `AiContextAssembler.build_case_context(case_id)` 至少补充：
  - 当前 case 基础信息
  - 关联 project / suite / environment 摘要
  - 最近成功/失败 execution item 的 request/response 样本
  - request shape 摘要：
    - path params
    - query params
    - body field paths
  - response shape 摘要：
    - status_code
    - top-level JSON keys
    - 历史成功/失败 payload exemplar
- 继续做敏感字段脱敏：
  - token
  - password
  - cookie
  - authorization

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py -q
```

Expected:

- PASS context 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase3.py backend/app/services/ai_context_assembler.py backend/app/services/workspace_service.py
git commit -m "feat: extend ai case context for phase3"
```

## Task 3: 实现 deterministic `test_data` seed builder

**Files:**
- Create: `backend/app/services/ai_test_data_seed_service.py`
- Modify: `backend/app/services/__init__.py`
- Test: `tests/test_ai_copilot_phase3.py`

**Step 1: 写失败测试，锁定 test-data seed 基线**

- 先写：
  - `test_test_data_seed_service_extracts_required_and_boundary_variants`
  - `test_test_data_seed_service_uses_recent_success_sample_as_baseline`
  - `test_test_data_seed_service_is_deterministic_without_llm`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py -q
```

Expected:

- FAIL，提示 seed builder 缺失

**Step 3: 实现最小规则引擎**

- 输入只支持 `case`
- 从下列信息生成 deterministic seeds：
  - `body_json`
  - URL / query 中的参数线索
  - `metadata_json`
  - 最近成功样本
- 第一版只生成 roadmap 要求的基础变体：
  - required missing
  - empty string
  - boundary length / numeric edge
  - enum mismatch
  - obvious invalid type

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py -q
```

Expected:

- PASS seed 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase3.py backend/app/services/ai_test_data_seed_service.py backend/app/services/__init__.py
git commit -m "feat: add deterministic test data seed service"
```

## Task 4: 实现 deterministic `mock` seed builder

**Files:**
- Create: `backend/app/services/ai_mock_template_seed_service.py`
- Modify: `backend/app/services/__init__.py`
- Test: `tests/test_ai_copilot_phase3.py`

**Step 1: 写失败测试，锁定 mock seed 基线**

- 先写：
  - `test_mock_seed_service_extracts_response_templates_from_history`
  - `test_mock_seed_service_builds_status_and_path_rules`
  - `test_mock_seed_service_is_deterministic_without_llm`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py -q
```

Expected:

- FAIL，提示 mock seed builder 缺失

**Step 3: 实现最小规则引擎**

- 输入只支持 `case`
- 从下列信息生成 deterministic mock seeds：
  - 最近成功 response
  - 最近失败 response
  - 当前 case method/url
  - assertion / metadata 中的状态线索
- 第一版只支持：
  - happy-path response template
  - permission denied
  - validation error
  - downstream timeout / degraded response

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py -q
```

Expected:

- PASS seed 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase3.py backend/app/services/ai_mock_template_seed_service.py backend/app/services/__init__.py
git commit -m "feat: add deterministic mock template seed service"
```

## Task 5: 打通 `test_data` capability 与 apply/export

**Files:**
- Create: `backend/app/services/ai_test_data_service.py`
- Modify: `backend/app/services/ai_copilot_service.py`
- Modify: `backend/app/api/routes/ai_copilot.py`
- Modify: `backend/app/services/workspace_service.py`
- Test: `tests/test_ai_copilot_phase3.py`
- Test: `tests/test_ai_copilot_web_routes.py`

**Step 1: 写失败测试，锁定 preview/history/apply/export 主链**

- 先写：
  - `test_ai_test_data_preview_persists_artifact`
  - `test_ai_test_data_apply_appends_variants_to_case_metadata`
  - `test_ai_test_data_apply_override_replaces_existing_variants`
  - `test_ai_test_data_export_returns_json_bundle`
  - `test_ai_test_data_web_routes_smoke`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- FAIL，提示 service / route / apply 缺失

**Step 3: 实现最小 capability**

- `AiTestDataService.generate_preview()`：
  - 消费 case context + deterministic seeds
  - 产出 `data_variants`
- 路由新增：
  - `POST /api/v1/ai-copilot/test-data/preview`
  - `GET /api/v1/ai-copilot/test-data/history`
  - `POST /api/v1/ai-copilot/test-data/{artifact_id}/apply`
  - `GET /api/v1/ai-copilot/test-data/{artifact_id}/export`
- deterministic apply：
  - 默认 append 到 `api_cases.metadata_json.ai_test_data_variants`
  - 显式 `override_existing=true` 才替换

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- PASS `test_data` 主链测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase3.py tests/test_ai_copilot_web_routes.py backend/app/services/ai_test_data_service.py backend/app/services/ai_copilot_service.py backend/app/api/routes/ai_copilot.py backend/app/services/workspace_service.py
git commit -m "feat: add ai test data capability"
```

## Task 6: 打通 `mock` capability 与 apply/export

**Files:**
- Create: `backend/app/services/ai_mock_service.py`
- Modify: `backend/app/services/ai_copilot_service.py`
- Modify: `backend/app/api/routes/ai_copilot.py`
- Modify: `backend/app/services/workspace_service.py`
- Test: `tests/test_ai_copilot_phase3.py`
- Test: `tests/test_ai_copilot_web_routes.py`

**Step 1: 写失败测试，锁定 mock preview/history/apply/export 主链**

- 先写：
  - `test_ai_mock_preview_persists_artifact`
  - `test_ai_mock_apply_appends_templates_to_case_metadata`
  - `test_ai_mock_apply_override_replaces_existing_templates`
  - `test_ai_mock_export_returns_json_bundle`
  - `test_ai_mock_web_routes_smoke`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- FAIL，提示 mock service / route / apply 缺失

**Step 3: 实现最小 capability**

- `AiMockService.generate_preview()`：
  - 消费 case context + deterministic seeds
  - 产出 `mock_templates`
- 路由新增：
  - `POST /api/v1/ai-copilot/mock/preview`
  - `GET /api/v1/ai-copilot/mock/history`
  - `POST /api/v1/ai-copilot/mock/{artifact_id}/apply`
  - `GET /api/v1/ai-copilot/mock/{artifact_id}/export`
- deterministic apply：
  - 默认 append 到 `api_cases.metadata_json.ai_mock_templates`
  - 显式 `override_existing=true` 才替换

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase3.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- PASS `mock` 主链测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase3.py tests/test_ai_copilot_web_routes.py backend/app/services/ai_mock_service.py backend/app/services/ai_copilot_service.py backend/app/api/routes/ai_copilot.py backend/app/services/workspace_service.py
git commit -m "feat: add ai mock capability"
```

## Task 7: 前端接入 case 级 `test_data / mock` 闭环

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/services.ts`
- Create: `frontend/src/components/ai-copilot/AiTestDataPanel.tsx`
- Create: `frontend/src/components/ai-copilot/AiMockTemplatePanel.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Test: `npm run build`

**Step 1: 先做最小交互草图**

- 在 case 编辑区新增两个能力入口：
  - `AI 测试数据`
  - `AI Mock`
- 每个入口都支持：
  - preview
  - history
  - export
  - apply

**Step 2: 写最小前端状态机**

- `test_data preview -> select variants -> apply/export`
- `mock preview -> select templates -> apply/export`
- 继续复用：
  - `AiCapabilityActionCard`
  - `AiSuggestionPanel`
  - `AiArtifactHistoryDrawer`

**Step 3: 接 API**

- `previewAiTestData(...)`
- `listAiTestDataHistory(...)`
- `applyAiTestData(...)`
- `exportAiTestData(...)`
- `previewAiMock(...)`
- `listAiMockHistory(...)`
- `applyAiMock(...)`
- `exportAiMock(...)`

**Step 4: 跑构建**

Run:

```bash
npm run build
```

Expected:

- PASS，Workspace case 编辑区无类型错误

**Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/services.ts frontend/src/components/ai-copilot/AiTestDataPanel.tsx frontend/src/components/ai-copilot/AiMockTemplatePanel.tsx frontend/src/pages/WorkspacePage.tsx
git commit -m "feat: add phase3 ai case preparation panels"
```

## Task 8: 收口验证与 roadmap 回写

**Files:**
- Modify: `docs/plans/2026-03-24-ai-copilot-roadmap.md`
- Modify: `docs/plans/2026-03-25-ai-copilot-phase3-implementation-plan.md`
- Test: `tests/test_ai_copilot_phase1.py`
- Test: `tests/test_ai_copilot_phase2.py`
- Test: `tests/test_ai_copilot_phase3.py`
- Test: `tests/test_ai_copilot_web_routes.py`
- Test: `tests/test_web_services.py`
- Test: `npm run build`

**Step 1: 补集成回归用例**

- `test_data` preview/apply/export 主链
- `mock` preview/apply/export 主链
- `case metadata` append/override 幂等性

**Step 2: 跑后端回归**

Run:

```bash
pytest tests/test_ai_copilot_phase1.py tests/test_ai_copilot_phase2.py tests/test_ai_copilot_phase3.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q
```

Expected:

- PASS Phase 1 + Phase 2 + Phase 3 回归

**Step 3: 跑前端构建**

Run:

```bash
npm run build
```

Expected:

- PASS，前端构建通过

**Step 4: 回写 roadmap**

- 顶部新增 `Status Update (2026-03-XX): Phase 3 is complete`
- 明确已交付：
  - `test_data`
  - `mock`
  - case metadata apply/export
- 明确偏差：
  - 未实现 runtime mock 平台
  - 未新增 dataset 专用表

**Step 5: Commit**

```bash
git add docs/plans/2026-03-24-ai-copilot-roadmap.md docs/plans/2026-03-25-ai-copilot-phase3-implementation-plan.md
git commit -m "docs: close phase3 ai copilot rollout"
```

## 风险与反模式

### 绝对不要做

- 直接把 AI 生成的数据变体写回 `body_json`
- 直接把 AI 生成的 mock 模板接成运行时拦截器
- 为 `test_data / mock` 再造一套独立历史存储
- 在 Phase 3 顺手扩展成“数据平台”或“mock 平台”

### 必须守住

- AI 只产建议，apply/export 由确定性代码完成
- 所有 preview 都必须进 `ai_artifacts`
- 所有 case metadata 写入都要支持 append / override 明确语义
- 所有敏感样本在传给 AI 前必须脱敏

## 完成定义

满足以下条件才算 Phase 3 完成：

1. 用户能在 case 编辑区为单个 case 生成结构化测试数据变体。
2. 用户能将选中的数据变体保存到 case metadata 或导出 JSON。
3. 用户能为单个 case 生成结构化 mock 模板。
4. 用户能将选中的 mock 模板保存到 case metadata 或导出 JSON。
5. 所有 `test_data / mock` 结果都可追溯、可回看、可重放。
6. 不引入 runtime mock 平台，不新增 dataset 专用持久化模型。
