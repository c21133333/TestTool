# Eazy Test Web 部署拓扑手册

## 1. 目标

这份手册对应 roadmap 的“部署拓扑标准化”，目标是把当前系统沉淀成一套团队可重复拉起的标准部署方式，而不是继续依赖作者本机经验。

交付范围：

- 推荐部署拓扑
- 单机部署方案
- 最小生产部署方案
- 反向代理与静态资源托管说明
- 进程保活策略

## 2. 推荐拓扑

当前代码结构最适合采用“同一应用镜像 + 分离 api / worker 进程 + 独立 PostgreSQL + 前置 Nginx”的拓扑。

```text
Browser
  |
  v
Nginx
  |
  v
FastAPI API container  <------>  PostgreSQL
  |
  +------> shared reports volume

Worker container  <----------->  PostgreSQL
  |
  +------> shared reports volume
```

解释：

- `api` 负责 REST API 和前端页面返回
- `worker` 负责消费 suite 执行任务
- `PostgreSQL` 负责主数据与执行记录
- `Nginx` 负责统一入口、反向代理和后续 TLS 接入
- `reports` 使用共享卷，确保 worker 生成的报告可被 API 读取

## 3. 为什么这样部署

当前后端已经支持托管 `frontend/dist`，所以最小生产方案不需要额外的前端运行时容器。

这带来几个好处：

- 拓扑简单，部署成本低
- API 与前端版本天然一致
- worker 与 API 使用同一套代码和依赖
- 未来需要拆分静态托管时，也有明确演进路径

## 4. 单机部署方案

适用场景：

- 小团队共享环境
- 预发布环境
- 低流量正式环境

推荐资产：

- `Dockerfile`
- `deploy/docker-compose.single-host.yml`
- `deploy/env/production.env.example`
- `deploy/nginx/eazytest.conf`

启动步骤：

1. 复制 `deploy/env/production.env.example` 为实际环境文件并修改敏感配置
2. 调整数据库口令和域名相关配置
3. 执行 `docker compose -f deploy/docker-compose.single-host.yml up -d --build`
4. 首次发布前单独执行迁移命令

首次迁移建议：

```powershell
docker compose -f deploy/docker-compose.single-host.yml run --rm api python -m requesttool migrate
```

## 5. 最小生产部署方案

最低建议组合：

- 1 台主机
- 1 个 PostgreSQL 实例
- 1 个 API 进程
- 1 个 worker 进程
- 1 个 Nginx 入口
- 1 个共享报告目录

最低要求：

- `EAZYTEST_DEPLOYMENT_ENV=production`
- `EAZYTEST_DATABASE_AUTO_MIGRATE=false`
- 禁止 bootstrap admin
- API 和 worker 使用相同版本镜像
- 报告目录持久化

## 6. 反向代理与静态资源托管

当前标准方案里，Nginx 不直接构建前端，而是把所有请求反代到 API 容器，由 FastAPI 返回 `frontend/dist`。

这是有意选择，不是偷懒：

- 贴合当前代码结构
- 避免多一套静态资源发布链路
- 单镜像更容易回滚

如果后续访问量上来，再演进到：

- Nginx 直接托管 `frontend/dist`
- `/api/v1`、`/docs`、`/openapi.json` 反代到 API

但在当前 v1 前，不建议过早拆分。

## 7. 进程保活策略

### Docker 部署

默认策略：

- `api`、`worker`、`db`、`nginx` 都使用 `restart: unless-stopped`
- `api` 提供健康检查
- `worker` 依赖 `api` 和 `db` 可用后再启动

### 非 Docker 部署

可用 `systemd` 托管：

- `deploy/systemd/eazytest-api.service`
- `deploy/systemd/eazytest-worker.service`

要求：

- 使用同一个工作目录
- 使用同一份 `.env`
- 统一通过虚拟环境执行

## 8. 回滚与升级建议

升级顺序：

1. 备份数据库
2. 执行迁移
3. 发布 API
4. 发布 worker
5. 验证健康检查与执行链路

回滚原则：

- 代码版本和镜像版本一起回滚
- 数据库迁移必须有对应回滚策略
- 不要让 API 和 worker 长时间处于不同版本

## 9. 关联文件

- `Dockerfile`
- `deploy/docker-compose.single-host.yml`
- `deploy/nginx/eazytest.conf`
- `deploy/systemd/eazytest-api.service`
- `deploy/systemd/eazytest-worker.service`
- `docs/manuals/environment-governance.md`
