# AI Copilot Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Phase 1 AI Copilot foundation and ship failure diagnosis, report summary, and assertion suggestion on top of one unified artifact workflow.

**Architecture:** Introduce a new `ai_artifacts` persistence layer plus a thin `AI Copilot` orchestration layer. The orchestration layer assembles context, invokes the LLM with capability-specific schema constraints, stores every preview as an artifact, and routes accepted artifacts through deterministic apply code. Existing `ai-case-drafts` stays online unchanged for now; Phase 1 uses the new stack only for `diagnosis`, `report_summary`, and `assertion`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, React 19, TypeScript, Ant Design, pytest.

---

## 审计结论

1. 现有最接近目标的不是 `ReportService`，而是 `AiCaseDraftService` 的闭环模型：
   - `preview -> validate -> history save -> import/apply`
   - 对应文件：`backend/app/services/ai_case_draft_service.py`、`backend/app/services/ai_case_history_service.py`
2. 当前 `execution` 和 `report` 数据已经足够支撑 Phase 1：
   - `ExecutionService` 已经产出 `failure_breakdown`、`first_failure`、`retry_history`
   - `ReportService` 已经把 `summary` 写进 `report.metadata_json`
3. Case 编辑入口不在独立页面，而在 `frontend/src/pages/WorkspacePage.tsx` 的用例编辑区。
4. 现有 `ai_case_histories` 是专用历史表，不适合作为统一 artifact store 继续扩展。
5. 因为 `ai-case-drafts` 已上线，Phase 1 不建议先做强迁移；新能力统一使用 `ai_artifacts`，旧能力后续 Phase 2 再并轨。

## Phase 1 范围

### 本期只做

- `diagnosis`
- `report_summary`
- `assertion`
- `ai_artifacts`
- `AI Copilot` 基础编排层

### 本期不做

- `test_point`
- `coverage`
- `test_data`
- `mock`
- `ai_case_histories -> ai_artifacts` 数据迁移
- 多 provider 抽象

## 落位决策

### `ai_artifacts` 放哪

- 新增一等模型：`backend/app/models/ai_artifact.py`
- 新增 repository：`backend/app/repositories/ai_artifact_repository.py`
- 新增 migration：`alembic/versions/20260324_000003_ai_artifacts.py`
- 导出到：`backend/app/models/__init__.py`

原因：

- 它不是 AI draft 的附属表，而是 Phase 1 之后所有 AI 结果的统一事实源。
- 它和 `execution` / `report` / `case` 都有关联，放在 `models` 层最自然。
- 现有仓库模式已经是 `model + repository + service` 三层，新增 artifact 继续沿用即可。

### `AI Copilot service` 放哪

- 新增编排服务：`backend/app/services/ai_copilot_service.py`
- 新增上下文组装器：`backend/app/services/ai_context_assembler.py`
- 新增 artifact 服务：`backend/app/services/ai_artifact_service.py`
- 新增 capability schema：`backend/app/schemas/ai_copilot.py`
- 新增 route：`backend/app/api/routes/ai_copilot.py`

原因：

- `ExecutionService` / `ReportService` 负责业务事实，不应直接承担 AI orchestration。
- `AiCaseDraftService` 已经偏“能力专用服务”，不适合作为 Phase 1 通用基类继续堆逻辑。
- 单独拆出 `ai_copilot_service` 后，三种 capability 共享一套 preview/apply/history 生命周期。

## Task 1: 建立 `ai_artifacts` 数据底座

**Files:**
- Create: `backend/app/models/ai_artifact.py`
- Create: `backend/app/repositories/ai_artifact_repository.py`
- Create: `alembic/versions/20260324_000003_ai_artifacts.py`
- Modify: `backend/app/models/__init__.py`
- Test: `tests/test_ai_copilot_phase1.py`

**Step 1: 写失败测试，约束 artifact 基础字段和状态流转**

- 新建 `tests/test_ai_copilot_phase1.py`
- 先写：
  - `test_ai_artifact_repository_creates_preview_artifact`
  - `test_ai_artifact_repository_lists_history_by_target`
  - `test_ai_artifact_repository_updates_status_to_applied`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase1.py -q
