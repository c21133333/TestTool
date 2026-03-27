# Eazy Test AI Copilot Roadmap

> Status Update (2026-03-25): Phase 4 is complete. Delivered capabilities include `ai_artifact_links` lineage bridging, case-first execution preparation wired into `ExecutionService`, unified provider/runtime resolution through `ai_provider_registry` + `ai_client_service`, and release-grade artifact telemetry with `call_mode`, `latency_ms`, `failure_category`, and `trace_json`. Frontend delivery now exposes execution preparation and lineage lookup directly inside `WorkspacePage`, so saved `test_data/mock` artifacts can be selected for a single case execution and traced back through artifact history. Known deviations: preparation remains case-first rather than suite-orchestrated, runtime mock is still out of scope, and provider routing still intentionally stays on a single `openai_compatible` family. Verification completed on 2026-03-25: `pytest tests/test_ai_copilot_phase1.py tests/test_ai_copilot_phase2.py tests/test_ai_copilot_phase3.py tests/test_ai_copilot_phase4.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q` and `npm run build`.
> Status Update (2026-03-25): Phase 3 is complete. Delivered capabilities include deterministic `test_data` and `mock` seed builders, unified `preview/history/apply/export` flows, and case-editor integrations for replaying history, appending or overriding curated outputs, and exporting JSON bundles. Known deviations: `test_data` still applies into `api_cases.metadata_json.ai_test_data_variants`, `mock` still applies into `api_cases.metadata_json.ai_mock_templates`, no runtime mock platform was introduced, and `ai_case_histories` remains separate from `ai_artifacts`. Verification completed on 2026-03-25: `pytest tests/test_ai_copilot_phase1.py tests/test_ai_copilot_phase2.py tests/test_ai_copilot_phase3.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q` and `npm run build`.
> Status Update (2026-03-24): Phase 1 is complete. Delivered foundations include `ai_artifacts`, unified `AI Copilot` services/contracts, richer context assembly, and shared frontend AI components. Delivered capabilities include `diagnosis`, `report_summary`, and `assertion`. Known deviations: `ai_case_histories` is not merged yet, provider support remains `openai_compatible`, and assertion apply defaults to append unless `override_existing=true`. Verification completed on 2026-03-24: `pytest tests/test_ai_copilot_phase1.py -q`, `pytest tests/test_web_services.py tests/test_ai_copilot_web_routes.py -q`, and `npm run build`.
> Status Update (2026-03-25): Phase 2 is complete. Delivered capabilities include deterministic `coverage` scanning, `test_point` preview/history, project/suite target support, and the bridge from selected test points into the existing `ai_case_histories` draft workflow. Frontend delivery now exposes `coverage -> prompt seed -> test point -> draft preview/import` inside `WorkspacePage` and `AiCaseGenerationPanel`. Known deviations: `coverage -> test_point` transfer remains a frontend prompt-seeding action rather than a backend artifact-to-artifact apply flow, and `ai_case_histories` still remains separate from `ai_artifacts`. Verification completed on 2026-03-25: `pytest tests/test_ai_copilot_phase1.py tests/test_ai_copilot_phase2.py tests/test_ai_copilot_web_routes.py tests/test_web_services.py -q` and `npm run build`.

- Phase 1 flow shipped as `context -> preview -> ai_artifacts -> review -> deterministic apply`.
- Phase 2 flow shipped as `coverage scan -> suggested points/prompt seed -> test point preview -> selected points -> draft batch -> ai_case_histories/import`.
- Phase 3 flow shipped as `case context -> deterministic seeds -> preview/history -> metadata apply/export`, covering both `test_data` and `mock`.
- Phase 4 flow shipped as `saved artifact -> execution preparation selection -> deterministic injection -> execution summary + lineage + telemetry`.
- New integration coverage includes diagnosis preview/history, report summary preview/apply lifecycle, and assertion append idempotence.
- Added Phase 2 route/integration coverage for project/suite targets, project-level test-point-to-draft mainline, and test-point history replay.
- Added Phase 3 route/integration coverage for `test_data` and `mock` preview/apply/export mainlines plus append idempotence.
- Added Phase 4 route/integration coverage for execution preparation payloads, lineage route reads, provider trace contracts, and AI route failure taxonomy.

## 1. 文档目标

