# Scheduled Suite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为现有 `suite execution` 链路增加“定时任务”能力，并在前端以全新的一级菜单组承载该功能。

**Architecture:** 新功能拆成三层：`scheduled_jobs / scheduled_job_runs` 持久化层、`scheduler` 触发层、现有 `execution worker` 执行层。调度器只负责到点创建 `pending suite execution`，不直接执行 case；前端新增独立 `SCHEDULE` 菜单组与 `ScheduledJobsPage` 页面，避免和手工执行中心混淆。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, React 19, TypeScript, Ant Design, Pytest, Vite

---

## 实施前约束

- 只做 `suite` 级定时任务，不引入 `case_group`
- 保持现有 `ExecutionService.process_next_pending_execution()` 语义不变
- 首版只正式支持 `concurrency_policy = forbid | allow`
- 首版默认 `misfire_policy = skip`，`fire_once` 作为可选字段保留
- 前端必须放到**全新一级菜单组**，不能挂进现有 `OPS`

## 依赖决策

- cron 解析推荐引入 `croniter`
- 实施时需要同步修改：
  - `requirements.txt`
  - `pyproject.toml`
- 合并前确认该依赖版本与 Python 版本兼容；不要手写 cron 解析器

### Task 1: 建立调度数据模型与数据库迁移

**Files:**
- Create: `D:\works\project\ezTest\TestTool\alembic\versions\20260327_000007_scheduled_jobs.py`
- Create: `D:\works\project\ezTest\TestTool\backend\app\models\scheduled_job.py`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\models\execution.py`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\models\registry.py`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\models\__init__.py`
- Modify: `D:\works\project\ezTest\TestTool\tests\test_web_services.py`

**Step 1: 写失败测试，锁定 schema 结果**

在 `tests/test_web_services.py` 增加最小模型测试，断言：

```python
def test_scheduled_job_models_persist():
    session = _make_session()
    # create project, suite, environment, user
    # create scheduled job and scheduled run
    # create execution with trigger_source="schedule"
    assert stored_job.suite_id == suite.id
    assert stored_run.execution_id == execution.id
    assert stored_execution.trigger_source.value == "schedule"
```

**Step 2: 运行测试，确认当前失败**

Run:

```bash
pytest tests/test_web_services.py::test_scheduled_job_models_persist -v
```

Expected: FAIL，缺少 `ScheduledJob` / `Execution.trigger_source`

**Step 3: 最小实现模型与迁移**

- 在 `backend/app/models/scheduled_job.py` 定义：
  - `ScheduledJob`
  - `ScheduledJobRun`
  - `ScheduledJobConcurrencyPolicy`
  - `ScheduledJobMisfirePolicy`
  - `ScheduledJobRunStatus`
- 在 `backend/app/models/execution.py` 增加：
  - `ExecutionTriggerSource`
  - `trigger_source`
  - `scheduled_job_id`
  - `scheduled_run_id`
- 在 migration 中创建：
  - `scheduled_jobs`
  - `scheduled_job_runs`
  - `executions` 新字段与外键

**Step 4: 重新运行测试**

Run:

```bash
pytest tests/test_web_services.py::test_scheduled_job_models_persist -v
```

Expected: PASS

**Step 5: 提交**

```bash
git add alembic/versions/20260327_000007_scheduled_jobs.py backend/app/models/scheduled_job.py backend/app/models/execution.py backend/app/models/registry.py backend/app/models/__init__.py tests/test_web_services.py
git commit -m "feat: add scheduled job persistence models"
```

### Task 2: 实现调度领域服务与仓储

**Files:**
- Create: `D:\works\project\ezTest\TestTool\backend\app\repositories\scheduled_job_repository.py`
- Create: `D:\works\project\ezTest\TestTool\backend\app\services\scheduled_job_service.py`
- Create: `D:\works\project\ezTest\TestTool\backend\app\schemas\scheduled_job.py`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\core\config.py`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\services\workspace_service.py`
- Create: `D:\works\project\ezTest\TestTool\tests\test_scheduled_jobs.py`
- Modify: `D:\works\project\ezTest\TestTool\requirements.txt`
- Modify: `D:\works\project\ezTest\TestTool\pyproject.toml`

**Step 1: 写失败测试，锁定 CRUD 与时间计算**

在 `tests/test_scheduled_jobs.py` 先写：

```python
def test_create_scheduled_job_computes_next_run_at():
    service = ScheduledJobService(session)
    payload = ScheduledJobCreate(
        project_id=project.id,
        suite_id=suite.id,
        environment_id=environment.id,
        name="daily smoke",
        cron_expr="0 9 * * 1-5",
        timezone="Asia/Shanghai",
        enabled=True,
        concurrency_policy="forbid",
        misfire_policy="skip",
    )
    job = service.create_job(payload, actor=user)
    assert job.next_run_at is not None

