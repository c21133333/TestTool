# AI Copilot Phase 2 Implementation Plan

> Status Update (2026-03-25): Complete. All eight tasks in this plan have shipped. Delivered scope: `test_point` contracts/context/preview/history, deterministic `coverage` scanner + Copilot capability, selected-test-point draft bridge, and Workspace frontend integration for `coverage -> test point -> draft`. Verification completed on 2026-03-25 with `pytest tests/test_ai_copilot_phase1.py tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q` and `npm run build`.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Phase 2 test-design loop by shipping `test_point` preview/selection, test-point-driven case draft generation, and deterministic `coverage` gap scanning on top of the existing unified AI Copilot workflow.

**Architecture:** Reuse the shipped `AI Copilot` backbone from Phase 1 and extend it with two new capabilities: `test_point` and `coverage`. `coverage` must remain a deterministic matrix scanner first, with AI limited to explanation, prioritization, and suggested test points; `test_point` must remain an artifact preview step that feeds the existing draft-generation/import workflow instead of creating a second draft persistence system.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, React 19, TypeScript, Ant Design, pytest.

---

## 审计结论

1. `Phase 1` 的 `context -> preview -> ai_artifacts -> review -> deterministic apply` 主链已经成立，`Phase 2` 只能扩 capability，不能另起栈。
2. `AiCaseGenerationPanel` 已经是测试设计入口，roadmap 也明确要求把“生成测试点 -> 选择测试点 -> 生成草稿”加在它前面，而不是新造页面。
3. `coverage` 不能直接交给 LLM。必须先做确定性 `coverage matrix`，再让 AI 负责解释、排序和建议测试点。
4. `ai_case_histories` 还未并轨到 `ai_artifacts`。`Phase 2` 不做历史迁移，只做桥接：测试点产物进 `ai_artifacts`，草稿产物继续复用既有 `ai_case_histories` 闭环。
5. 当前 provider 仍然以 `openai_compatible` 为主，`Phase 2` 不扩多 provider 抽象，避免范围失控。

## Phase 2 范围

### 本期只做

- `test_point` capability
- `coverage` capability
- 基于测试点生成 `case draft`
- `suite / project` 级 coverage 扫描与测试点转化
- Workspace 侧统一交互入口

### 本期不做

- `test_data`
- `mock`
- `ai_case_histories -> ai_artifacts` 数据迁移
- 复杂业务链路 coverage 建模
- 多 provider/runtime 配置平台化

## 落位决策

### `test_point` 放哪

- capability schema: `backend/app/schemas/ai_copilot.py`
- capability runner: `backend/app/services/ai_test_point_service.py`
- route: `backend/app/api/routes/ai_copilot.py`
- drafts bridge: `backend/app/services/ai_test_point_draft_service.py`

原因：
- `test_point` 是标准 `AI Copilot preview artifact`
- 生成草稿只是它的下游动作，不应该直接混回 `AiCaseDraftService.preview_drafts(markdown_text=...)`
- 选中的测试点最终应转换成现有 draft batch，而不是直接落库成 `ApiCase`

### `coverage` 放哪

- deterministic scanner: `backend/app/services/ai_coverage_scan_service.py`
- AI explanation layer: `backend/app/services/ai_coverage_service.py`
- route: `backend/app/api/routes/ai_copilot.py`

原因：
- `coverage` 的事实生成和 AI 解释必须分层
- scanner 负责“算出缺什么”，AI 只负责“解释为什么缺、建议先补什么”
- 这样 Phase 2 之后即使替换模型，也不会污染 coverage 基线算法

### 前端入口放哪

- 核心入口继续放 `frontend/src/components/ai/AiCaseGenerationPanel.tsx`
- Workspace 容器仍放在 `frontend/src/pages/WorkspacePage.tsx`
- 新增 Phase 2 展示组件放 `frontend/src/components/ai-copilot/`

原因：
- roadmap 已明确 “测试点生成 / AI case draft 生成 / 覆盖率扫描入口” 都在 Workspace 侧
- Task 7 已经抽出共享 AI 展示组件，Phase 2 应继续复用

## Task 1: 冻结 Phase 2 contract

**Files:**
- Modify: `backend/app/schemas/ai_copilot.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/services.ts`
- Test: `tests/test_ai_copilot_phase2.py`

