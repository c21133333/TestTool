# Eazy Test Web 执行链路可靠性手册

## 1. 目标

这份手册对应 roadmap 的“执行链路可靠性”，目标不是把执行系统做成调度平台，而是先把当前 v1 所需的可靠性底线收口。

本阶段覆盖：

- 默认请求超时
- 瞬时失败重试
- 取消语义收口
- stale 运行任务恢复
- 失败分类与定位信息

## 2. 当前策略

### 单用例执行

- 每个 case 默认带 `EAZYTEST_EXECUTION_REQUEST_TIMEOUT_SECONDS`
- 如 case 的 `metadata_json` 显式提供 `timeout_seconds`，优先使用 case 配置
- 瞬时失败会按 `EAZYTEST_EXECUTION_RETRY_LIMIT` 自动重试

### Suite 执行

- `pending` 任务由 worker 顺序消费
- 运行中如果收到 cancel 请求，会在下一个 case 开始前收口
- 运行中的 suite 超过 `EAZYTEST_EXECUTION_STALE_TIMEOUT_SECONDS` 会被 worker 标记为 stale failure

## 3. 失败分类

当前统一使用这些失败分类：

- `timeout`
- `request_error`
- `assertion_failed`
- `processor_abort`
- `invalid_request`
- `runtime_error`
- `canceled`
- `worker_stale`

这些分类会进入：

- `execution.summary_json.failure_breakdown`
- `execution.summary_json.first_failure`
- `execution_item.response_json.execution_meta`

## 4. 重试语义

- 仅瞬时失败会自动重试：`timeout`、`request_error`
- 默认重试次数为 1，表示“首次失败后再试一次”
- 重试历史会记录在 `execution_item.response_json.execution_meta.retry_history`
- `pending` 和 `running` 执行不允许手工点击 retry，只能对终态执行重试

## 5. 取消语义

- `pending` suite cancel：立即收口为失败终态，并标记 `_control.canceled=true`
- `running` suite cancel：先记录 `cancel_requested`，执行链路在安全边界处收口
- 当前不支持中断已经发出的单条 HTTP 请求

## 6. stale 恢复语义

worker 每次取任务前，都会先扫描长时间停留在 `running` 的 suite：

- 如果超过 `EAZYTEST_EXECUTION_STALE_TIMEOUT_SECONDS`
- 则标记为失败，并写入 `_control.worker_stale=true`
- 该任务不会自动续跑，需要由用户显式 retry 生成新执行

这是有意设计：

- 避免“半途恢复”导致状态不一致
- 保证失败路径清晰可定位
- 优先可恢复，而不是伪装成无损续跑

## 7. 建议配置

### development

```env
EAZYTEST_EXECUTION_REQUEST_TIMEOUT_SECONDS=20
EAZYTEST_EXECUTION_RETRY_LIMIT=0
EAZYTEST_EXECUTION_STALE_TIMEOUT_SECONDS=900
```

### test

```env
EAZYTEST_EXECUTION_REQUEST_TIMEOUT_SECONDS=20
EAZYTEST_EXECUTION_RETRY_LIMIT=1
EAZYTEST_EXECUTION_STALE_TIMEOUT_SECONDS=600
```

### production

```env
EAZYTEST_EXECUTION_REQUEST_TIMEOUT_SECONDS=20
EAZYTEST_EXECUTION_RETRY_LIMIT=1
EAZYTEST_EXECUTION_STALE_TIMEOUT_SECONDS=900
```

## 8. 边界说明

- 当前仍是单 worker 优先模型，不做分布式调度保证
- 当前超时主要收口在请求执行层，不强制杀死已发出的阻塞线程
- 更强的可观测性、任务指标和报警，放在后续“可观测性补全”阶段处理
## 9. Scheduled dispatch reliability

### Component roles

- `scheduler` only scans due jobs and creates `pending suite execution`.
- `worker` remains the only component that executes suite cases.
- `api` can create, enable, disable, and trigger scheduled jobs, but it does not replace the scheduler loop.

### Dispatch guarantees

- A scheduled run writes a dedicated `scheduled_job_run` record before or while creating the linked execution.
- `execution.trigger_source=schedule` is the source-of-truth marker for schedule-created executions.
- `execution.scheduled_job_id` and `execution.scheduled_run_id` are used for reverse tracing from execution back to schedule.

### Concurrency policy

- `forbid`: if the same scheduled job still has an active `pending/running` execution, the new run is recorded as `skipped`.
- `allow`: the scheduler may enqueue another execution for the same job.
- `replace`: reserved for future implementation and should not be relied on operationally.

### Misfire policy

- `skip`: if the due window is missed, the scheduler advances `next_run_at` and does not backfill immediately.
- `fire_once`: reserved as a schema-level option; rollout should treat it as opt-in and verify behavior before production use.

### Operational checks

- If scheduled jobs stop dispatching, verify the `scheduler` process is running before checking `worker`.
- If executions exist but never start, inspect the `worker` process and `pending` queue depth.
- If an execution looks unexpected, open the execution detail page and verify `trigger_source`, `scheduled_job_id`, and `scheduled_run_id`.