def test_create_scheduled_job_rejects_cross_project_environment():
    with pytest.raises(HTTPException):
        service.create_job(payload, actor=user)
```

**Step 2: 运行测试，确认失败**

Run:

```bash
pytest tests/test_scheduled_jobs.py -v
```

Expected: FAIL，缺少仓储、schema、cron 计算逻辑

**Step 3: 最小实现**

- 新增 Pydantic schema：
  - `ScheduledJobCreate`
  - `ScheduledJobUpdate`
  - `ScheduledJobRead`
  - `ScheduledJobRunRead`
- `ScheduledJobService` 实现：
  - create
  - update
  - enable
  - disable
  - list
  - list_runs
  - `_compute_next_run_at()`
  - `validate suite/environment/project relation`
- `config.py` 增加：
  - `scheduler_poll_interval_seconds`
  - `scheduler_batch_size`

**Step 4: 跑测试直到通过**

Run:

```bash
pytest tests/test_scheduled_jobs.py -v
```

Expected: PASS

**Step 5: 提交**

```bash
git add backend/app/repositories/scheduled_job_repository.py backend/app/services/scheduled_job_service.py backend/app/schemas/scheduled_job.py backend/app/core/config.py backend/app/services/workspace_service.py tests/test_scheduled_jobs.py requirements.txt pyproject.toml
git commit -m "feat: add scheduled job service layer"
```

### Task 3: 打通 API、权限与审计

**Files:**
- Create: `D:\works\project\ezTest\TestTool\backend\app\api\routes\scheduled_jobs.py`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\api\router.py`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\services\audit_log_service.py`
- Modify: `D:\works\project\ezTest\TestTool\tests\test_web_services.py`

**Step 1: 写失败测试，锁定接口契约**

在 `tests/test_web_services.py` 增加 API 层测试，覆盖：

```python
def test_scheduled_jobs_route_create_and_list(client, admin_token):
    created = client.post("/api/v1/scheduled-jobs", json=payload, headers=admin_token)
    assert created.status_code == 200
    listed = client.get("/api/v1/scheduled-jobs", headers=admin_token)
    assert listed.json()["data"]["items"][0]["name"] == "daily smoke"

def test_scheduled_jobs_route_forbids_developer_write(client, developer_token):
    response = client.post("/api/v1/scheduled-jobs", json=payload, headers=developer_token)
    assert response.status_code in {401, 403}
```

**Step 2: 运行测试，确认失败**

Run:

```bash
pytest tests/test_web_services.py -k scheduled_jobs -v
```

Expected: FAIL，路由不存在

**Step 3: 最小实现 API**

实现这些端点：

- `GET /scheduled-jobs`
- `POST /scheduled-jobs`
- `PUT /scheduled-jobs/{job_id}`
- `POST /scheduled-jobs/{job_id}/enable`
- `POST /scheduled-jobs/{job_id}/disable`
- `POST /scheduled-jobs/{job_id}/trigger`
- `GET /scheduled-jobs/{job_id}/runs`

并补全 audit action：

- `scheduled_job.create`
- `scheduled_job.update`
- `scheduled_job.enable`
- `scheduled_job.disable`
- `scheduled_job.trigger`
- `scheduled_job.delete`

**Step 4: 重跑测试**

Run:

```bash
pytest tests/test_web_services.py -k scheduled_jobs -v
```

Expected: PASS

**Step 5: 提交**

```bash
git add backend/app/api/routes/scheduled_jobs.py backend/app/api/router.py backend/app/services/audit_log_service.py tests/test_web_services.py
git commit -m "feat: expose scheduled job management api"
```

### Task 4: 实现 scheduler 进程与 execution 触发链路

**Files:**
- Create: `D:\works\project\ezTest\TestTool\backend\app\services\schedule_dispatch_service.py`
- Create: `D:\works\project\ezTest\TestTool\backend\app\scheduler.py`
- Create: `D:\works\project\ezTest\TestTool\backend\scheduler.py`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\services\execution_service.py`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\repositories\execution_repository.py`
- Modify: `D:\works\project\ezTest\TestTool\tests\test_scheduled_jobs.py`

**Step 1: 写失败测试，锁定调度触发**

先写两个关键测试：

```python
def test_scheduler_dispatch_creates_pending_suite_execution(monkeypatch):
    dispatched = dispatch_service.dispatch_due_job(job.id, now=fixed_now)
    assert dispatched.execution_id is not None
    assert execution.status.value == "pending"
    assert execution.trigger_source.value == "schedule"

