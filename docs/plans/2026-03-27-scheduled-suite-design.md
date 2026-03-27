# Scheduled Suite Design

## 1. Goal

为 Eazy Test Web 增加“定时跑套件”能力，使用户可以为已有 `suite` 配置周期性执行规则，并在到点时自动创建 `execution`，由现有 worker 链路消费执行。

本设计仅覆盖 **方案 A：定时任务引用 Suite**，目标是以最小领域改动上线可用版本。

## 2. Non-Goals

- 不引入 `case_group` / `case_set` 正式实体
- 不支持跨 suite 混选 case 组成执行目标
- 不引入 Redis、Celery、外部 MQ 等新基础设施
- 不实现复杂工作流编排，例如多 suite 串行/并行依赖
- 不做通知中心、告警升级、审批流

## 3. Current Context

当前系统已经具备可复用的执行主链路：

- `suite` 是现有聚合边界，`case` 从属于 `suite`
- `suite execution` 会先写入 `executions` 表，状态为 `pending`
- worker 以轮询方式消费 `pending suite execution`
- `case execution` 为同步直跑，不进入 worker 队列

这意味着定时能力不应该直接重写执行逻辑，而应该只承担“到点触发并创建 suite execution”的职责。

## 4. Design Principles

1. **复用优先**
   - 调度器只创建 execution，不直接跑 case。
   - 执行语义继续由 `ExecutionService` 与 worker 负责。

2. **范围收敛**
   - 首版仅支持 `suite`。
   - 未来如果需要 `case_group`，在调度层扩展 target type，而不推翻当前模型。

3. **幂等优先**
   - 同一个调度窗口不能因为多实例或重复轮询而触发多次。
   - 调度触发记录需要独立留痕。

4. **运营可见**
   - 用户必须看到任务是否启用、下次运行时间、最近结果。
   - execution 需要能反查来源 schedule。

## 5. User Story

### 5.1 创建任务

测试人员在“定时任务”页面：

- 选择项目下某个 suite
- 选择执行环境
- 配置 cron 表达式
- 配置时区
- 配置并发策略
- 启用或暂停任务

保存后，系统计算 `next_run_at`。

### 5.2 调度触发

当系统时间达到 `next_run_at`：

- scheduler 领取到期 job
- 校验该 job 当前状态、并发策略与 suite / environment 是否仍有效
- 创建一条新的 `suite execution`
- 写入一次 `scheduled_job_run`
- 回写 `last_triggered_at`、`last_triggered_execution_id`
- 计算新的 `next_run_at`

### 5.3 结果查看

用户可以：

- 在“定时任务列表”查看最近一次触发结果
- 点击跳转到对应 execution 详情
- 在 execution 详情里看到本次执行来源于哪个 schedule

## 6. Domain Model

新增两个实体：

### 6.1 `scheduled_jobs`

表示一条定时规则。

建议字段：

- `id`
- `project_id`
- `suite_id`
- `environment_id`
- `name`
- `description`
- `cron_expr`
- `timezone`
- `enabled`
- `next_run_at`
- `last_triggered_at`
- `last_triggered_execution_id`
- `concurrency_policy`
- `misfire_policy`
- `created_by_user_id`
- `updated_by_user_id`
- `created_at`
- `updated_at`

字段说明：

- `suite_id`
  - 直接引用 suite，避免引入 target_type / target_id 泛化设计
- `timezone`
  - 首版保留，避免默认服务端时区造成理解偏差
- `concurrency_policy`
  - `forbid`: 上一次未结束则跳过本次
  - `allow`: 允许并发创建新的 execution
  - `replace`: 首版不执行强制中断，仅语义上按 `forbid` 降级处理并记录 warning
- `misfire_policy`
  - `skip`: 错过窗口则跳过
  - `fire_once`: 错过窗口则补触发一次

### 6.2 `scheduled_job_runs`

表示调度器的一次触发尝试，用于审计和幂等。

建议字段：

- `id`
- `scheduled_job_id`
- `planned_run_at`
- `triggered_at`
- `execution_id`
- `status`
- `message`
- `created_at`

`status` 建议枚举：

- `triggered`
- `skipped`
- `failed`

说明：

- `planned_run_at` 是本次理论应触发时间点，不是实际落库时间
- 对同一 job + 同一 `planned_run_at` 建唯一约束，作为幂等闸门

## 7. Execution Model Changes

### 7.1 `Execution` 增加调度来源字段

建议在 `executions` 表上追加：

- `trigger_source`: `manual` | `schedule`
- `scheduled_job_id`
- `scheduled_run_id`

目的：