本文档用于沉淀 `Eazy Test Web` 在接口测试场景下的 AI 能力建设方案，作为后续分阶段实现的唯一长期上下文载体。

这份文档的目标不是讨论“AI 能不能做”，而是明确：

- 现阶段选择什么架构方案
- 每个 AI 能力落在哪个产品环节
- 哪些能力先做，哪些后做
- AI 输出如何被系统确定性接管
- 后续分阶段执行时需要遵守哪些边界

本文档后续会持续更新。新的实现、偏差、接口调整、阶段完成情况，都应回写到本文档，而不是只留在对话上下文里。

## 2. 决策结论

### 2.1 选型结论

当前选择 **方案 B：统一 AI Copilot 层**。

不采用“每个功能单独接一次 LLM”的原因是：

- prompt 会快速分裂
- 历史记录会分散
- 前后端数据结构难以复用
- 后续维护成本会比首轮开发成本更高

### 2.2 核心原则

AI 在本系统中的定位是：

- 负责：建议、补全、归因、总结、推荐
- 不负责：最终判定、最终落库、最终执行结果裁决

也就是说：

- AI 可以提出断言建议，但不能直接决定 case 通过与否
- AI 可以给出失败归因，但不能替代确定性错误分类
- AI 可以总结报告，但不能修改原始执行结果

### 2.3 一句话架构

把 AI 能力建设成一层统一的 `AI Copilot` 能力层，挂接到现有的：

- 用例设计链路
- 用例编辑链路
- 执行分析链路
- 报告解读链路

而不是让每个页面各自长出一套 AI 逻辑。

---

## 3. 当前工程基础

当前工程已经具备 AI 能力扩展所需的主要底座：

### 3.1 已有的 AI 入口

已存在基于 Markdown 文档生成接口用例草稿并导入的闭环：

- 文档解析
- LLM 生成 draft
- 草稿预览与校验
- 人工确认
- 导入 suite / case

相关实现位置：

- `backend/app/api/routes/ai_case_drafts.py`
- `backend/app/services/ai_case_draft_service.py`
- `backend/app/services/llm_case_generation_service.py`
- `backend/app/services/ai_case_import_service.py`
- `backend/app/services/ai_case_history_service.py`
- `frontend/src/components/ai/AiCaseGenerationPanel.tsx`
- `frontend/src/components/ai/AiCaseDraftTable.tsx`

### 3.2 已有的执行与报告底座

当前系统已经具备以下能力，这些能力可以直接成为 AI 的上下文来源：

- Case / Suite 执行
- 失败分类
- Retry 元数据
- 报告生成
- 执行详情查看

相关实现位置：

- `backend/app/services/execution_service.py`
- `backend/app/models/execution.py`
- `backend/app/services/report_service.py`
- `frontend/src/pages/ExecutionsPage.tsx`
- `frontend/src/pages/ReportsPage.tsx`

### 3.3 现阶段不需要推翻重来

现有架构已经证明：

- 平台具备 Web-first 的测试编排能力
- AI 已经进入到“生成用例”环节
- 执行与报告数据结构基本稳定

因此后续 AI 建设应遵循：

- 复用现有执行模型
- 复用现有报告模型
- 复用现有 AI case draft 历史思路
- 在此基础上抽一层统一 AI Copilot 能力，而不是重新发明整条链路

---

## 4. 总体架构设计

## 4.1 总体目标

统一管理以下 7 类能力：

1. 测试点生成
2. 智能补断言
3. 失败诊断
4. 测试数据生成
5. 覆盖率缺口分析
6. Mock 辅助
7. 报告总结

这些能力共享一套：

- 上下文组装逻辑
- AI 调用逻辑
- 结果存档逻辑
- 人工确认逻辑
- 落库应用逻辑

## 4.2 逻辑分层

建议新增统一 AI Copilot 分层：

```text
现有业务数据
  - project / suite / case
  - execution / execution_item
  - report
  - markdown 文档 / AI draft history

        |
        v

AI Context Assembler
  - 收集上下文
  - 压缩上下文
  - 标准化输入快照

        |
        v

AI Task Service
  - 按 capability 调度 prompt
  - 调用 LLM
  - 校验输出 schema
  - 记录 artifact

        |
        v

AI Artifact Store
  - 保存输入、输出、状态、版本

        |
        v

Deterministic Applier
  - 用户确认后将建议转为系统标准结构
  - 保证落库和执行逻辑确定性
```

