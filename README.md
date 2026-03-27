# Eazy Test Web

Eazy Test Web 是一个面向团队协作的 Web-first API 测试平台。它把项目、套件、用例、环境、执行、报告和 AI Copilot 收口到同一套 Web 工作流里，目标不是做一个新的玩具，而是替代历史桌面端，形成可共享、可追踪、可治理的测试平台。

## 适合谁

- 需要统一管理 API 测试资产的测试团队
- 需要把执行与报告从个人机器迁移到服务端的团队
- 需要把 AI 辅助能力接入测试设计、编写、排障与汇报链路的团队

## 当前能力

### 测试资产

- `Project / Suite / Case / Environment` 全量管理
- 用例结构化编辑：`Headers / Body / Assertions / Processors / Metadata`
- Excel 导入
- 历史桌面端 `project.json` 导入

### 执行与报告

- 单用例即时执行
- 套件排队执行
- 独立 worker 消费执行队列
- HTML / JSON 报告生成与在线查看
- 失败筛选、取消、重试、执行详情追踪

### 调度与治理

- 定时任务管理（`suite + environment` 维度）
- 登录认证与基础 RBAC
- 审计日志
- 用户管理

### AI Copilot

- 覆盖率扫描
- 测试点生成
- 用例草稿生成与导入
- 断言建议
- AI 测试数据
- AI Mock 模板
- AI 预执行准备
- 执行失败诊断
- 报告 AI 总结
- AI Chat 历史与上下文能力

## 项目状态

当前仓库更接近 `MVP+ / Beta`，不是完全产品化的 `v1.0`。

它已经具备真实可用的主链路，但仍然保留了明显的迁移期特征：

- 共享执行内核仍复用历史 `src/requesttool`
- 默认开发数据库仍是 SQLite
- 历史导入能力仍保留，用于平滑迁移
- 生产环境需要显式拆分 `api / worker / scheduler`

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
        +--> backend/app/models + repositories + database
        |
        +--> backend/app/testing
                    |
                    v
             src/requesttool
```

## 技术栈

### Backend

- Python 3.9+
- FastAPI
- SQLAlchemy 2
- Alembic
- Pydantic v2
- Uvicorn
- SQLite（默认开发）
- PostgreSQL（推荐生产）

### Frontend

- React 19
- TypeScript
- Vite
- Ant Design 5

### Shared Runtime

- `requests`
- `jsonpath-ng`
- `openpyxl`
- Node.js（供脚本型 Processor 使用）

## 快速启动

### 1. 安装后端依赖

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

### 3. 初始化数据库

```powershell
python -m requesttool migrate
```

### 4. 启动 API

```powershell
python -m requesttool serve --reload
```

默认地址：

- Web: `http://127.0.0.1:8000/`
- Swagger: `http://127.0.0.1:8000/docs`

### 5. 启动 worker

套件执行依赖独立 worker：

```powershell
python -m requesttool worker
```

### 6. 启动 scheduler

定时任务依赖独立 scheduler：

```powershell
python -m backend.scheduler
```

### 7. 前端单独开发模式

如果需要单独跑前端热更新：

```powershell
Set-Location frontend
npm run dev
```

### 8. 后端托管前端产物

```powershell
Set-Location frontend
npm run build
Set-Location ..
python -m requesttool serve
```

## 常用命令

```powershell
python -m requesttool serve --host 0.0.0.0 --port 8000 --reload
python -m requesttool worker
python -m requesttool worker --once
python -m requesttool migrate --revision head
python -m backend.scheduler
python -m pytest
```

## 关键配置

系统使用 `EAZYTEST_` 前缀读取环境变量，并支持仓库根目录 `.env`。

常用项：

- `EAZYTEST_DEPLOYMENT_ENV`
- `EAZYTEST_DATABASE_URL`
- `EAZYTEST_DATABASE_AUTO_MIGRATE`
- `EAZYTEST_REPORT_DIR`
- `EAZYTEST_REPORT_TEMPLATE_PATH`
- `EAZYTEST_EXECUTION_REQUEST_TIMEOUT_SECONDS`
- `EAZYTEST_EXECUTION_RETRY_LIMIT`
- `EAZYTEST_EXECUTION_STALE_TIMEOUT_SECONDS`
- `EAZYTEST_WORKER_POLL_INTERVAL_SECONDS`
- `EAZYTEST_SCHEDULER_POLL_INTERVAL_SECONDS`
- `EAZYTEST_SCHEDULER_BATCH_SIZE`
- `EAZYTEST_BOOTSTRAP_ADMIN_ENABLED`
- `EAZYTEST_BOOTSTRAP_ADMIN_USERNAME`
- `EAZYTEST_BOOTSTRAP_ADMIN_PASSWORD`

AI 相关配置通过 `DATATEST_AI_*` 和 `OPENAI_API_KEY` 注入。

如果用例使用脚本型 Processor，可以显式指定：

```env
REQUESTTOOL_NODE_BIN=/absolute/path/to/node
```

## 目录结构

```text
TestTool/
├─ backend/                  # FastAPI backend
├─ frontend/                 # React 管理台
├─ src/requesttool/          # 共享执行内核与 CLI
├─ alembic/                  # 数据库迁移
├─ deploy/                   # 部署基线
├─ docs/manuals/             # 使用与专题手册
├─ docs/security/            # 安全与权限文档
├─ docs/archive/             # 历史计划与归档手册
├─ tests/                    # pytest 测试
├─ web_runs/                 # 报告输出目录
└─ web_eazytest.db           # 默认 SQLite 数据库
```

## 使用入口

建议按这个顺序阅读：

1. [用户使用手册](./docs/manuals/user-guide.md)
2. [项目介绍手册（归档）](./docs/archive/manuals/project-overview.md)
3. [配置与环境治理](./docs/manuals/environment-governance.md)
4. [执行链路可靠性](./docs/manuals/execution-reliability.md)
5. [部署拓扑](./docs/manuals/deployment-topology.md)
6. [权限矩阵](./docs/security/permissions-matrix.md)

历史迁移设计、阶段性实施计划和路线图已移动到 `docs/archive/`，避免与当前主文档混读。

## 已知边界

- 默认开发环境使用 SQLite，生产环境必须切换到 PostgreSQL 或同等级数据库
- `bootstrap admin` 默认关闭，且生产环境禁止开启
- 调度链路为 `api + worker + scheduler` 三进程模式
- `replace` 并发策略与 `fire_once` 补偿策略仍应视为谨慎使用能力
- 历史导入能力是迁移桥，不是长期产品主模型

## 验证建议

改完配置或部署方式后，至少执行下面这组最小验证：

```powershell
python -m pytest
Set-Location frontend
npm run build
Set-Location ..
```