- execution 列表能区分“手工发起”还是“定时触发”
- 方便从 execution 反查 schedule 和本次调度记录

### 7.2 保持现有 worker 语义不变

调度器创建出来的 execution 仍然是：

- `scope = suite`
- `status = pending`

worker 不需要知道 execution 是手工触发还是调度触发，只继续消费 pending suite execution。

## 8. API Design

新增资源：`/scheduled-jobs`

### 8.1 列表

`GET /api/v1/scheduled-jobs`

查询参数建议：

- `page`
- `page_size`
- `project_id`
- `suite_id`
- `enabled`
- `search`

返回字段建议：

- job 基本信息
- suite / environment 简要信息
- `next_run_at`
- `last_triggered_at`
- `last_triggered_execution_id`
- `last_run_status`

### 8.2 创建

`POST /api/v1/scheduled-jobs`

请求体建议：

```json
{
  "project_id": 1,
  "suite_id": 12,
  "environment_id": 3,
  "name": "每日冒烟",
  "description": "工作日早上执行登录与核心下单链路",
  "cron_expr": "0 0 9 * * 1-5",
  "timezone": "Asia/Shanghai",
  "enabled": true,
  "concurrency_policy": "forbid",
  "misfire_policy": "skip"
}
```

校验规则：

- suite 必须属于 project
- environment 必须属于同一 project
- cron 必须合法
- timezone 必须合法

### 8.3 更新

`PUT /api/v1/scheduled-jobs/{job_id}`

更新时重新计算 `next_run_at`。

### 8.4 启停

`POST /api/v1/scheduled-jobs/{job_id}/enable`

`POST /api/v1/scheduled-jobs/{job_id}/disable`

说明：

- 单独开接口比复用 update 更利于审计
- enable 时重算 `next_run_at`
- disable 后不清空历史执行记录

### 8.5 立即触发

`POST /api/v1/scheduled-jobs/{job_id}/trigger`

说明：

- 这是运营效率接口
- 行为等同于“按当前 job 配置手动触发一次”
- 会创建 `scheduled_job_run`
- `planned_run_at = triggered_at`

### 8.6 运行历史

`GET /api/v1/scheduled-jobs/{job_id}/runs`

返回最近 N 次 `scheduled_job_runs`，用于前端展示触发成功、跳过、失败原因。

## 9. Scheduler Runtime Design

新增 scheduler 组件，但仍运行在现有 backend 进程体系内。

### 9.1 组件职责拆分

#### `ScheduledJobService`

负责：

- CRUD
- 参数校验
- cron / timezone 解析
- `next_run_at` 计算

#### `ScheduledJobRepository`

负责：

- 查询到期 job
- 乐观/悲观领取 job
- 创建 run 记录
- 回写 next_run_at / last_triggered_at

#### `ScheduleDispatchService`

负责：

- 判断并发策略
- 判断 misfire 语义
- 创建 execution
- 写 run 记录

#### `scheduler worker`

负责：

- 周期扫描 `next_run_at <= now` 的 enabled job
- 批量触发 dispatch
- 写日志与监控事件

### 9.2 推荐运行方式

新增独立入口，例如：

- `backend/app/scheduler.py`
- `backend/scheduler.py`

保持与现有 API / worker 拆开部署：

- `api`: 提供管理接口
- `worker`: 消费 execution
- `scheduler`: 产生 execution

这是最清晰的职责分离，也避免把调度轮询耦合进 API 进程。

### 9.3 调度轮询流程

伪代码：

```text
loop:
  now = utc_now()
  due_jobs = repository.list_due_jobs(now, limit=N)
  for job in due_jobs:
    begin transaction
      lock job
      refresh latest state
      if job disabled:
        continue
      planned_run_at = job.next_run_at
      if run for (job_id, planned_run_at) already exists:
        advance next_run_at if needed
        continue
      if concurrency_policy says skip:
        create scheduled_job_run(status=skipped)
        advance next_run_at
        commit
        continue
      create execution via queue_suite_execution_from_schedule(...)
      create scheduled_job_run(status=triggered, execution_id=...)
      update job.last_triggered_at
      update job.last_triggered_execution_id
      update job.next_run_at
    commit
  sleep(poll_interval)
```

## 10. Concurrency and Idempotency

这是本功能最重要的非功能设计点。

### 10.1 幂等闸门

必须同时具备两层保障：

1. **数据库唯一约束**
   - `scheduled_job_runs(job_id, planned_run_at)` 唯一
2. **事务内加锁**
   - 领取 job 时对 job 行加锁