**Step 1: 写失败测试，锁定枚举与响应 contract**

- 新建 `tests/test_ai_copilot_phase2.py`
- 先写：
  - `test_ai_copilot_capability_enum_includes_test_point_and_coverage`
  - `test_ai_test_point_preview_response_contract`
  - `test_ai_coverage_preview_response_contract`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py -q
```

Expected:

- FAIL，提示 capability/schema 缺失

**Step 3: 定义最小 schema**

- 扩展 `AiArtifactCapability`:
  - `test_point`
  - `coverage`
- 新增 request:
  - `AiTestPointPreviewRequest`
  - `AiTestPointGenerateDraftsRequest`
  - `AiCoverageScanRequest`
- 新增 result:
  - `AiTestPointResult`
  - `AiCoverageResult`
  - `AiCoverageMissingDimension`
  - `AiCoverageSuggestedPoint`

`test_point` 最小输出：

```json
{
  "test_points": [
    {
      "id": "tp_login_happy",
      "title": "登录成功主链路",
      "category": "happy_path",
      "risk_level": "high",
      "reason": "核心登录入口",
      "covered_by_existing_cases": false,
      "suggested_case_count": 2
    }
  ]
}
```

`coverage` 最小输出：

```json
{
  "coverage_score": 67,
  "missing_dimensions": [],
  "suggested_points": []
}
```

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py -q
```

Expected:

- PASS contract 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase2.py backend/app/schemas/ai_copilot.py frontend/src/api/types.ts frontend/src/api/services.ts
git commit -m "feat: add phase2 ai copilot contracts"
```

## Task 2: 扩展 project / suite 级设计上下文

**Files:**
- Modify: `backend/app/services/ai_context_assembler.py`
- Modify: `backend/app/services/workspace_service.py`
- Modify: `backend/app/repositories/workspace_repository.py`
- Test: `tests/test_ai_copilot_phase2.py`

**Step 1: 写失败测试，锁定 Phase 2 上下文事实集**

- 先写：
  - `test_project_context_contains_suites_and_case_summary`
  - `test_suite_context_contains_cases_and_assertion_breakdown`
  - `test_suite_context_sanitizes_sensitive_fields`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py -q
```

Expected:

- FAIL，提示 `project/suite` context builder 不存在

**Step 3: 实现最小读取侧聚合**

- `AiContextAssembler` 新增：
  - `build_project_context(project_id)`
  - `build_suite_context(suite_id)`
- `build_context(...)` 支持 `target_type=project|suite`
- Phase 2 上下文至少包含：
  - project/suite 基础信息
  - case 列表摘要
  - method/path 去重结果
  - 断言类型统计
  - metadata category/priority/tag 摘要
  - 最近 execution / report 摘要（如果存在）

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py -q
```

Expected:

- PASS context 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase2.py backend/app/services/ai_context_assembler.py backend/app/services/workspace_service.py backend/app/repositories/workspace_repository.py
git commit -m "feat: add phase2 project and suite ai context"
```

## Task 3: 实现 deterministic coverage scanner

**Files:**
- Create: `backend/app/services/ai_coverage_scan_service.py`
- Modify: `backend/app/services/__init__.py`
- Test: `tests/test_ai_copilot_phase2.py`

**Step 1: 写失败测试，锁定 coverage matrix 基线**

- 先写：
  - `test_coverage_scan_scores_suite_from_case_metadata_and_assertions`
  - `test_coverage_scan_reports_missing_dimensions`
  - `test_coverage_scan_is_deterministic_without_llm`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py -q
```

Expected:

- FAIL，提示 scanner/service 缺失

**Step 3: 实现最小 coverage 规则引擎**

- 输入只支持 `project` 和 `suite`
- 第一版只扫描 roadmap 明确的确定性维度：
  - endpoint: `method + path`
  - scenario: `happy_path / negative_path / boundary_path / auth / idempotent / pagination`
  - assertion: `status / business_code / body_field / schema / latency`
- 规则来源仅限：
  - case `metadata_json`
  - case `assertions_json`
  - method/url
- 不做复杂业务链路 coverage 推断

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py -q
```

Expected:

- PASS scanner 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase2.py backend/app/services/ai_coverage_scan_service.py backend/app/services/__init__.py
git commit -m "feat: add deterministic coverage scanner"
```

## Task 4: 落地 `coverage` capability 与历史链路

**Files:**
- Create: `backend/app/services/ai_coverage_service.py`
- Modify: `backend/app/services/ai_copilot_service.py`
- Modify: `backend/app/api/routes/ai_copilot.py`
- Test: `tests/test_ai_copilot_phase2.py`
- Test: `tests/test_ai_copilot_web_routes.py`

**Step 1: 写失败测试，锁定 coverage preview/history**

- 先写：
  - `test_ai_copilot_coverage_preview_persists_artifact`
  - `test_ai_copilot_coverage_history_filters_by_suite`
  - `test_ai_copilot_coverage_result_contains_suggested_points`
- web route 追加：
  - `test_ai_copilot_coverage_routes_smoke`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- FAIL，提示 coverage runner / route 缺失

**Step 3: 实现 capability runner**

- `AiCoverageService` 组合：
  - `AiCoverageScanService` 的 deterministic 输出
  - AI explanation/prioritization 逻辑
- 路由新增：
  - `POST /api/v1/ai-copilot/coverage/scan`
  - `GET /api/v1/ai-copilot/coverage/history`
- `target_type` 支持：
  - `suite`
  - `project`

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- PASS capability 与 route 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py backend/app/services/ai_coverage_service.py backend/app/services/ai_copilot_service.py backend/app/api/routes/ai_copilot.py
git commit -m "feat: add ai coverage capability"
```

## Task 5: 落地 `test_point` preview capability

**Files:**
- Create: `backend/app/services/ai_test_point_service.py`
- Modify: `backend/app/services/ai_copilot_service.py`
- Modify: `backend/app/api/routes/ai_copilot.py`
- Test: `tests/test_ai_copilot_phase2.py`
- Test: `tests/test_ai_copilot_web_routes.py`

**Step 1: 写失败测试，锁定测试点预览 contract**

- 先写：
  - `test_ai_test_point_preview_marks_existing_coverage_overlap`
  - `test_ai_test_point_preview_supports_markdown_plus_suite_context`
  - `test_ai_test_point_history_filters_by_target`
- web route 追加：
  - `test_ai_copilot_test_point_preview_route_smoke`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- FAIL，提示 `test_point` runner / route 缺失

**Step 3: 实现最小预览能力**

- 输入支持：
  - `project_id` 或 `suite_id`
  - `markdown_text`
  - optional `prompt_hints`
- 生成范围先锁定 roadmap 的第一阶段边界：
  - `happy_path`
  - `negative_path`
  - `boundary_path`
- 输出必须标记：
  - 是否被现有 case 覆盖
  - 建议 case 数量
  - 风险等级

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- PASS preview 与 history 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py backend/app/services/ai_test_point_service.py backend/app/services/ai_copilot_service.py backend/app/api/routes/ai_copilot.py
git commit -m "feat: add ai test point preview capability"
```

## Task 6: 基于选中测试点生成 case draft

**Files:**
- Create: `backend/app/services/ai_test_point_draft_service.py`
- Modify: `backend/app/services/ai_case_draft_service.py`
- Modify: `backend/app/api/routes/ai_copilot.py`
- Test: `tests/test_ai_copilot_phase2.py`
- Test: `tests/test_ai_copilot_web_routes.py`

**Step 1: 写失败测试，锁定 bridge 语义**

- 先写：
  - `test_generate_drafts_from_selected_test_points_returns_ai_case_batch`
  - `test_generate_drafts_from_selected_test_points_requires_selection`
  - `test_generated_drafts_keep_source_mapping_to_test_point`
- web route 追加：
  - `test_ai_copilot_test_points_generate_drafts_route`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- FAIL，提示 drafts bridge 缺失

**Step 3: 实现 bridge**

- 路由新增：
  - `POST /api/v1/ai-copilot/test-points/generate-drafts`
- 输入：
  - `artifact_id`
  - `selected_point_ids`
  - `project_id`
  - `suite_name`
  - runtime config (`provider/model/base_url/api_key/timeout_seconds`)
- 输出：
  - 继续复用 `AiCaseDraftBatchRead`
- 约束：
  - 生成草稿仍走 `AiCaseHistoryService`
  - 每个 draft 写入 `source_location.test_point_id`
  - 不直接创建 `ApiCase`

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- PASS bridge 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py backend/app/services/ai_test_point_draft_service.py backend/app/services/ai_case_draft_service.py backend/app/api/routes/ai_copilot.py
git commit -m "feat: generate case drafts from selected ai test points"
```

