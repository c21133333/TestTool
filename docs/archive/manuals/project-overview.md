# Eazy Test Web 项目介绍手册

## 1. 项目是什么

Eazy Test Web 是一个面向团队协作的 API 测试平台，当前版本的核心目标不是“从零造一个新工具”，而是把历史桌面端能力迁移成一个可多人使用的 Web-first 系统。

它已经覆盖当前主链路：

- 用户登录与基础角色权限
- 项目、套件、用例、环境管理
- 单用例执行
- 套件排队执行
- HTML / JSON 报告生成与在线查看
- Excel 导入
- 桌面端 `project.json` 和历史资产迁移
- 审计日志与用户管理

简化理解：

- 如果从产品阶段看，它更接近 `MVP+ / Beta`
- 如果从工程演进看，它是“桌面端退役中的 Web 替代核心”

## 2. 项目解决什么问题

传统桌面测试工具的典型问题包括：

- 资产难共享
- 执行环境依赖个人机器
- 多人协作和权限治理薄弱
- 历史报告与执行记录分散

Eazy Test Web 试图解决这些问题：

- 把测试资产放进统一的数据模型
- 让执行过程通过服务端和 worker 编排
- 通过浏览器而不是桌面壳承载主要操作
- 让用户、权限、报告、审计具备基础平台化能力

## 3. 当前产品能力

### 3.1 工作区能力

- Project CRUD
- Suite CRUD
- Case CRUD
- Environment CRUD
- 用例结构化编辑：headers、body、assertions、processors、metadata

### 3.2 执行能力

- 单用例即时执行
- 套件排队执行
- 执行记录分页、搜索、筛选
- 轮询刷新执行状态
- 失败过滤
- 取消 / 重试
- 查看逐项执行详情

### 3.3 报告能力

- 生成 JSON 报告
- 生成 HTML 报告
- 在线预览报告
- 新标签页打开报告

### 3.4 治理能力

- 登录 / 登出
- Token 鉴权
- 基础 RBAC
- 审计日志
- 用户管理

### 3.5 迁移能力

- Excel 导入
- 桌面端 `project.json` 导入
- 历史执行与报告数据迁移

## 4. 技术栈

### 4.1 后端

后端基于 Python 技术栈，核心组件如下：

| 类别 | 技术 |
| --- | --- |
| Web Framework | FastAPI |
| ORM | SQLAlchemy 2 |
| Schema / Settings | Pydantic v2 / pydantic-settings |
| Migration | Alembic |
| Server | Uvicorn |
| Database Driver | psycopg |
| Default Dev DB | SQLite |
| Recommended Prod DB | PostgreSQL |

后端职责：

- 提供 REST API
- 管理认证与权限
- 维护测试资产数据
- 编排执行与报告
- 在启动阶段完成数据库 bootstrap 和可选的 bootstrap admin 创建

### 4.2 前端

前端是一个 React 单页应用，核心技术如下：

| 类别 | 技术 |
| --- | --- |
| UI Framework | React 19 |
| Language | TypeScript |
| Build Tool | Vite |
| Router | react-router-dom |
| UI Library | Ant Design 5 |

前端职责：

- 提供登录界面和主导航壳
- 承载工作台、环境、执行记录、报告、审计、用户管理页面
- 对不同角色做页面级权限控制

### 4.3 共享执行内核

这个项目没有重写整个执行引擎，而是复用了历史内核，这是当前架构最关键的“熵减点”之一。

共享执行能力主要来自 `src/requesttool`：

- HTTP 请求执行
- Processor 执行
- 断言处理
- 报告生成

相关依赖包括：

- `requests`
- `jsonpath-ng`
- `openpyxl`
- Node.js（供脚本型 Processor 使用）

## 5. 架构概览

整体结构可以概括为：

```text
React + Vite frontend
        |
        v
FastAPI API layer
        |
        v
Service layer
        |
        +--> SQLAlchemy models / repositories / database
        |
        +--> testing runtime adapter
                    |
                    v
              src/requesttool
```

分层说明：

- `frontend`：浏览器端 UI 和 API 调用
- `backend/app/api`：路由、依赖注入、认证入口
- `backend/app/services`：业务编排层
- `backend/app/repositories`：数据库访问
- `backend/app/models`：数据模型
- `backend/app/testing`：对共享执行内核的适配层
- `src/requesttool`：历史可复用执行引擎

## 6. 目录结构

项目目录的重点部分如下：

```text
TestTool/
├─ backend/                  # FastAPI backend
│  └─ app/
│     ├─ api/                # 路由与认证依赖
│     ├─ core/               # 配置、数据库、安全
│     ├─ models/             # SQLAlchemy 模型
│     ├─ repositories/       # 数据访问层
│     ├─ schemas/            # Pydantic schema
│     ├─ services/           # 业务服务
│     └─ testing/            # 执行内核适配层
├─ frontend/                 # React 管理台
├─ src/requesttool/          # 共享执行内核与 CLI
├─ alembic/                  # 数据库迁移
├─ tests/                    # pytest 测试
├─ docs/archive/             # 设计与路线图归档
├─ docs/manuals/             # 使用手册
├─ web_runs/                 # 报告输出目录
└─ web_eazytest.db           # 默认 SQLite 数据库
```