## 4.3 核心设计原则

### 原则 1：AI 只出建议，不直接改核心业务对象

例如：

- 补断言时，AI 输出的是 `assertion suggestions`
- 覆盖率扫描时，AI 输出的是 `missing dimensions` 和 `suggested points`
- 失败诊断时，AI 输出的是 `diagnosis hypothesis`

真正把建议写回 case、report、mock 配置时，必须经过用户确认，并通过确定性代码转换。

### 原则 2：上下文组装统一收口

同一条 execution 详情、同一份 report、同一个 case，不应该在不同 AI 功能中各自拼一套上下文。

应统一由 `AI Context Assembler` 来负责：

- 拉哪些字段
- 截取哪些片段
- 如何脱敏
- 如何做 token budget 控制

### 原则 3：AI 结果必须可追溯

任何 AI 输出都要能够回答：

- 当时输入了什么上下文
- 用的什么 capability
- 用的哪个模型
- 输出了什么
- 最终有没有被接受和应用

这要求所有 AI 结果统一进入 `artifact store`。

### 原则 4：平台最终规则必须是确定性的

例如：

- 断言最终仍然是 `assertions_json`
- 报告最终仍然来自 execution / report 原始数据
- case 通过失败仍由 execution runtime 决定

AI 不能绕开现有规则引擎。

---

## 5. 统一 AI Copilot 组件设计

## 5.1 AI Context Assembler

### 职责

负责为不同能力构建标准化上下文。

### 输入来源

- `Project`
- `Suite`
- `ApiCase`
- `Execution`
- `ExecutionItem`
- `Report`
- Markdown 文档
- AI 历史草稿
- 环境配置
- 历史成功 / 失败样本

### 输出结构建议

```json
{
  "capability": "assertion",
  "target_type": "case",
  "target_id": 123,
  "context_version": "v1",
  "input_snapshot": {
    "case": {},
    "recent_success_samples": [],
    "recent_failure_samples": [],
    "doc_excerpt": "",
    "execution_summary": {}
  }
}
```

### 设计要求

- 控制上下文长度
- 保留 source trace
- 对敏感字段做脱敏
- 保证不同 capability 能共享同一种基础上下文格式

## 5.2 AI Task Service

### 职责

按能力类型驱动 AI 调用。

### 建议的 capability 枚举

- `test_point`
- `assertion`
- `diagnosis`
- `test_data`
- `coverage`
- `mock`
- `report_summary`

### 统一输入

- capability
- target_type
- target_id
- input_snapshot
- runtime model config
- optional prompt hints

### 统一输出

- result_json
- warnings
- confidence
- apply_hint

### 设计要求

- 每种 capability 使用独立 schema
- 输出必须强校验
- 输出失败时返回明确错误原因
- 所有请求必须记录 artifact

## 5.3 AI Artifact Store

### 目标

把 AI 产物从“临时结果”变成“可治理资产”。

### 建议新增数据表

建议新增统一表：`ai_artifacts`

建议字段：

- `id`
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

### status 建议

- `draft`
- `accepted`
- `rejected`
- `applied`
- `superseded`

### 价值

- 便于追踪 AI 结果质量
- 便于后续做反馈学习
- 便于页面展示历史建议
- 便于后续做审计和回溯

## 5.4 Deterministic Applier

### 职责

将 AI 建议转为系统已存在的数据结构。

### 例子

- 断言建议 -> `assertions_json`
- 测试点建议 -> case draft input
- 测试数据建议 -> dataset / variables
- mock 建议 -> mock rule schema
- 报告总结 -> `report.metadata_json.ai_summary`

### 原则

- 不允许 AI 输出直接落库
- 必须先过 schema 校验
- 必须保留人工确认步骤

---

## 6. 能力详细设计

## 6.1 能力一：测试点生成

### 目标

把当前“直接生成接口用例”升级为“两阶段生成”：

1. 先生成测试点
2. 再按选中的测试点生成 case draft

### 为什么先做测试点

直接让 AI 出 case，容易出现：

- 重复
- 颗粒度不一致
- 全是 happy path
- 和已有 case 重叠

测试点层更适合做人机协作。

### 输入

