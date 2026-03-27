# AI Copilot Phase 4 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
> Status (2026-03-25): Complete.
> Delivered: lineage bridge via `ai_artifact_links`, case-first execution preparation injection, unified provider registry/client, artifact telemetry + audit failure taxonomy, and `WorkspacePage` execution preparation/lineage UI.
> Verification: `pytest tests/test_ai_copilot_phase1.py tests/test_ai_copilot_phase2.py tests/test_ai_copilot_phase3.py tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q` and `npm run build`.
> Deviations kept intentionally: no suite-level preparation orchestration, no runtime mock platform, and no multi-provider routing/fallback beyond the unified `openai_compatible` runtime path.

**Goal:** Productize the shipped AI Copilot system by adding artifact lineage governance, case-first execution preparation, provider abstraction, and release-grade observability.

**Architecture:** Reuse the shipped `AI Copilot` backbone from Phases 1-3 and avoid introducing any new end-user capability family. Phase 4 only hardens the system around four seams: `ai_artifacts <-> ai_case_histories` lineage, deterministic execution-time preparation for `test_data/mock`, provider/client abstraction for LLM-backed flows, and production-grade telemetry plus regression gates. Keep `AI -> preview -> review -> deterministic apply` unchanged.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, React 19, TypeScript, Ant Design, pytest.

---

## 审计结论

1. `Phase 1/2/3` 已经把 7 个 capability 都接进统一 `AI Copilot` 主链，当前最大问题已经不是“少功能”，而是“缺治理”。
2. `ai_case_histories` 仍然是独立历史宇宙，`test_point -> draft` 的桥虽然能用，但 lineage 仍然靠隐式约定，不利于后续审计、回放和追踪。
3. `test_data/mock` 目前只停留在 `metadata/apply/export`，还没有真正进入执行前准备链路；这会让 Phase 3 产物停留在“建议可看”，而不是“可稳定使用”。
4. 当前 LLM 型能力仍以 `provider/base_url/api_key/model` 直传为主，缺少统一 provider registry 和调用观测口径，后面扩 provider 会快速漂移。
5. `ExecutionService` 是最合适的 Phase 4 落位点，因为真正的 deterministic 注入必须发生在 `_build_case_payload()` 附近，而不是在前端临时拼请求。

## Phase 4 范围

### 本期只做

- `ai_artifacts` 与 `ai_case_histories` 的 lineage bridge
- `test_data/mock` 的 case-first execution preparation
- provider registry / unified AI client abstraction
- AI telemetry / audit / regression gate 补强
- 前端执行前准备入口与 lineage 展示

### 本期不做

- 新 capability
- suite 级批量 test-data/mock 注入编排
- runtime mock platform
- dataset 独立持久化模型
- 多 provider 策略路由或自动 fallback
- AI 自动修复测试脚本

## 落位决策

### `ai_case_histories` 怎么处理

- 不做强迁移
- 新增轻量 bridge：`ai_artifact_links`
- 让 `ai_artifacts` 可以指向：
  - 派生 artifact
  - `ai_case_history` 这种外部历史对象

原因：
- 当前最需要的是 traceability，不是大迁移
- 先 bridge 再决定是否并轨，风险更低

### `test_data/mock` 怎么进入执行

- 只做 case 级 execution first cut
- 执行请求显式带入 preparation 选择：
  - `selected_test_data_variant_ids`
  - `selected_mock_template_ids`
- 最终在 `ExecutionService._build_case_payload()` 做 deterministic 注入

原因：
- 这能把 Phase 3 产物真正接进可用链路
- 又不会把 suite 批量运行、环境切换、profile 编排一次性拖进来

### provider 怎么收口

- 增加 provider registry
- `ai_case_draft_service`、`ai_test_point_draft_service` 和后续所有 LLM 型服务只依赖统一 client 接口

原因：
- 现在的 `provider/base_url/api_key/model` 直传方式可用，但不可治理
- Phase 4 需要先切掉“每个服务自己组 provider 细节”的趋势

### telemetry 怎么做

- telemetry 进入两层：
  - `ai_artifacts` 级调用元数据
  - audit log 级用户动作与失败分类
- deterministic capability 也要记录“无 LLM 调用”的明确口径

原因：
- 没有统一口径，后面根本无法比较 cost、latency、失败率

## Task 1: 冻结 Phase 4 contract

**Files:**
- Modify: `backend/app/schemas/ai_copilot.py`
- Modify: `backend/app/schemas/execution.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/services.ts`
- Create: `tests/test_ai_copilot_phase4.py`