## Task 7: 前端接入测试设计闭环

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/services.ts`
- Modify: `frontend/src/components/ai/AiCaseGenerationPanel.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Create: `frontend/src/components/ai-copilot/AiTestPointTable.tsx`
- Create: `frontend/src/components/ai-copilot/AiCoveragePanel.tsx`
- Test: `npm run build`

**Step 1: 先做最小交互草图**

- 在 `AiCaseGenerationPanel` 增加三段流程：
  - `生成测试点`
  - `选择测试点`
  - `基于测试点生成草稿`
- 在 `WorkspacePage` 增加：
  - `覆盖率扫描`
  - suite/project coverage 结果面板

**Step 2: 写前端最小状态机**

- `test_point preview -> point selection -> draft preview`
- `coverage scan -> result render -> transfer to test point preview`
- 继续复用：
  - `AiCapabilityActionCard`
  - `AiSuggestionPanel`
  - `AiArtifactHistoryDrawer`

**Step 3: 接 API**

- `previewAiTestPoints(...)`
- `generateAiDraftsFromTestPoints(...)`
- `scanAiCoverage(...)`
- `listAiCoverageHistory(...)`

**Step 4: 跑构建**

Run:

```bash
npm run build
```

Expected:

- PASS，Workspace 侧无类型错误

**Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/services.ts frontend/src/components/ai/AiCaseGenerationPanel.tsx frontend/src/pages/WorkspacePage.tsx frontend/src/components/ai-copilot/AiTestPointTable.tsx frontend/src/components/ai-copilot/AiCoveragePanel.tsx
git commit -m "feat: add phase2 ai test design workspace flow"
```

## Task 8: 收口验证与文档回写

**Files:**
- Modify: `docs/plans/2026-03-24-ai-copilot-roadmap.md`
- Modify: `docs/plans/2026-03-24-ai-copilot-phase2-implementation-plan.md`
- Test: `tests/test_ai_copilot_phase2.py`
- Test: `tests/test_ai_copilot_web_routes.py`
- Test: `tests/test_ai_copilot_phase1.py`
- Test: `tests/test_web_services.py`

**Step 1: 补集成回归用例**

- `coverage` project/suite smoke
- `test_point -> generate_drafts` 主链
- coverage 建议转测试点建议的串联验证

**Step 2: 跑后端回归**

Run:

```bash
pytest tests/test_ai_copilot_phase1.py tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q
```

Expected:

- PASS Phase 1 + Phase 2 回归

**Step 3: 跑前端构建**

Run:

```bash
npm run build
```

Expected:

- PASS

**Step 4: 回写 roadmap**

- 标记 `Phase 2` 已完成或记录偏差
- 写清：
  - `coverage` 采用 deterministic-first
  - `test_point` 通过 bridge 进入 draft flow
  - `ai_case_histories` 是否仍为并行历史线

**Step 5: Commit**

```bash
git add docs/plans/2026-03-24-ai-copilot-roadmap.md docs/plans/2026-03-24-ai-copilot-phase2-implementation-plan.md tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py
git commit -m "docs: close phase2 ai copilot plan and verification"
```

## Phase 2 验收标准

- 用户能在 Workspace 侧先生成测试点，再选择测试点生成 case draft
- 用户能在 suite / project 维度看到 coverage 缺口
- coverage 结果能转成测试点建议
- 所有 `test_point / coverage` 结果都能进入 `ai_artifacts`
- 生成的 case draft 仍保持人工确认与导入闭环，不直接落库到 `ApiCase`

## 实施顺序建议

1. 先冻结 contract，再扩上下文
2. 先做 deterministic coverage scanner，再接 AI explanation
3. 先做 test point preview，再做 selected-point -> draft bridge
4. 最后做前端整合和回归收口

## 不建议的做法

- 直接把 `coverage score` 交给 LLM 计算
- 跳过测试点层，重新回到“直接生成大量 case”
- 让选中的测试点直接落库成 `ApiCase`
- 为 Phase 2 顺手做 `ai_case_histories` 迁移
- 在 Phase 2 顺手扩 `test_data` / `mock`