```

Expected:

- FAIL，提示 `AiArtifact` 或 repository 不存在

**Step 3: 实现最小模型和 repository**

- `AiArtifact` 字段至少包含：
  - `id`
  - `artifact_id`
  - `capability`
  - `target_type`
  - `target_id`
  - `project_id`
  - `suite_id`
  - `case_id`
  - `execution_id`
  - `report_id`
  - `input_json`
  - `output_json`
  - `warnings_json`
  - `status`
  - `provider`
  - `model`
  - `created_by_user_id`
  - `created_at`
  - `updated_at`
- `status` 先支持：
  - `draft`
  - `accepted`
  - `rejected`
  - `applied`
  - `superseded`

**Step 4: 写 migration**

- 新表：`ai_artifacts`
- 索引优先加在：
  - `artifact_id`
  - `(capability, target_type, target_id)`
  - `execution_id`
  - `report_id`
  - `case_id`

**Step 5: 重新跑测试**

Run:

```bash
pytest tests/test_ai_copilot_phase1.py -q
```

Expected:

- PASS 当前 repository 相关测试

## Task 2: 建立 AI Copilot 公共 contract

**Files:**
- Create: `backend/app/schemas/ai_copilot.py`
- Create: `backend/app/services/ai_artifact_service.py`
- Create: `backend/app/services/ai_context_assembler.py`
- Create: `backend/app/services/ai_copilot_service.py`
- Test: `tests/test_ai_copilot_phase1.py`

**Step 1: 写失败测试，锁定 preview 输出 contract**

- 先写：
  - `test_ai_copilot_preview_returns_artifact_envelope`
  - `test_ai_copilot_history_filters_by_capability_and_target`

**Step 2: 定义 schema**

- `AiCopilotPreviewResponse`
- `AiArtifactRead`
- `AiArtifactHistoryListRead`
- `AiDiagnosisPreviewRequest`
- `AiAssertionPreviewRequest`
- `AiAssertionApplyRequest`
- `AiReportSummaryPreviewRequest`
- `AiReportSummaryApplyRequest`

统一 preview 返回：

```json
{
  "artifact_id": "uuid",
  "capability": "diagnosis",
  "status": "draft",
  "warnings": [],
  "result": {}
}
```

**Step 3: 实现 `AiArtifactService`**

- 提供：
  - `create_draft_artifact(...)`
  - `accept_artifact(...)`
  - `reject_artifact(...)`
  - `mark_applied(...)`
  - `list_history(...)`
  - `get_artifact_or_404(...)`

**Step 4: 实现 `AiContextAssembler` 最小版**

- `build_execution_context(execution_id)`
- `build_report_context(report_id)`
- `build_case_context(case_id)`
- 要求：
  - 保留 source trace
  - 敏感字段脱敏
  - 控制文本长度

**Step 5: 实现 `AiCopilotService` 预留 capability dispatch**

- 暂时只支持：
  - `diagnosis`
  - `report_summary`
  - `assertion`

**Step 6: 跑测试**

Run:

```bash
pytest tests/test_ai_copilot_phase1.py -q
```

Expected:

- PASS contract 测试

## Task 3: 复用现有 execution/report/case 事实源

**Files:**
- Modify: `backend/app/services/execution_service.py`
- Modify: `backend/app/services/report_service.py`
- Possibly Modify: `backend/app/services/workspace_service.py`
- Test: `tests/test_ai_copilot_phase1.py`

**Step 1: 写失败测试，锁定 Phase 1 上下文最小事实集**

- `test_execution_context_contains_first_failure_and_retry_history`
- `test_report_context_contains_summary_and_recent_execution_reference`
- `test_case_context_contains_existing_assertions_and_recent_success_sample`

**Step 2: 补足读取侧而不是修改执行语义**

- 不改 execution 通过/失败规则
- 不改 report 文件生成逻辑
- 如需补字段，只补读取便利性，不改业务裁决

**Step 3: 明确 Phase 1 上下文来源**

- `diagnosis`:
  - `Execution.summary_json`
  - `Execution.items`
  - `Execution.error_message`
  - `ExecutionItem.request_json`
  - `ExecutionItem.response_json`
- `report_summary`:
  - `Report.metadata_json`
  - `Report.execution`
  - 同 suite 最近一次 execution
- `assertion`:
  - `ApiCase`
  - 最近成功 execution item
  - case 现有 `assertions_json`

**Step 4: 跑测试**

Run:

```bash
pytest tests/test_ai_copilot_phase1.py -q
```

Expected:

- PASS 上下文组装测试

## Task 4: 实现失败诊断 capability

**Files:**
- Modify: `backend/app/services/ai_copilot_service.py`
- Create or Modify: `backend/app/api/routes/ai_copilot.py`
- Modify: `backend/app/api/router.py`
- Modify: `frontend/src/api/services.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/ExecutionsPage.tsx`
- Test: `tests/test_ai_copilot_phase1.py`

**Step 1: 写失败测试**

- `test_diagnosis_preview_creates_draft_artifact`
- `test_diagnosis_history_returns_existing_artifacts`

**Step 2: 实现后端 preview**

- `POST /api/v1/ai-copilot/diagnosis/preview`
- `GET /api/v1/ai-copilot/diagnosis/history`

`result` schema 至少包含：

```json
{
  "diagnosis_category": "dependency_timeout",
  "root_cause_hypothesis": "......",
  "confidence": 0.83,
  "next_actions": ["..."]
}
```

**Step 3: 前端接入 `ExecutionsPage`**

- 在执行详情 drawer 增加：
  - `AI 诊断` 按钮
  - 诊断结果卡片
  - 历史记录入口

**Step 4: 跑后端测试和前端构建**

Run:

```bash
pytest tests/test_ai_copilot_phase1.py -q
npm run build
```

Expected:

- diagnosis API 测试通过
- frontend build 成功

## Task 5: 实现报告总结 capability

**Files:**
- Modify: `backend/app/services/ai_copilot_service.py`
- Modify: `backend/app/services/report_service.py`
- Modify: `backend/app/api/routes/ai_copilot.py`
- Modify: `frontend/src/api/services.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/ReportsPage.tsx`
- Test: `tests/test_ai_copilot_phase1.py`

**Step 1: 写失败测试**

- `test_report_summary_preview_creates_artifact`
- `test_report_summary_apply_writes_metadata_json_ai_summary`

**Step 2: 实现 preview + apply**

- `POST /api/v1/ai-copilot/report-summary/preview`
- `POST /api/v1/ai-copilot/report-summary/{artifact_id}/apply`

apply 规则：

- 只写 `report.metadata_json.ai_summary`
- 不修改 report 文件
- artifact 状态从 `draft -> accepted -> applied`

**Step 3: 前端接入 `ReportsPage`**

- 增加：
  - `AI 总结`
  - `重新生成`
  - `应用到报告元数据`
  - `复制摘要`

**Step 4: 跑测试**

Run:

```bash
pytest tests/test_ai_copilot_phase1.py -q
npm run build
```

Expected:

- PASS report summary 相关测试

## Task 6: 实现补断言 capability

**Files:**
- Modify: `backend/app/services/ai_copilot_service.py`
- Modify: `backend/app/api/routes/ai_copilot.py`
- Modify: `frontend/src/api/services.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Test: `tests/test_ai_copilot_phase1.py`