**Step 1: 写失败测试，锁定 Phase 4 contract**

- 先写：
  - `test_phase4_execution_preparation_request_contract`
  - `test_phase4_artifact_lineage_contract`
  - `test_phase4_provider_trace_contract`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py -q
```

Expected:

- FAIL，提示 execution preparation / lineage / telemetry schema 缺失

**Step 3: 定义最小 schema**

- 为 execution 增加 preparation request/read：
  - `AiExecutionPreparationSelection`
  - `AiExecutionPreparationRead`
- 为 lineage 增加 read model：
  - `AiArtifactLineageNodeRead`
  - `AiArtifactLineageRead`
- 为 provider/trace 增加 read model：
  - `AiProviderConfigRead`
  - `AiCallTraceRead`

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py -q
```

Expected:

- PASS contract 测试

**Step 5: Commit**

```bash
git add tests/test_ai_copilot_phase4.py backend/app/schemas/ai_copilot.py backend/app/schemas/execution.py frontend/src/api/types.ts frontend/src/api/services.ts
git commit -m "feat: add phase4 copilot governance contracts"
```

## Task 2: 建立 artifact lineage bridge

**Files:**
- Create: `backend/app/models/ai_artifact_link.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/registry.py`
- Create: `backend/app/repositories/ai_artifact_link_repository.py`
- Create: `backend/app/services/ai_artifact_lineage_service.py`
- Modify: `backend/app/services/ai_test_point_draft_service.py`
- Modify: `backend/app/services/ai_case_history_service.py`
- Modify: `backend/app/api/routes/ai_copilot.py`
- Create: `alembic/versions/20260325_000004_ai_artifact_links.py`
- Test: `tests/test_ai_copilot_phase4.py`
- Test: `tests/test_ai_copilot_web_routes.py`

**Step 1: 写失败测试，锁定 bridge 行为**

- 先写：
  - `test_artifact_lineage_links_test_point_artifact_to_case_history`
  - `test_artifact_lineage_lists_derived_nodes_in_order`
  - `test_artifact_lineage_route_returns_bridge_nodes`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- FAIL，提示 `ai_artifact_links` 表或 lineage service 不存在

**Step 3: 实现最小 bridge**

- 新增 `ai_artifact_links` 表，字段至少包括：
  - `source_artifact_id`
  - `target_artifact_id`
  - `target_resource_type`
  - `target_resource_key`
  - `link_type`
- 在 `test_point -> generate_drafts` 成功后写入 bridge：
  - `artifact -> ai_case_history`
- 新增 lineage 查询接口：
  - `GET /api/v1/ai-copilot/artifacts/{artifact_id}/lineage`

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- PASS lineage 测试

**Step 5: Commit**

```bash
git add backend/app/models/ai_artifact_link.py backend/app/models/__init__.py backend/app/models/registry.py backend/app/repositories/ai_artifact_link_repository.py backend/app/services/ai_artifact_lineage_service.py backend/app/services/ai_test_point_draft_service.py backend/app/services/ai_case_history_service.py backend/app/api/routes/ai_copilot.py alembic/versions/20260325_000004_ai_artifact_links.py tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py
git commit -m "feat: add ai artifact lineage bridge"
```

## Task 3: 实现 case-first execution preparation

**Files:**
- Create: `backend/app/services/ai_execution_preparation_service.py`
- Modify: `backend/app/services/workspace_service.py`
- Modify: `backend/app/schemas/execution.py`
- Test: `tests/test_ai_copilot_phase4.py`

**Step 1: 写失败测试，锁定 preparation 选择逻辑**

- 先写：
  - `test_execution_preparation_resolves_selected_test_data_variants`
  - `test_execution_preparation_resolves_selected_mock_templates`
  - `test_execution_preparation_rejects_unknown_variant_or_template`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py -q
```

Expected:

- FAIL，提示 preparation service 缺失

**Step 3: 实现最小 preparation service**

- 从 `api_cases.metadata_json` 中解析：
  - `ai_test_data_variants`
  - `ai_mock_templates`
- 根据显式选择生成 execution-time plan：
  - 最终请求 body
  - mock 响应模板清单
  - execution summary 可追踪元数据

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py -q
```

Expected:

- PASS preparation service 测试

**Step 5: Commit**

```bash
git add backend/app/services/ai_execution_preparation_service.py backend/app/services/workspace_service.py backend/app/schemas/execution.py tests/test_ai_copilot_phase4.py
git commit -m "feat: add ai execution preparation service"
```