def test_scheduler_forbid_policy_skips_when_previous_execution_active():
    queued = execution_service.queue_suite_execution_from_schedule(job, run_record)
    skipped = dispatch_service.dispatch_due_job(job.id, now=fixed_now)
    assert skipped.status.value == "skipped"
```

**Step 2: 运行测试，确认失败**

Run:

```bash
pytest tests/test_scheduled_jobs.py -k "dispatch or forbid" -v
```

Expected: FAIL，缺少调度派发服务

**Step 3: 最小实现**

- `ExecutionService` 新增：
  - `queue_suite_execution_from_schedule(job, scheduled_run)`
- `ExecutionRepository` 新增：
  - 查询某个 `scheduled_job_id` 最近活跃 execution
- `ScheduleDispatchService` 实现：
  - due job dispatch
  - job/run 幂等保护
  - `forbid|allow`
  - `skip|fire_once`
- `backend/app/scheduler.py` 实现轮询入口

**Step 4: 跑测试直到通过**

Run:

```bash
pytest tests/test_scheduled_jobs.py -v
pytest tests/test_web_services.py::test_execution_worker_processes_pending_suite -v
```

Expected: PASS

**Step 5: 提交**

```bash
git add backend/app/services/schedule_dispatch_service.py backend/app/scheduler.py backend/scheduler.py backend/app/services/execution_service.py backend/app/repositories/execution_repository.py tests/test_scheduled_jobs.py
git commit -m "feat: add scheduled dispatch worker"
```

### Task 5: 新增独立菜单组与定时任务管理页面

**Files:**
- Create: `D:\works\project\ezTest\TestTool\frontend\src\pages\ScheduledJobsPage.tsx`
- Modify: `D:\works\project\ezTest\TestTool\frontend\src\App.tsx`
- Modify: `D:\works\project\ezTest\TestTool\frontend\src\components\shell\AppShell.tsx`
- Modify: `D:\works\project\ezTest\TestTool\frontend\src\api\types.ts`
- Modify: `D:\works\project\ezTest\TestTool\frontend\src\api\services.ts`
- Modify: `D:\works\project\ezTest\TestTool\frontend\src\auth\permissions.ts`

**Step 1: 先让类型失败**

在 `frontend/src/api/types.ts` 增加类型声明占位引用，并在 `App.tsx` 引入懒加载页面：

```ts
const ScheduledJobsPage = lazy(async () => ({ default: (await import('./pages/ScheduledJobsPage')).ScheduledJobsPage }));
```

此时页面文件还不存在，先制造编译失败。

**Step 2: 运行前端构建，确认失败**

Run:

```bash
cd frontend
npm run build
```

Expected: FAIL，找不到 `ScheduledJobsPage`

**Step 3: 最小实现页面与菜单**

- 新建路由：
  - `/scheduled-jobs`
- 在 `AppShell.tsx` 新增全新一级菜单组：
  - group key: `schedule`
  - group code: `SCH`
  - item key: `/scheduled-jobs`
  - label: `定时任务`
- 不要把入口加到现有 `operate` 组
- 页面实现最小能力：
  - 列表
  - 创建 / 编辑抽屉
  - 启停按钮
  - 手动触发按钮
  - 最近运行记录抽屉

**Step 4: 重新构建**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS

**Step 5: 提交**

```bash
git add frontend/src/pages/ScheduledJobsPage.tsx frontend/src/App.tsx frontend/src/components/shell/AppShell.tsx frontend/src/api/types.ts frontend/src/api/services.ts frontend/src/auth/permissions.ts
git commit -m "feat: add scheduled jobs page and navigation"
```

### Task 6: 在执行中心展示调度来源

**Files:**
- Modify: `D:\works\project\ezTest\TestTool\frontend\src\pages\ExecutionsPage.tsx`
- Modify: `D:\works\project\ezTest\TestTool\frontend\src\api\types.ts`
- Modify: `D:\works\project\ezTest\TestTool\frontend\src\api\services.ts`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\schemas\execution.py`
- Modify: `D:\works\project\ezTest\TestTool\backend\app\api\routes\executions.py`