- Markdown / OpenAPI / 手工接口描述
- Project / Suite 上下文
- 已有 case 列表
- 可选的历史缺陷标签

### 输出建议结构

```json
{
  "test_points": [
    {
      "id": "tp_xxx",
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

### 前端入口

建议放在现有 `AiCaseGenerationPanel` 前面，加一步：

- `生成测试点`
- `选择测试点`
- `基于测试点生成草稿`

### 后端建议

新增 route / service：

- `POST /api/v1/ai-copilot/test-points/preview`
- `POST /api/v1/ai-copilot/test-points/generate-drafts`

### 第一阶段边界

先只支持：

- happy path
- negative path
- boundary path
- auth path

暂不支持复杂状态机和跨接口业务流。

---

## 6.2 能力二：智能补断言

### 目标

为已有 case 自动补充高价值断言，提升 case 质量，而不是单纯增加 case 数量。

### 典型场景

当前很多 case 可能只校验：

- `status_code == 200`

但没有校验：

- 业务码
- 字段类型
- 必填字段
- 分页结构
- 响应耗时
- 关键业务字段约束

### 输入

- `ApiCase`
- 最近成功执行样本
- 文档片段
- 现有 `assertions_json`

### 输出建议结构

```json
{
  "suggested_assertions": [
    {
      "type": "json_path",
      "path": "$.code",
      "operator": "==",
      "expected": 0,
      "reason": "成功响应示例中 code 为 0",
      "confidence": 0.89
    }
  ]
}
```

### 支持的断言类型

第一期建议支持：

- `status_code`
- `json_path exists`
- `json_path equals`
- `json_path type`
- `json_path in`
- `response_time`
- `header exists`

### 产品交互

Case 编辑页增加：

- `AI 补断言`
- `预览建议`
- `选择应用`
- `差异对比`

### 落库规则

- 默认只追加，不直接覆盖
- 覆盖现有断言时必须二次确认
- 应用后仍存储到标准 `assertions_json`

### 风险控制

- 不允许 AI 发明文档中不存在的复杂业务不变量
- 对低置信度断言标记 warning

---

## 6.3 能力三：失败诊断

### 目标

在 execution 失败后，用 AI 先做一次“故障分诊”，减少人工排查时间。

### 典型收益

当前已有执行失败分类，但仍需要人工判断：

- 是环境问题还是代码回归
- 是 token 过期还是断言写错
- 是依赖超时还是数据污染

AI 适合做第一轮归因建议。

### 输入

- `Execution`
- `ExecutionItem`
- `summary_json`
- `failure_breakdown`
- `first_failure`
- request / response
- `execution_meta.retry_history`

### 输出建议结构

```json
{
  "diagnosis_category": "dependency_timeout",
  "root_cause_hypothesis": "下游依赖请求多次 timeout，重试后仍失败，更像环境或依赖抖动问题。",
  "confidence": 0.83,
  "next_actions": [
    "检查依赖服务健康状态",
    "检查同时间段其他 suite 是否也出现 timeout"
  ]
}
```

### 建议分类枚举

- `environment_issue`
- `auth_issue`
- `test_data_issue`
- `assertion_too_strict`
- `real_regression`
- `dependency_timeout`
- `mock_mismatch`
- `unknown`

### 产品交互

在 `ExecutionsPage` 详情中增加：

- `AI 诊断`
- `查看诊断历史`
- `复制建议`

### 设计原则

- 不改变 execution 原始状态
- 只附加诊断建议
- 诊断结果应支持重新生成

### 第一阶段范围

只做单条 execution 诊断，不做跨 execution 聚类。

---

## 6.4 能力四：测试数据生成

### 目标

降低造数成本，让用户更快生成有效、边界、异常参数组合。

### 输入

- Case body / query / path 参数
- metadata
- 环境变量
- 历史成功样本

### 输出建议结构

```json
{
  "data_variants": [
    {
      "name": "required_field_missing",
      "payload": {
        "username": "",
        "password": "demo123"
      },
      "expected_category": "validation_error"
    }
  ],
  "precondition_steps": [],
  "cleanup_steps": []
}
```

### 分两层推进

#### 第一层：参数变体生成

先生成：

- 空值
- 必填缺失
- 长度边界
- 枚举非法值
- 金额边界
- 日期边界

#### 第二层：前后置数据建议

后续再支持：

- 创建前置资源
- 清理测试脏数据
- 账号准备建议

### 产品交互

Case 编辑页增加：

- `AI 生成数据集`
- `保存为数据变体`

Suite 执行页后续可增加：

- `选择数据集执行`

### 第一阶段边界

先不接数据库，不直接做自动造数脚本，只做 HTTP 级请求变体。

---

## 6.5 能力五：覆盖率缺口分析

### 目标

明确回答“还有什么没测”。

### 关键思想

这项能力不能完全交给 AI。应该先有确定性 coverage matrix，再让 AI 做解释和建议。

### 建议先做的确定性维度

#### 接口维度

- method
- path

#### 场景维度

- happy path
- negative path
- boundary path
- auth
- idempotent
- pagination

#### 断言维度

- status
- business code
- body field
- schema
- latency

### AI 负责的部分

- 缺口解释
- 风险排序
- 建议优先补哪些测试点

### 输出建议结构

```json
{
  "coverage_score": 67,
  "missing_dimensions": [
    {
      "endpoint": "POST /api/login",
      "dimension": "boundary",
      "reason": "已有 case 仅覆盖成功和参数错误，缺少边界输入"
    }
  ],
  "suggested_points": []
}
```

### 产品交互

在 Project / Suite 页面增加：

- `覆盖率扫描`
- `缺口列表`
- `一键转测试点建议`

### 第一阶段边界

先按规则扫描 case 元数据和断言类型，不做复杂业务链路 coverage。

---

## 6.6 能力六：Mock 辅助

### 目标

在依赖服务不稳定、未就绪、难构造异常响应时，快速得到 mock payload 和场景模板。

### 第一阶段原则

先做“mock 内容建议器”，不要直接做“完整 mock 平台”。

### 输入

- 文档片段
- 历史成功 response
- 历史失败 response
- 目标场景

### 输出建议结构

```json
{
  "scenario_name": "login_permission_denied",
  "response_template": {
    "code": 40301,
    "message": "permission denied"
  },
  "mock_rules": [
    {
      "method": "POST",
      "path": "/api/login",
      "status_code": 403
    }
  ]
}
```

### 产品交互

在 Case 或接口详情中增加：

- `AI 生成 Mock`
- `导出 JSON 模板`

### 第二阶段方向

如果后续平台要内建 mock，可以继续扩展：

- mock rule 管理
- scenario 切换
- suite 级 mock profile

### 第一阶段边界

不内建拦截器，不做复杂 mock 生命周期管理。

---

## 6.7 能力七：报告总结

### 目标

把当前报告从“原始结果展示”升级为“可读结论输出”。

### 输入

- `Execution.summary_json`
- `Execution.items`
- `Report.metadata_json`
- 最近一次同 suite 执行结果

### 输出建议结构

```json
{
  "executive_summary": "本次执行共 24 条，失败 3 条，主要集中在鉴权和超时问题。",
  "risk_summary": "存在登录链路回归风险，但有 2 条失败更像环境波动。",
  "top_failures": [],
  "recommended_actions": []
}
```

### 产品交互

在 `ReportsPage` 中增加：

- `AI 总结`
- `重新生成总结`
- `复制业务摘要`

### 落库建议

可将总结保存到：

- `report.metadata_json.ai_summary`

### 第一阶段边界

只生成摘要，不参与报告评分，不修改原始报告文件。

---

## 7. 统一数据模型建议

## 7.1 新增 ai_artifacts 表

建议新增统一 AI 工件表：

```text
ai_artifacts
  - id
  - capability
  - target_type
  - target_id
  - project_id
  - suite_id
  - case_id
  - execution_id
  - report_id
  - input_json
  - output_json
  - warnings_json
  - status
  - provider
  - model
  - created_by_user_id
  - created_at
  - updated_at