**Step 1: 写失败测试**

- `test_assertion_preview_returns_suggestions_for_case`
- `test_assertion_apply_appends_assertions_without_overwriting_by_default`
- `test_assertion_apply_requires_explicit_override_when_replacing_existing_assertions`

**Step 2: 实现 preview**

- `POST /api/v1/ai-copilot/assertions/preview`

`result` schema 至少包含：

```json
{
  "suggested_assertions": [
    {
      "type": "json_path",
      "path": "$.code",
      "operator": "==",
      "expected": 0,
      "reason": "......",
      "confidence": 0.89
    }
  ]
}
```

**Step 3: 实现 apply**

- `POST /api/v1/ai-copilot/assertions/{artifact_id}/apply`

apply 规则：

- 默认 append
- 只有显式 `override_existing=true` 才允许替换
- 最终仍写入 `api_cases.assertions_json`

**Step 4: 前端接入 `WorkspacePage` 的 case editor**

- 仅在编辑已有 case 时展示：
  - `AI 补断言`
  - 建议列表
  - 差异预览
  - `应用追加`
  - `覆盖应用`

**Step 5: 跑测试**

Run:

```bash
pytest tests/test_ai_copilot_phase1.py -q
npm run build
```

Expected:

- PASS assertion preview/apply 相关测试