## 7. 核心模块说明

### 7.1 API 路由

当前 API 主要分为以下几组：

- `/health`
- `/auth`
- `/audit-logs`
- `/users`
- `/projects`
- `/suites`
- `/cases`
- `/environments`
- `/executions`
- `/reports`
- `/imports`

这说明系统已经从“只有执行”演进到“执行 + 资产管理 + 治理”。

### 7.2 CLI 入口

项目同时提供 CLI，用于本地开发和部署运行：

```powershell
python -m requesttool serve
python -m requesttool worker
python -m requesttool migrate
```

含义如下：

- `serve`：启动 Web 服务
- `worker`：处理套件执行队列
- `migrate`：执行 Alembic 迁移

### 7.3 Worker 机制

套件执行不是直接在页面请求里跑完，而是由独立 worker 消费待执行任务。好处是：

- 避免长任务阻塞 Web 请求
- 更适合后续扩展并发和重试策略
- 为执行链路产品化打下基础

### 7.4 前端页面结构

当前前端主要页面包括：

- Dashboard
- Workspace
- Environments
- Executions
- Reports
- Audit Logs
- Users

页面权限由角色控制：

- `admin`：全部页面
- `tester`：业务操作页
- `developer`：只读协作页

## 8. 数据与运行方式

### 8.1 默认运行数据

默认情况下：

- 数据库存储在 `web_eazytest.db`
- 报告输出到 `web_runs/`
- API 前缀为 `/api/v1`

这意味着当前仓库默认适合本地开发和演示验证。

### 8.2 环境变量

系统通过 `EAZYTEST_` 前缀读取环境变量，核心配置包括：

- `EAZYTEST_DATABASE_URL`
- `EAZYTEST_DATABASE_AUTO_MIGRATE`
- `EAZYTEST_APP_NAME`
- `EAZYTEST_API_PREFIX`
- `EAZYTEST_AUTH_TOKEN_TTL_HOURS`
- `EAZYTEST_USER_PASSWORD_MIN_LENGTH`
- `EAZYTEST_BOOTSTRAP_ADMIN_ENABLED`
- `EAZYTEST_BOOTSTRAP_ADMIN_USERNAME`
- `EAZYTEST_BOOTSTRAP_ADMIN_PASSWORD`
- `EAZYTEST_REPORT_DIR`
- `EAZYTEST_REPORT_TEMPLATE_PATH`
- `EAZYTEST_WORKER_POLL_INTERVAL_SECONDS`

Processor 相关还涉及：

- `REQUESTTOOL_NODE_BIN`

### 8.3 启动方式

本地最小启动流程：

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .[dev]
```

```powershell
Set-Location frontend
npm install
Set-Location ..
```

```powershell
python -m requesttool migrate
python -m requesttool serve --reload
```

如果需要套件执行，再启动一个 worker：

```powershell
python -m requesttool worker
```

如果需要让后端托管前端产物，再构建前端：

```powershell
Set-Location frontend
npm run build
Set-Location ..
python -m requesttool serve
```

## 9. 权限模型

当前权限模型是基础 RBAC：

| 角色 | 说明 |
| --- | --- |
| `admin` | 系统管理员，具备平台治理能力 |
| `tester` | 资产维护与执行角色 |
| `developer` | 只读协作角色 |

权限边界大致为：

- `admin`：可以管理用户和审计
- `tester`：不能管理用户，但可以维护测试资产和执行
- `developer`：可以查看，但不能做写操作

## 10. 当前版本边界与现实判断

这部分最重要。这个项目现在“能跑”，但还没有完全进入“生产级交付”。

当前边界主要有：

- 默认数据库仍是 SQLite，本质更偏开发环境
- 历史迁移能力仍存在，说明系统还处于过渡期
- 执行链路已有独立 worker，但更强的超时、恢复、可观测性仍有继续完善空间
- 文档和部署规范已经开始成型，但离完整生产工程化还有距离

换句话说，当前项目最核心的工程主题不是继续堆功能，而是把已有主链路收口为可交付、可维护、可发布的系统。

## 11. 适合谁看

这份介绍手册适合：

- 新加入项目的研发或测试成员
- 需要快速了解系统边界的架构师
- 需要做迁移评估或接手维护的同学
- 需要对外介绍项目的负责人

## 12. 延伸阅读

- 功能使用手册：`docs/manuals/user-guide.md`
- Web 迁移设计：`docs/archive/plans/2026-03-23-web-migration-design.md`
- V1 路线图：`docs/archive/plans/2026-03-23-v1-roadmap.md`
