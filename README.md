# Eazy Test Web

Eazy Test Web 是一个面向团队协作的 API 测试平台，当前版本的核心目标是将历史桌面端能力迁移到 Web 体系，同时保留原有请求执行、断言、Processor 和报告生成能力。

它现在已经不是单纯的 Demo，而是一个可运行的 Web-first 测试工作台，覆盖了：

- 登录认证与角色权限
- Project / Suite / Case / Environment 管理
- 单用例即时执行
- Suite 排队执行与独立 worker 消费
- HTML / JSON 报告生成与在线查看
- 审计日志
- Excel 导入
- 旧桌面 `project.json` 与历史运行报告导入

## 当前状态

当前仓库处于“桌面端退役中的 Web 迁移版本”：

- Web 主链路已经打通
- 历史执行引擎仍复用 `src/requesttool`
- 旧桌面 UI、安装链路和样例资产已经大部分移除
- 历史导入能力仍保留，用于平滑迁移旧数据

如果你把它理解为产品阶段，更接近 `MVP+ / Beta`，还不是最终意义上的 `v1.0`

## 技术栈

### Backend

- Python 3.9+
- FastAPI
- SQLAlchemy
- Alembic
- Pydantic v2
- Uvicorn
- SQLite（默认开发环境）
- PostgreSQL（推荐生产环境）

### Frontend

- React 19
- TypeScript
- Vite
- Ant Design 5

### Shared Runtime

- `requests` 执行 HTTP 请求
- `jsonpath-ng` 做 JSONPath 断言
- `openpyxl` 导入 Excel
- Node.js 用于脚本型 Processor 运行

## 架构概览

```text
frontend (React + Vite)
        |
        v
backend/app/api (FastAPI routes)
        |
        v
backend/app/services
        |
        +--> backend/app/models + repositories + SQLite
        |
        +--> backend/app/testing/runtime
                    |
                    v
             src/requesttool
             - http_client
             - processor_engine
             - shared.assertions
             - shared.reporting
```

## 目录结构

```text
TestTool/
├─ backend/                # FastAPI backend
│  └─ app/
│     ├─ api/              # 路由与鉴权依赖
│     ├─ core/             # 配置、数据库、安全
│     ├─ models/           # SQLAlchemy 模型
│     ├─ repositories/     # 数据访问层
│     ├─ services/         # 业务编排
│     └─ testing/          # 复用旧执行引擎的适配层
├─ frontend/               # React 管理台
├─ src/requesttool/        # 共享执行内核与 CLI
├─ tests/                  # pytest 测试
├─ docs/plans/             # 迁移设计与退役计划
├─ web_runs/               # 运行时报告输出目录
└─ web_eazytest.db         # 默认 SQLite 数据库文件
```

## 角色模型

当前内置三种角色：

- `admin`: 用户管理、审计、工作区管理、执行管理
- `tester`: 工作区管理、导入、执行
- `developer`: 只读查看为主，不能做受限写操作

## 默认运行数据

默认开发数据库为 SQLite，库文件位于仓库根目录：

- `web_eazytest.db`

默认报告输出目录：

- `web_runs/`

bootstrap admin 默认关闭。

- 如需本地初始化管理员，必须显式设置 `EAZYTEST_BOOTSTRAP_ADMIN_ENABLED=true`
- 同时必须显式提供 `EAZYTEST_BOOTSTRAP_ADMIN_USERNAME` 和强密码 `EAZYTEST_BOOTSTRAP_ADMIN_PASSWORD`
- `production` 环境禁止启用 bootstrap admin

## 快速开始

### 1. 安装 Python 依赖

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .[dev]
```

### 2. 安装前端依赖

```powershell
Set-Location frontend
npm install
Set-Location ..
```

### 3. 启动后端

```powershell
python -m requesttool serve --reload
```

默认监听：

- `http://127.0.0.1:8000`

Swagger 文档：

- `http://127.0.0.1:8000/docs`

### 4. 启动 worker

```powershell
python -m requesttool worker
```

这个进程负责消费 `suite` 类型的排队执行任务。

### 4.1 手动执行数据库迁移

```powershell
python -m requesttool migrate
```

如果你提供的是常见的 PostgreSQL 连接串，例如 `postgres://` 或 `postgresql://`，系统会自动归一化到 `psycopg` 驱动。

### 5. 启动前端开发服务器

```powershell
Set-Location frontend
npm run dev
```

### 6. 生产式联调方式

如果先执行前端打包：

```powershell
Set-Location frontend
npm run build
Set-Location ..
python -m requesttool serve
```

后端会自动托管 `frontend/dist`，根路径直接返回前端页面。

## 常用命令

### 启动 Web 服务

```powershell
python -m requesttool serve --host 0.0.0.0 --port 8000 --reload
```

### 启动 worker

```powershell
python -m requesttool worker
```

### 执行数据库迁移

```powershell
python -m requesttool migrate --revision head
```

### 仅处理一条待执行任务

```powershell
python -m requesttool worker --once
```

### 运行测试

```powershell
python -m pytest
```

当前仓库测试状态：

- `33 passed`