## Task 7: 抽前端复用组件，避免页面级 AI 逻辑复制

**Files:**
- Create: `frontend/src/components/ai-copilot/AiCapabilityActionCard.tsx`
- Create: `frontend/src/components/ai-copilot/AiSuggestionPanel.tsx`
- Create: `frontend/src/components/ai-copilot/AiArtifactHistoryDrawer.tsx`
- Create: `frontend/src/components/ai-copilot/AiWarningList.tsx`
- Possibly Create: `frontend/src/components/ai-copilot/AiDiffPreview.tsx`
- Modify: `frontend/src/pages/ExecutionsPage.tsx`
- Modify: `frontend/src/pages/ReportsPage.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`

**Step 1: 先抽共同 UI contract**

- action button card
- warnings list
- suggestion panel
- artifact history drawer

**Step 2: 页面仅保留场景差异**

- `ExecutionsPage` 只负责执行对象和调用诊断能力
- `ReportsPage` 只负责报告对象和调用总结能力
- `WorkspacePage` 只负责当前 case 和调用补断言能力

**Step 3: 跑构建**

Run:

```bash
npm run build
```

Expected:

- build 成功，无 TypeScript 错误

## Task 8: 收口测试、回归验证、文档回写

**Files:**
- Modify: `tests/test_web_services.py`
- Modify: `docs/plans/2026-03-24-ai-copilot-roadmap.md`
- Possibly Modify: `README.md`

**Step 1: 增补集成测试**

- route 层 smoke test
- artifact status lifecycle test
- apply 幂等性测试

**Step 2: 跑完整最小回归**

Run:

```bash
pytest tests/test_web_services.py tests/test_ai_copilot_phase1.py -q
npm run build
```

Expected:

- 全部通过

**Step 3: 回写 roadmap**

- 标记 Phase 1 已完成项
- 记录与 roadmap 的偏差：
  - `ai_case_histories` 暂未并轨
  - 仅支持 `openai_compatible`
  - assertion apply 默认 append

**Step 4: 提交**

```bash
git add alembic backend frontend tests docs/plans/2026-03-24-ai-copilot-roadmap.md
git commit -m "feat: add ai copilot phase 1 foundation"
```

## 实施顺序铁律

1. 先落 `ai_artifacts`，再写 capability。
2. 先跑 preview，后做 apply。
3. 先接 execution/report/case 现有事实源，不改现有业务裁决。
4. 所有 capability 先 schema 化，再接前端。
5. 前端只展示 preview 结果，所有 apply 必须显式确认。

## 验收标准

- `ExecutionsPage` 能对单条 execution 生成并查看 AI 诊断。
- `ReportsPage` 能生成、查看、应用 AI 总结到 `report.metadata_json.ai_summary`。
- `WorkspacePage` 能对已有 case 预览 AI 断言建议并应用。
- 三类能力的 preview/apply/history 都进入 `ai_artifacts`。
- 没有任何 capability 直接绕过确定性 apply 写业务对象。

## 风险提示

- 如果一开始就尝试把 `ai_case_histories` 一并改造成统一 artifact，会拖慢 Phase 1 主线。
- 如果把 capability 逻辑直接塞进 `ExecutionService` / `ReportService` / `WorkspacePage`，后续 Phase 2 一定分裂。
- 如果 apply 不做默认 append 和显式确认，补断言质量会不可控。

Plan complete and saved to `docs/plans/2026-03-24-ai-copilot-phase1-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