```

## 7.2 target_type 建议

- `project`
- `suite`
- `case`
- `execution`
- `report`

## 7.3 capability 建议

- `test_point`
- `assertion`
- `diagnosis`
- `test_data`
- `coverage`
- `mock`
- `report_summary`

## 7.4 status 建议

- `draft`
- `accepted`
- `rejected`
- `applied`
- `superseded`

## 7.5 历史保留策略

建议：

- AI 结果默认保留
- 新一轮生成不覆盖旧 artifact
- 如果新的 artifact 替代旧结果，则旧结果标记 `superseded`

---

## 8. API 设计建议

## 8.1 路由前缀建议

建议统一新增：

- `/api/v1/ai-copilot/...`

而不是继续把所有能力都堆进 `ai-case-drafts`。

## 8.2 第一批建议接口

### 测试点生成

- `POST /api/v1/ai-copilot/test-points/preview`
- `POST /api/v1/ai-copilot/test-points/generate-drafts`

### 智能补断言

- `POST /api/v1/ai-copilot/assertions/preview`
- `POST /api/v1/ai-copilot/assertions/{artifact_id}/apply`

### 失败诊断

- `POST /api/v1/ai-copilot/diagnosis/preview`
- `GET /api/v1/ai-copilot/diagnosis/history`

### 测试数据生成

- `POST /api/v1/ai-copilot/test-data/preview`
- `POST /api/v1/ai-copilot/test-data/{artifact_id}/apply`

### 覆盖率分析

- `POST /api/v1/ai-copilot/coverage/scan`

### Mock 辅助

- `POST /api/v1/ai-copilot/mock/preview`

### 报告总结

- `POST /api/v1/ai-copilot/report-summary/preview`
- `POST /api/v1/ai-copilot/report-summary/{artifact_id}/apply`

## 8.3 统一返回规范

所有 preview 型接口建议统一返回：

```json
{
  "artifact_id": "uuid",
  "capability": "assertion",
  "status": "draft",
  "warnings": [],
  "result": {}
}
```

---

## 9. 前端集成建议

## 9.1 页面入口建议

### Workspace 侧

- 测试点生成
- AI case draft 生成
- 覆盖率扫描入口

### Case 编辑侧

- 智能补断言
- 测试数据生成
- Mock 辅助

### Execution 侧

- 失败诊断

### Report 侧

- 报告总结

## 9.2 统一组件建议

建议新增统一组件目录：

- `frontend/src/components/ai-copilot/`

建议拆分：

- `AiCapabilityActionCard.tsx`
- `AiSuggestionPanel.tsx`
- `AiArtifactHistoryDrawer.tsx`
- `AiDiffPreview.tsx`
- `AiWarningList.tsx`

## 9.3 前端交互原则

- 所有 AI 结果默认先 preview
- 应用动作必须显式确认
- 历史建议可回看
- 失败要能清晰展示是 AI 调用失败还是 schema 校验失败

---

## 10. 分阶段实施计划

## 10.1 Phase 1：最快见效阶段

### 目标

快速让 AI 进入“执行后分析”和“case 质量提升”环节。

### 范围

1. 失败诊断
2. 报告总结
3. 智能补断言

### 为什么先做这三项

- 直接复用现有 execution / report / case 数据
- 对现有产品改动最小
- 用户收益最直观
- 不依赖复杂新模型

### Phase 1 交付物

- `ai_artifacts` 基础表
- AI Copilot 基础 service 抽象
- 执行诊断接口与页面入口
- 报告总结接口与页面入口
- 补断言接口与 case 编辑应用器

### Phase 1 验收标准

- 用户能在 execution 详情看到 AI 诊断
- 用户能在 report 页面查看 AI 摘要
- 用户能对某个 case 获取断言建议并应用
- 所有结果都能在 artifact store 中追踪

## 10.2 Phase 2：测试设计闭环阶段

### 目标

把“AI 生成 case”升级为“AI 辅助测试设计”。

### 范围

4. 测试点生成
5. 覆盖率缺口分析

### Phase 2 交付物

- 测试点 preview 能力
- 基于测试点生成 case draft
- 覆盖率规则引擎初版
- 缺口扫描页面与结果面板

### Phase 2 验收标准

- 用户能先选测试点再生成 case draft
- 用户能看到 suite / project 的 coverage 缺口
- 覆盖率结果能转成测试点建议

## 10.3 Phase 3：执行前准备增强阶段

### 目标

减少人工造数与依赖阻塞。

### 范围

6. 测试数据生成
7. Mock 辅助

### Phase 3 交付物

- 请求级数据变体生成
- 数据建议存储结构
- mock 响应模板生成
- mock 场景导出能力

### Phase 3 验收标准

- 用户能为某个 case 快速生成边界数据
- 用户能为某个接口快速生成 mock 响应模板
- AI 生成的数据与 mock 均可追溯和复用

---

## 11. 分阶段实施顺序建议

建议严格按以下顺序推进：

1. 先抽统一 AI Copilot 基础层
2. 再做 Phase 1 三个高收益能力
3. 再做 Phase 2 测试设计闭环
4. 最后做 Phase 3 执行前准备增强

不建议的做法：

- 先做 mock 平台
- 先做复杂多轮 agent 编排
- 每个页面自己接一个 AI API

---

## 12. 工程约束与执行铁律

## 12.1 必须遵守的工程约束

### 约束 1：AI 不能直接修改核心业务对象

所有写回：

- case
- report metadata
- mock rule
- dataset

都必须由确定性 apply 逻辑完成。

### 约束 2：新能力必须复用统一 artifact 体系

不能出现：

- 诊断结果存文件
- 断言建议存数据库
- 报告总结只存在前端内存

这种分裂实现。

### 约束 3：所有 capability 都要有 schema

不能接受：

- 返回自由文本后前端自己解析
- 依赖 prompt 约定但没有 Pydantic 校验

### 约束 4：AI 上下文必须可裁剪

必须考虑：

- token budget
- 长报告截断
- 多 execution 样本采样

### 约束 5：敏感信息必须脱敏

例如：

- token
- password
- cookie
- 身份信息

传给 AI 前必须脱敏或剔除。

## 12.2 产品约束

- 不做“AI 自动导入不用确认”
- 不做“AI 自动判定通过失败”
- 不做“AI 自动改 case 不留痕”

## 12.3 演进约束

后续如果要扩展更多能力，也必须先回答：

- 它属于哪种 capability
- target_type 是什么
- 上下文从哪里来
- 输出结果的 schema 是什么
- 最终 apply 到哪里

---

## 13. 风险与反模式

## 13.1 风险一：把 AI 当规则引擎

后果：

- 输出不稳定
- case 通过失败无法审计
- 回归结果难以信任

## 13.2 风险二：能力分散落地

后果：

- prompt 分裂
- 数据结构分裂
- 历史记录分裂

## 13.3 风险三：一次性做太多

后果：

- 上下文过长
- 设计失焦
- 每个功能都半成品

## 13.4 风险四：没有人工确认

后果：

- 大量低质量断言进入系统
- 测试数据污染
- mock 结果失真

---

## 14. 后续接续方式

这份文档的用途之一，是作为后续多轮实现时的“长期记忆锚点”。

后续推进建议严格按照以下方式进行：

### Step 1

每次开始新阶段时，先明确：

- 当前要做哪个 Phase
- 只做哪些 capability
- 本轮不做哪些内容

### Step 2

在实施前，先基于本文档输出一份该阶段的 Implementation Plan。

### Step 3

实施完成后，回写本文档：

- 已完成什么
- 具体偏差是什么
- 哪些设计被调整
- 下一阶段前置条件是否满足

### Step 4

如果后续某轮对话上下文变长，只要重新读取本文档，即可快速恢复：

- 架构决策
- 阶段边界
- 关键对象
- 执行顺序

---

## 15. 当前推荐的下一步

当前已经确定选择方案 B，因此推荐下一步是：

1. 先按本文档进入 `Phase 1`
2. 先设计统一 `ai_artifacts` 与 AI Copilot service 抽象
3. 以“失败诊断”作为第一个实现能力

原因：

- 它最容易复用现有 execution 数据
- 用户收益直接
- 能验证统一 AI Copilot 层是否成立

---

## 16. 当前范围内不做的事

为了避免范围失控，当前路线图明确不包含：

- 自动回归集推荐
- git diff 变更影响分析
- flaky case 自动识别
- 复杂多 agent 协作编排
- AI 自动修复测试脚本
- AI 直接驱动执行器

这些方向未来可以继续做，但不在当前 7 项能力的阶段范围内。

---

## 17. 一句话总结

`Eazy Test` 的下一步，不是继续把 AI 塞进“生成更多用例”，而是把 AI 建成一层统一的 `AI Copilot`，系统性提升：

- 测什么
- 断什么
- 为什么挂
- 还缺什么
- 怎么更快看懂结果

后续所有阶段实现，都应以本文档为准。