## 配置项

后端使用 `EAZYTEST_` 前缀读取环境变量，支持 `.env` 文件。

常用配置：

- `EAZYTEST_DEPLOYMENT_ENV`
- `EAZYTEST_DATABASE_URL`
- `EAZYTEST_DATABASE_AUTO_MIGRATE`
- `EAZYTEST_APP_NAME`
- `EAZYTEST_APP_VERSION`
- `EAZYTEST_API_PREFIX`
- `EAZYTEST_LOG_LEVEL`
- `EAZYTEST_AUTH_TOKEN_TTL_HOURS`
- `EAZYTEST_AUTH_MAX_ACTIVE_TOKENS_PER_USER`
- `EAZYTEST_USER_PASSWORD_MIN_LENGTH`
- `EAZYTEST_BOOTSTRAP_ADMIN_ENABLED`
- `EAZYTEST_BOOTSTRAP_ADMIN_USERNAME`
- `EAZYTEST_BOOTSTRAP_ADMIN_PASSWORD`
- `EAZYTEST_REPORT_DIR`
- `EAZYTEST_REPORT_TEMPLATE_PATH`
- `EAZYTEST_WORKER_POLL_INTERVAL_SECONDS`
- `EAZYTEST_SCHEDULER_POLL_INTERVAL_SECONDS`
- `EAZYTEST_SCHEDULER_BATCH_SIZE`

脚本型 Processor 依赖 Node.js：

- 默认从系统 `PATH` 中查找 `node`
- 如果本机未配置，可显式设置 `REQUESTTOOL_NODE_BIN=/absolute/path/to/node`

## 当前已完成能力

### Workspace

- Project CRUD
- Suite CRUD
- Case CRUD
- Environment CRUD
- 结构化编辑 headers、body、assertions、processors、metadata

### Execution

- Case 即时执行
- Suite 排队执行
- 轮询查看执行状态
- 失败筛选
- Cancel / Retry

### Report

- JSON 报告生成
- HTML 报告生成
- 在线拉取报告内容

### Governance

- 登录 / 登出
- Token 鉴权
- 角色权限控制
- 审计日志

### Migration

- Excel 导入
- 桌面端 `project.json` 导入
- 桌面端历史 `runsIndex` / html / json 报告导入

## 已知边界

这个版本的重点是“迁移可用”而不是“最终产品化”，所以有一些明确边界：

- 默认开发环境仍使用 SQLite，生产环境应切到 PostgreSQL
- 仍保留桌面时代的导入兼容逻辑
- 历史导入能力是迁移桥，不是最终主数据模型
- bootstrap admin 仅适合本地显式初始化，不适合共享或生产环境
- 运行产物 `web_eazytest.db` 和 `web_runs/` 应视为本地运行数据，不应作为产品源码的一部分管理

## 文档

迁移设计与退役计划见：

- `docs/plans/2026-03-23-web-migration-design.md`
- `docs/plans/2026-03-23-desktop-decommission-plan.md`

## Security Baseline

## AI Copilot Phase 4

- `WorkspacePage` 的用例编辑区现在包含 `AI 预执行准备` 卡片，可直接选择已保存的 `AI 测试数据变体` 与 `AI Mock 模板`，然后触发单次 case execution。
- execution preparation 只会把显式选中的 artifact 注入本次执行请求，不会静默改写 `api_cases.metadata_json` 或当前编辑中的请求体。
- 执行完成后，可在 execution 的 `summary_json.ai_preparation` 中查看本次命中的 variant/template 数量、选择摘要，以及最终的 deterministic preparation 结果。
- `AI 测试数据` 与 `AI Mock` 历史抽屉现在支持 `Lineage` 入口，可回看 artifact 到派生对象/历史记录之间的 bridge 关系。
- 所有 LLM-backed artifact 现在统一记录 provider/runtime trace；deterministic capability 也会显式记录 `call_mode=deterministic`，便于审计与观测。

### 推荐使用方式

1. 先在用例编辑区生成并应用 `AI 测试数据` 或 `AI Mock`，把需要复用的 artifact 保存进 case metadata。
2. 在同一页面的 `AI 预执行准备` 卡片中选择本次执行要携带的 variant/template，必要时再选择 environment。
3. 触发执行后，去执行记录查看 `summary_json.ai_preparation`，确认本次到底带入了哪些准备项。
4. 如果需要追踪来源，打开对应 artifact 的历史抽屉并点击 `Lineage`，即可查看 artifact lineage bridge 与相关派生节点。

- Bootstrap admin is disabled by default and requires explicit credentials when enabled for local development.
- `EAZYTEST_DEPLOYMENT_ENV=production` rejects `EAZYTEST_BOOTSTRAP_ADMIN_ENABLED=true`.
- Access tokens use a fixed TTL from `EAZYTEST_AUTH_TOKEN_TTL_HOURS` and a per-user live-token cap from `EAZYTEST_AUTH_MAX_ACTIVE_TOKENS_PER_USER`.
- Only `admin` can manage users or change account active state. `developer` remains read-only for execution write operations.
- See `docs/security/permissions-matrix.md` for the current permission matrix and account-state rules.