## Task 4: 把 preparation 接进执行链路

**Files:**
- Modify: `backend/app/services/execution_service.py`
- Modify: `backend/app/api/routes/executions.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/services.ts`
- Test: `tests/test_ai_copilot_phase4.py`
- Test: `tests/test_ai_copilot_web_routes.py`
- Test: `tests/test_web_services.py`

**Step 1: 写失败测试，锁定 execution 注入行为**

- 先写：
  - `test_run_case_now_applies_selected_test_data_variant_to_request_body`
  - `test_run_case_now_persists_preparation_summary_into_execution`
  - `test_execution_route_accepts_case_preparation_payload`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q
```

Expected:

- FAIL，提示 execution request 不接受 preparation 或执行结果未记录 preparation

**Step 3: 做最小链路接入**

- 扩展 `ExecutionCreateRequest`
- `executions` route 支持 case 级 preparation payload
- `ExecutionService.run_case_now()` 接收 preparation
- 在 `_build_case_payload()` 做 deterministic 注入
- 在 `execution.summary_json` 记录：
  - selected variant/template ids
  - 是否命中 metadata baseline
  - 最终 preparation 摘要

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q
```

Expected:

- PASS execution preparation 测试

**Step 5: Commit**

```bash
git add backend/app/services/execution_service.py backend/app/api/routes/executions.py frontend/src/api/types.ts frontend/src/api/services.ts tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py
git commit -m "feat: connect ai preparation into case execution"
```

## Task 5: provider registry 与 unified AI client

**Files:**
- Create: `backend/app/services/ai_provider_registry.py`
- Create: `backend/app/services/ai_client_service.py`
- Modify: `backend/app/services/ai_case_draft_service.py`
- Modify: `backend/app/services/ai_test_point_draft_service.py`
- Modify: `backend/app/services/llm_case_generation_service.py`
- Modify: `backend/app/core/config.py`
- Test: `tests/test_ai_copilot_phase4.py`

**Step 1: 写失败测试，锁定 provider abstraction**

- 先写：
  - `test_provider_registry_resolves_openai_compatible_runtime`
  - `test_llm_draft_flow_consumes_unified_ai_client`
  - `test_provider_registry_rejects_unknown_provider`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py -q
```

Expected:

- FAIL，提示 provider registry / unified client 缺失

**Step 3: 实现最小 abstraction**

- provider registry 统一解析：
  - provider
  - base_url
  - api_key
  - model
  - timeout
- draft/test-point 相关 LLM 流改为依赖统一 client 接口
- 保持当前 `openai_compatible` 行为不变

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py -q
```

Expected:

- PASS provider abstraction 测试

**Step 5: Commit**

```bash
git add backend/app/services/ai_provider_registry.py backend/app/services/ai_client_service.py backend/app/services/ai_case_draft_service.py backend/app/services/ai_test_point_draft_service.py backend/app/services/llm_case_generation_service.py backend/app/core/config.py tests/test_ai_copilot_phase4.py
git commit -m "refactor: add unified ai provider registry"
```

## Task 6: 补 AI telemetry / audit / failure taxonomy

**Files:**
- Modify: `backend/app/models/ai_artifact.py`
- Modify: `backend/app/repositories/ai_artifact_repository.py`
- Modify: `backend/app/services/ai_artifact_service.py`
- Modify: `backend/app/services/ai_copilot_service.py`
- Modify: `backend/app/api/routes/ai_copilot.py`
- Create: `alembic/versions/20260325_000005_ai_artifact_telemetry.py`
- Test: `tests/test_ai_copilot_phase4.py`
- Test: `tests/test_ai_copilot_web_routes.py`

**Step 1: 写失败测试，锁定 telemetry 行为**

- 先写：
  - `test_artifact_persists_call_trace_for_llm_capability`
  - `test_artifact_marks_deterministic_capability_without_llm_call`
  - `test_ai_route_audit_log_includes_failure_category`

**Step 2: 跑测试确认失败**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- FAIL，提示 telemetry 字段或 trace 记录缺失

**Step 3: 实现最小 telemetry**

- 为 `ai_artifacts` 补充可查询调用元数据，至少包括：
  - `call_mode`
  - `latency_ms`
  - `failure_category`
  - `trace_json`
- `AiCopilotService` 与 LLM 型能力统一写入 trace
- deterministic capability 明确写入 `call_mode=deterministic`

**Step 4: 跑测试确认通过**

Run:

```bash
pytest tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py -q
```

Expected:

- PASS telemetry 测试

**Step 5: Commit**

