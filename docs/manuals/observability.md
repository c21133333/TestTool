# Eazy Test Web 可观测性手册

## 1. 目标

这份手册对应 roadmap 的“可观测性补全”。目标不是一次性引入完整监控平台，而是先把 v1 最需要的三件事补齐：

- 结构化日志：日志可机器解析，不再靠字符串猜上下文
- 健康与依赖状态：数据库、报告模板、报告目录一眼可见
- 最小指标快照：执行总量、成功率、失败数、平均耗时可直接查看

## 2. 当前观测面

### 结构化日志

API 和 worker 统一输出 JSON 日志，核心字段包括：

- `timestamp`
- `level`
- `component`
- `logger`
- `event`
- `request_id`

HTTP 请求会自动生成或透传 `X-Request-ID`，并回写到响应头。

### 关键业务事件

当前已补齐这些事件：

- 登录成功 / 失败 / 禁用拦截
- token 签发与注销
- Excel / legacy project 导入开始与完成
- case 执行、suite 入队、执行完成、取消、重试、stale 恢复
- 报告生成开始、失败、完成
- API / worker 启动

## 3. 健康检查

接口：

```text
GET /api/v1/health
```

返回内容包含：

- `status`：`ok` 或 `degraded`
- `readiness`：依赖是否全部可用
- `dependencies`：数据库、报告模板、报告目录
- `metrics`：执行指标快照
- `runtime`：运行环境和关键配置摘要

### 依赖判定规则

- `database`：执行 `SELECT 1`
- `report_template`：模板文件必须存在
- `report_dir`：报告目录必须可创建/可访问

只要有任一依赖退化，`status` 就会变成 `degraded`。

## 4. 最小指标集合

当前健康接口直接基于数据库执行记录聚合：

- `total_executions`
- `success_count`
- `failed_count`
- `pending_count`
- `running_count`
- `success_rate`
- `average_duration_ms`
- `stale_failure_count`
- `last_execution_at`

这是一套“排障优先”的快照，不是时序监控替代品。

## 5. 推荐配置

```env
EAZYTEST_LOG_LEVEL=INFO
```

### development

- `INFO` 足够
- 只在调试链路时临时切到 `DEBUG`

### production

- 推荐保持 `INFO`
- 如遇故障排查，可短时切换到 `DEBUG`，排查后恢复

## 6. 运维使用建议

### 先看健康接口

如果用户反馈“跑不起来”或“报告没生成”，先访问：

```text
/api/v1/health
```

先确认是不是数据库、模板路径、报告目录问题。

### 再按 request_id 查日志

API 请求都会返回 `X-Request-ID`。排查时优先拿这个值过滤日志，而不是全文搜索。

### 最后看执行摘要

执行链路问题优先看：

- `failure_breakdown`
- `first_failure`
- `retry_stats`

这样比只看 `failed` 更容易判断是 timeout、request error 还是 assertion failure。

## 7. 边界说明

- 当前还没有 Prometheus / Grafana / tracing
- 当前指标是健康快照，不带时间窗口维度
- 当前日志默认输出到 stdout，落盘与采集由部署层负责

## 8. 关联文档

- `README.md`
- `docs/manuals/environment-governance.md`
- `docs/manuals/execution-reliability.md`
- `docs/plans/2026-03-23-v1-roadmap.md`