## Configuration Governance

- `development`: can use SQLite and `EAZYTEST_DATABASE_AUTO_MIGRATE=true`.
- `test`: should use isolated config and avoid sharing long-lived data with development.
- `production`: must use PostgreSQL (or equivalent) and `EAZYTEST_DATABASE_AUTO_MIGRATE=false`.
- API and worker now fail fast on dangerous runtime defaults such as SQLite in production, auto-migrate in production, or missing report template paths.
- See `docs/manuals/environment-governance.md` for the full environment matrix and rollout guidance.

## Deployment Topology

- The standard topology is `nginx + api + worker + scheduler + postgresql`.
- The backend image builds `frontend/dist` and serves it directly, so the minimal production deployment does not need a separate frontend runtime.
- Use [deployment-topology.md](D:/works/project/ezTest/TestTool/docs/manuals/deployment-topology.md) together with `deploy/docker-compose.single-host.yml` for the single-host baseline.

## Execution Reliability

- Suite executions now recover stale `running` tasks before worker consumption continues.
- Transient request failures (`timeout`, `request_error`) support bounded automatic retry via `EAZYTEST_EXECUTION_RETRY_LIMIT`.
- Execution summaries now include `failure_breakdown`, `first_failure`, and retry metadata for faster diagnosis.
- See [execution-reliability.md](D:/works/project/ezTest/TestTool/docs/manuals/execution-reliability.md) for the current reliability rules and boundaries.

## Observability

- API and worker now emit structured JSON logs with a shared event format.
- HTTP responses include `X-Request-ID`, and the same request id is written into request logs for traceability.
- `GET /api/v1/health` now exposes dependency status plus a minimal execution metrics snapshot.
- See [observability.md](D:/works/project/ezTest/TestTool/docs/manuals/observability.md) for the current logging and health-check baseline.

## API Contract

- JSON success responses use a consistent `success / message / data` envelope.
- JSON errors now use a standard `success=false + error{code,status,details,request_id}` envelope instead of relying on ad hoc `detail`.
- Main list endpoints now share a paginated `items / total / page / page_size` shape.
- See [api-contract.md](D:/works/project/ezTest/TestTool/docs/manuals/api-contract.md) for the current API contract and error model.

## Legacy Compatibility Retirement

- Legacy imports are now explicitly treated as a migration bridge instead of a long-term product surface.
- `GET /api/v1/imports/policy` exposes the current compatibility policy, capability inventory, and planned retirement path.
- `EAZYTEST_LEGACY_IMPORTS_ENABLED=false` disables migration imports at runtime, and disabled routes return `410 Gone`.
- `EAZYTEST_LEGACY_IMPORTS_SUNSET_DATE` can be used to publish a retirement date before the final removal phase.
- See [legacy-compatibility-retirement.md](D:/works/project/ezTest/TestTool/docs/manuals/legacy-compatibility-retirement.md) for the full exit strategy.

## CI/CD Governance

- `.github/workflows/ci.yml` now runs three minimum gates: backend tests, frontend build, and API/worker startup smoke.
- `scripts/ci_smoke.py` validates that the API can start and answer `/api/v1/health`, and that the worker can complete a `run_once()` bootstrap path.
- `.github/release-template.md` is the release-note template for each `v1.x.y` delivery.
- See [release-governance.md](D:/works/project/ezTest/TestTool/docs/manuals/release-governance.md) for versioning, release checklist, and rollback rules.

## 开发建议

如果你准备继续把它推进到 `v1`，建议优先处理这四类问题：

1. 生产级数据库与部署方式
2. 安全与默认配置收口
3. 迁移期兼容代码的清退策略
4. 文档、观测性和发布流程补全
## Scheduled Suite Dispatch

- Scheduled jobs bind to `suite + environment` and only create `pending suite execution` records.
- The runtime topology is now `api + worker + scheduler`.
- `api` handles CRUD, auth, and manual trigger endpoints.
- `scheduler` scans due jobs and enqueues executions.
- `worker` consumes queued suite executions and generates reports.

### Start scheduler locally

```powershell
python -m backend.scheduler
```

### Production notes

- Production should run `api`, `worker`, and `scheduler` as independent long-lived processes.
- Keep `EAZYTEST_DATABASE_AUTO_MIGRATE=false` in production and apply migrations before rollout.
- Tune dispatch with `EAZYTEST_SCHEDULER_POLL_INTERVAL_SECONDS` and `EAZYTEST_SCHEDULER_BATCH_SIZE`.
- Schedule-created executions are traceable in the execution center through `trigger_source=schedule`.

### Final validation checklist

```powershell
pytest tests/test_scheduled_jobs.py -v
pytest tests/test_web_services.py -v
Set-Location frontend
npm run build
Set-Location ..
```

### Manual smoke

- Confirm the left navigation shows the standalone `SCHEDULE` group.
- Create a scheduled job and verify `next_run_at` is computed.
- Trigger the job once and confirm a new execution is created.
- Open the execution detail page and confirm it shows the schedule source and link.
- Disable the job and confirm it no longer dispatches automatically.