```bash
git add backend/app/models/ai_artifact.py backend/app/repositories/ai_artifact_repository.py backend/app/services/ai_artifact_service.py backend/app/services/ai_copilot_service.py backend/app/api/routes/ai_copilot.py alembic/versions/20260325_000005_ai_artifact_telemetry.py tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py
git commit -m "feat: add ai artifact telemetry"
```

## Task 7: 前端接 execution preparation 和 lineage UI

**Files:**
- Create: `frontend/src/components/ai-copilot/AiExecutionPreparationPanel.tsx`
- Modify: `frontend/src/components/ai-copilot/AiArtifactHistoryDrawer.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/services.ts`
- Test: `frontend` build only

**Step 1: 写最小前端状态验收清单**

- 锁定 3 个场景：
  - case 编辑区能选择已保存的 test-data/mock 产物后执行
  - artifact history 能看到 lineage/derived link
  - preparation 失败时错误能明确落在 UI 上

**Step 2: 实现最小 UI**

- `WorkspacePage` 新增 execution preparation 区块
- `AiExecutionPreparationPanel` 负责：
  - 列出已保存 variant/template
  - 选择后触发 case execution
  - 显示本次 execution 准备摘要
- `AiArtifactHistoryDrawer` 增加 lineage 展示入口

**Step 3: 跑构建确认通过**

Run:

```bash
npm run build
```

Expected:

- PASS，允许保留 chunk warning，但不能有类型错误或构建失败

**Step 4: Commit**

```bash
git add frontend/src/components/ai-copilot/AiExecutionPreparationPanel.tsx frontend/src/components/ai-copilot/AiArtifactHistoryDrawer.tsx frontend/src/pages/WorkspacePage.tsx frontend/src/api/types.ts frontend/src/api/services.ts
git commit -m "feat: add ai execution preparation ui"
```

## Task 8: 收口验证、性能与文档回写

**Files:**
- Modify: `docs/plans/2026-03-24-ai-copilot-roadmap.md`
- Modify: `docs/plans/2026-03-25-ai-copilot-phase4-implementation-plan.md`
- Modify: `README.md`
- Test: `tests/test_ai_copilot_phase1.py`
- Test: `tests/test_ai_copilot_phase2.py`
- Test: `tests/test_ai_copilot_phase3.py`
- Test: `tests/test_ai_copilot_phase4.py`
- Test: `tests/test_ai_copilot_web_routes.py`
- Test: `tests/test_web_services.py`

**Step 1: 跑全量验证**

Run:

```bash
pytest tests/test_ai_copilot_phase1.py tests/test_ai_copilot_phase2.py tests/test_ai_copilot_phase3.py tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q
npm run build
```

Expected:

- 后端测试全绿
- 前端构建通过

**Step 2: 做 release gate 检查**

- 检查 append/override 幂等性是否仍然成立
- 检查 execution preparation 不会静默改写 case metadata
- 检查 lineage route 不暴露敏感信息
- 记录大 chunk warning 是否仍存在

**Step 3: 回写文档**

- 在 roadmap 顶部新增 `Phase 4 complete` 状态更新
- 在本 plan 顶部新增完成状态、偏差和验证命令
- 在 `README.md` 补一段：
  - execution preparation 使用方式
  - lineage/traceability 使用方式

**Step 4: Commit**

```bash
git add docs/plans/2026-03-24-ai-copilot-roadmap.md docs/plans/2026-03-25-ai-copilot-phase4-implementation-plan.md README.md
git commit -m "docs: finalize ai copilot phase4 rollout"
```

## 验收标准

- `test_point -> ai_case_history` 关系可以通过 lineage 查询回放
- 用户可以在 case 编辑区选择已保存的 `test_data/mock` 产物后执行 case
- 执行记录中能看到 preparation 摘要，不需要猜本次到底用了什么
- LLM 型能力统一走 provider registry，不再由各 service 自己解释 provider 参数
- `ai_artifacts` 能区分 deterministic 与 llm-backed 调用，并记录统一 trace 口径

## 已知风险

- 如果把 suite 级 preparation 一起做，会显著扩大范围；本计划明确只做 case-first
- `ai_artifact_links` 是 bridge，不是终局；是否最终并轨 `ai_case_histories` 仍需后续决策
- 前端 bundle warning 大概率仍会存在，除非单独立项做拆包

## 推荐执行顺序

1. 先做 contract
2. 再做 lineage bridge
3. 再接 case-first execution preparation
4. 再做 provider registry 和 telemetry
5. 最后做前端与收口