这样即使 scheduler 有多个实例，也只能有一个实例成功写入本次 run。

### 10.2 并发策略

首版只真正支持两种：

- `forbid`
  - 如果该 job 最近触发的 suite execution 仍处于 `pending` 或 `running`
  - 则本轮创建 `scheduled_job_run(status=skipped, message="previous execution still active")`
- `allow`
  - 直接创建新的 execution

`replace` 暂不真正中断旧任务，因为当前 suite cancel 是“请求取消”语义，不是强制抢占。首版若暴露该枚举，建议在服务端降级为 `forbid` 并返回 warning；更稳妥的做法是首版不暴露 `replace`。

### 10.3 Misfire 处理

定义：

- scheduler 停机
- 或进程阻塞
- 或系统时间漂移
- 导致 `next_run_at` 已经过期

首版建议：

- 默认 `skip`
- 可选 `fire_once`

语义：

- `skip`: 只记录 skipped run，然后直接推算下一个未来时间点
- `fire_once`: 补一条 execution，然后推算下一个未来时间点

不建议首版支持“补齐所有错过窗口”，否则在长时间停机后会瞬间制造任务风暴。

## 11. Validation Rules

创建和更新 job 时，服务端必须做这些校验：

- suite 存在，且未被删除
- suite 属于 `project_id`
- environment 存在且属于同一 project
- cron 表达式合法
- timezone 为合法 IANA 时区
- `name` 去空白后非空

触发前仍需二次校验：

- suite 仍存在
- environment 仍存在
- suite / environment 仍属于同一 project

如果引用对象失效：

- 本次 run 记为 `failed`
- job 不自动删除
- 在列表中暴露异常状态，等待用户修复

## 12. Audit and Observability

### 12.1 Audit Log

新增 audit action：

- `scheduled_job.create`
- `scheduled_job.update`
- `scheduled_job.enable`
- `scheduled_job.disable`
- `scheduled_job.trigger`
- `scheduled_job.delete`

### 12.2 Structured Log

新增事件：

- `schedule.job.dispatched`
- `schedule.job.skipped`
- `schedule.job.failed`
- `schedule.worker.started`

关键日志字段：

- `scheduled_job_id`
- `planned_run_at`
- `execution_id`
- `suite_id`
- `environment_id`
- `concurrency_policy`
- `misfire_policy`

### 12.3 页面可见性

前端至少展示：

- 任务状态：启用 / 暂停 / 异常
- cron + 时区
- 下次运行时间
- 最近触发时间
- 最近触发结果
- 最近 execution 链接

## 13. Frontend Design

### 13.1 新页面

建议新增 `ScheduledJobsPage`，并放在左侧导航的**全新一级菜单组**下，而不是塞进现有 `OPS` 分组。

建议信息架构：

- 一级菜单组：`SCHEDULE`
- 页面入口：`定时任务`
- 路由：`/scheduled-jobs`

原因：

- 该功能是“自动触发执行”，语义上不同于手工执行中心
- 独立菜单能避免用户把“执行记录”和“调度配置”混为一谈
- 未来如果扩展 cron 模板、通知、维护窗口、任务健康度，也有清晰承载位

页面分为两块：

1. 任务列表
   - 搜索
   - 项目过滤
   - 状态过滤
   - 最近结果标记

2. 创建 / 编辑抽屉
   - project
   - suite
   - environment
   - cron
   - timezone
   - enabled
   - concurrency policy
   - misfire policy
   - 描述

### 13.2 与执行中心联动

在 execution 列表或详情页增加以下展示：

- `trigger_source`
- 若来自 schedule，则展示 schedule 名称 / 快捷跳转

这样可以回答“这条执行是谁发起的”。

## 14. Permission Model

建议沿用当前执行权限：

- `admin` / `tester`
  - 创建、编辑、启停、删除、立即触发
- `developer`
  - 只读查看

理由：

- 定时任务本质是自动化执行配置，权限等级不应低于手工执行

## 15. Failure Semantics

### 15.1 调度失败

调度失败不等于 execution 失败，两者需要分层：

- **调度失败**
  - 没能成功创建 execution
  - 记录在 `scheduled_job_runs`
- **执行失败**
  - execution 已创建，但 suite 跑挂
  - 记录在 execution / report 体系

### 15.2 失败场景

典型调度失败：

- suite 已删除
- environment 已删除
- cron 计算异常
- DB 锁竞争异常
- 创建 execution 事务失败

处理原则：

- run 记录必须落库
- 不能因为调度失败而丢失本次触发审计
- job 本身保持可见，等待人工修复

## 16. Schema Sketch

