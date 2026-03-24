# Eazy Test Web 配置与环境治理手册

## 1. 目标

这份手册对应 roadmap 的“配置与环境治理”收口，目标不是增加更多配置，而是把运行配置变成：

- 清晰：新环境不需要翻源码找变量
- 可控：dev / test / production 边界明确
- 可审计：危险默认值在启动前直接失败

## 2. 配置来源

后端统一使用 `EAZYTEST_` 前缀读取环境变量，并支持仓库根目录 `.env` 文件。

推荐优先级：

1. 进程环境变量
2. 仓库根目录 `.env`
3. 代码默认值

原则：

- 默认值只服务本地开发
- 共享环境和生产环境必须显式声明关键配置
- 不允许依赖“隐式安全”或“启动后再看日志”

## 3. 环境分层约定

### development

适用场景：

- 本地开发
- 功能联调
- UI / API 快速验证

推荐配置：

- `EAZYTEST_DEPLOYMENT_ENV=development`
- `EAZYTEST_DATABASE_URL=sqlite:///./web_eazytest.db`
- `EAZYTEST_DATABASE_AUTO_MIGRATE=true`
- `EAZYTEST_BOOTSTRAP_ADMIN_ENABLED=false`，如确有本地初始化需要，再显式开启

### test

适用场景：

- CI
- 集成测试
- 临时验证环境

推荐配置：

- `EAZYTEST_DEPLOYMENT_ENV=test`
- 使用隔离数据库
- 可按需要启用 `EAZYTEST_DATABASE_AUTO_MIGRATE=true`
- 禁止把测试环境当作长期共享环境使用

### production

适用场景：

- 团队共享正式环境
- 对外提供持续服务的发布环境

强制规则：

- `EAZYTEST_DEPLOYMENT_ENV=production`
- 必须使用 PostgreSQL 或同等级生产数据库
- 必须设置 `EAZYTEST_DATABASE_AUTO_MIGRATE=false`
- 禁止 `EAZYTEST_BOOTSTRAP_ADMIN_ENABLED=true`
- 首个管理员必须通过显式初始化流程创建，而不是依赖启动时注入

## 4. 关键配置项

| 配置项 | 用途 | 默认值 | 生产要求 |
| --- | --- | --- | --- |
| `EAZYTEST_DEPLOYMENT_ENV` | 运行环境标识 | `development` | 必须显式设为 `production` |
| `EAZYTEST_DATABASE_URL` | 数据库连接串 | SQLite | 必须改为 PostgreSQL |
| `EAZYTEST_DATABASE_AUTO_MIGRATE` | 启动时自动迁移 | `true` | 必须为 `false` |
| `EAZYTEST_REPORT_DIR` | 报告输出目录 | `web_runs` | 建议挂载到持久化存储 |
| `EAZYTEST_REPORT_TEMPLATE_PATH` | HTML 报告模板路径 | 内置模板 | 路径必须存在 |
| `EAZYTEST_AUTH_TOKEN_TTL_HOURS` | token 生命周期 | `12` | 按安全策略显式确认 |
| `EAZYTEST_AUTH_MAX_ACTIVE_TOKENS_PER_USER` | 每用户活跃 token 上限 | `5` | 按团队策略显式确认 |
| `EAZYTEST_USER_PASSWORD_MIN_LENGTH` | 密码最短长度 | `12` | 不建议低于默认值 |
| `EAZYTEST_EXECUTION_REQUEST_TIMEOUT_SECONDS` | 默认请求超时 | `20` | 建议显式确认 |
| `EAZYTEST_EXECUTION_RETRY_LIMIT` | 瞬时失败重试次数 | `1` | 建议显式确认 |
| `EAZYTEST_EXECUTION_STALE_TIMEOUT_SECONDS` | stale 运行任务恢复阈值 | `900` | 建议显式确认 |
| `EAZYTEST_BOOTSTRAP_ADMIN_ENABLED` | 启动时创建管理员 | `false` | 必须保持 `false` |
| `EAZYTEST_WORKER_POLL_INTERVAL_SECONDS` | worker 轮询间隔 | `2.0` | 按吞吐和资源调整 |

## 5. 启动前检查机制

当前系统会在 API 和 worker 启动前执行统一校验。

直接失败的场景包括：

- `production` 仍使用 SQLite
- `production` 仍启用自动迁移
- `production` 试图启用 bootstrap admin
- 报告模板路径不存在
- `api_prefix` 不是以 `/` 开头
- worker 轮询间隔小于等于 0

这类失败属于“配置错误”，不是运行时告警，必须在启动前解决。

## 6. 推荐落地方式

### 本地开发

```env
EAZYTEST_DEPLOYMENT_ENV=development
EAZYTEST_DATABASE_URL=sqlite:///./web_eazytest.db
EAZYTEST_DATABASE_AUTO_MIGRATE=true
EAZYTEST_BOOTSTRAP_ADMIN_ENABLED=false
```

### 测试环境

```env
EAZYTEST_DEPLOYMENT_ENV=test
EAZYTEST_DATABASE_URL=postgresql://tester:secret@db-host:5432/eazytest_test
EAZYTEST_DATABASE_AUTO_MIGRATE=true
EAZYTEST_BOOTSTRAP_ADMIN_ENABLED=false
```

### 生产环境

```env
EAZYTEST_DEPLOYMENT_ENV=production
EAZYTEST_DATABASE_URL=postgresql://app:secret@db-host:5432/eazytest
EAZYTEST_DATABASE_AUTO_MIGRATE=false
EAZYTEST_BOOTSTRAP_ADMIN_ENABLED=false
```

生产建议流程：

1. 先执行 `python -m requesttool migrate`
2. 再启动 `python -m requesttool serve`
3. 最后启动 `python -m requesttool worker`

## 7. 运维注意事项

- `.env` 只应保存当前环境自己的配置，不要把多环境内容混放在一个文件里
- 生产数据库、令牌策略和管理员初始化必须走变更流程
- `web_runs/` 属于运行产物目录，不应作为源码提交对象
- 配置变更后，优先重启 API 和 worker 以确保同一套配置生效

## 8. 关联文档

- `README.md`
- `docs/security/permissions-matrix.md`
- `docs/manuals/execution-reliability.md`
- `docs/manuals/observability.md`
- `docs/plans/2026-03-23-v1-roadmap.md`