**Step 1: 先写最小断言**

在后端测试或现有 execution 测试里补：

```python
assert execution_payload["trigger_source"] == "schedule"
assert execution_payload["scheduled_job_id"] == job.id
```

**Step 2: 运行测试，确认失败**

Run:

```bash
pytest tests/test_scheduled_jobs.py -k trigger_source -v
```

Expected: FAIL，execution schema 未暴露来源

**Step 3: 最小实现**

- 后端 `ExecutionRead` 暴露：
  - `trigger_source`
  - `scheduled_job_id`
  - `scheduled_run_id`
- 前端 `ExecutionsPage.tsx` 增加：
  - 来源标签 `手工触发 / 定时任务`
  - 若存在 `scheduled_job_id`，增加跳转到 `/scheduled-jobs`

**Step 4: 验证**

Run:

```bash
pytest tests/test_scheduled_jobs.py -v
cd frontend
npm run build
```

Expected: PASS

**Step 5: 提交**

```bash
git add frontend/src/pages/ExecutionsPage.tsx frontend/src/api/types.ts frontend/src/api/services.ts backend/app/schemas/execution.py backend/app/api/routes/executions.py tests/test_scheduled_jobs.py
git commit -m "feat: expose scheduled execution source"
```

### Task 7: 回归、文档与部署入口

**Files:**
- Modify: `D:\works\project\ezTest\TestTool\README.md`
- Modify: `D:\works\project\ezTest\TestTool\docs\manuals\execution-reliability.md`
- Modify: `D:\works\project\ezTest\TestTool\deploy\docker-compose.single-host.yml`
- Modify: `D:\works\project\ezTest\TestTool\.env.example`

**Step 1: 写部署与回归清单**

在文档中补：

- `scheduler` 进程如何启动
- 新增环境变量
- `SCHEDULE` 菜单入口说明
- 并发策略和 misfire 的用户可见语义

**Step 2: 运行回归**

Run:

```bash
pytest tests/test_scheduled_jobs.py -v
pytest tests/test_web_services.py -v
cd frontend
npm run build
```

Expected: 全部 PASS

**Step 3: 手工冒烟**

检查：

- 登录后左侧出现独立 `SCHEDULE` 菜单组
- 创建定时任务成功
- 立即触发成功生成 execution
- execution 详情可反查 schedule
- 禁用任务后不再自动触发

**Step 4: 提交**

```bash
git add README.md docs/manuals/execution-reliability.md deploy/docker-compose.single-host.yml .env.example
git commit -m "docs: document scheduled suite deployment"
```

## 推荐执行顺序

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7

不要并发执行 Task 1-4，它们共享模型和 schema 边界，抢跑只会制造返工。Task 5 和 Task 6 可以在后端 API 稳定后分开推进。

## 最终验收标准

- 用户能在独立 `SCHEDULE` 菜单组里管理定时任务
- 定时任务能引用 `suite + environment`
- 到点后自动创建 `pending suite execution`
- worker 能正常消费该 execution
- execution 能显示 `schedule` 来源
- 调度历史有独立 run 记录
- `forbid` 并发策略生效
- 全量回归测试和前端构建通过