### 16.1 `scheduled_jobs`

```sql
create table scheduled_jobs (
  id integer primary key,
  project_id integer not null references projects(id) on delete cascade,
  suite_id integer not null references suites(id) on delete cascade,
  environment_id integer null references environments(id) on delete set null,
  name varchar(128) not null,
  description text not null default '',
  cron_expr varchar(128) not null,
  timezone varchar(64) not null,
  enabled boolean not null default true,
  concurrency_policy varchar(16) not null default 'forbid',
  misfire_policy varchar(16) not null default 'skip',
  next_run_at timestamptz null,
  last_triggered_at timestamptz null,
  last_triggered_execution_id integer null references executions(id) on delete set null,
  created_by_user_id integer null references users(id) on delete set null,
  updated_by_user_id integer null references users(id) on delete set null,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

### 16.2 `scheduled_job_runs`

```sql
create table scheduled_job_runs (
  id integer primary key,
  scheduled_job_id integer not null references scheduled_jobs(id) on delete cascade,
  planned_run_at timestamptz not null,
  triggered_at timestamptz null,
  execution_id integer null references executions(id) on delete set null,
  status varchar(16) not null,
  message text not null default '',
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique (scheduled_job_id, planned_run_at)
);
```

### 16.3 `executions` 扩展

```sql
alter table executions
  add column trigger_source varchar(16) not null default 'manual';

alter table executions
  add column scheduled_job_id integer null references scheduled_jobs(id) on delete set null;

alter table executions
  add column scheduled_run_id integer null references scheduled_job_runs(id) on delete set null;
```

## 17. Service-Level Changes

### 17.1 `ExecutionService`

新增方法建议：

- `queue_suite_execution_from_schedule(job, run_record)`

与现有 `queue_suite_execution(...)` 的区别：

- `triggered_by_user_id = null`
- `trigger_source = schedule`
- 回填 `scheduled_job_id` / `scheduled_run_id`

### 17.2 `ExecutionRepository`

新增查询：

- 查询某个 schedule 最近是否存在活跃 execution
- execution 列表 / 详情查询时带出调度来源字段

### 17.3 `AuditLogService`

补 schedule 相关动作。

## 18. Testing Strategy

### 18.1 Unit Tests

- cron / timezone 解析
- `next_run_at` 计算
- `forbid` 并发策略
- `allow` 并发策略
- `skip` misfire
- `fire_once` misfire
- 同一 `planned_run_at` 幂等保护

### 18.2 Integration Tests

- 创建 enabled schedule 后正确计算 `next_run_at`
- scheduler 到点后成功创建一条 `pending suite execution`
- 当上次 execution 未结束时，`forbid` 正确跳过
- suite 被删除后，本次 run 记 failed
- 手动 trigger 成功生成 execution

### 18.3 Regression Tests

- 手工 `run suite`
- 手工 `run case`
- worker 消费 `pending suite execution`
- cancel / retry 语义

## 19. Rollout Plan

### Phase 1

- migration
- model / repository
- service / API
- scheduler worker
- 基础前端页面

### Phase 2

- execution 页面展示调度来源
- 运行历史页
- 更多列表筛选

### Phase 3

- 指标与告警
- 高级 misfire 策略
- schedule 健康状态聚合

## 20. Risks

### 风险 1：重复触发

原因：

- 多实例 scheduler
- 事务外计算 next_run_at

缓解：

- 唯一约束 + 事务内写 run 记录

### 风险 2：任务风暴

原因：

- scheduler 停机恢复后补齐过多 misfire

缓解：

- 首版禁止“补齐全部”，最多 `fire_once`

### 风险 3：引用漂移

原因：

- suite / environment 被删除或迁移

缓解：

- 触发前二次校验
- 列表暴露异常状态

## 21. Recommendation

建议按以下顺序实施：

1. 先补模型和 migration
2. 再补 scheduler worker 与 service
3. 然后打通 CRUD API
4. 最后上前端管理页面和 execution 来源展示

这条路径的优点是：

- 复用现有 execution 主链路
- 不改现有 suite / case 领域结构
- 支持未来平滑演进到 `case_group`

## 22. Open Questions

当前仍有两个需要产品确认但不阻塞设计落地的问题：

1. cron 表达式是否直接面向高级用户开放，还是前端只提供“每天/每周/工作日”模板生成
2. 首版是否需要在 UI 中暴露 `misfire_policy=fire_once`，还是服务端先固定为 `skip`

在没有额外约束的前提下，本设计默认：

- 前端支持 cron 原文输入
- 首版默认并推荐 `misfire_policy = skip`
