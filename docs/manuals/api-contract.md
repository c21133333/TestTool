# Eazy Test Web API 契约手册

## 1. 目标

这份手册对应 roadmap 的“API 契约与错误模型收口”。目标不是重新设计整套接口，而是把当前 v1 已有 API 收成一套稳定、可预测、可文档化的契约。

本阶段统一四件事：

- 成功响应包络
- 错误响应包络
- 分页与筛选参数命名
- OpenAPI 中的公共错误响应说明

## 2. 成功响应

所有 JSON 成功响应统一使用：

```json
{
  "success": true,
  "message": "Projects loaded.",
  "data": {}
}
```

### 单对象 / 动作型接口

适用于：

- 创建
- 更新
- 获取详情
- 登录
- 取消 / 重试等动作

`data` 直接放业务对象。

### 列表接口

所有主列表接口统一使用分页 envelope：

```json
{
  "success": true,
  "message": "Projects loaded.",
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20
  }
}
```

当前已统一的列表接口包括：

- `/projects`
- `/suites`
- `/cases`
- `/environments`
- `/users`
- `/reports`
- `/executions`
- `/audit-logs`

## 3. 错误响应

所有 JSON 错误统一使用：

```json
{
  "success": false,
  "message": "Authentication required.",
  "error": {
    "code": "unauthorized",
    "status": 401,
    "details": null,
    "request_id": "..."
  },
  "data": null
}
```

### 当前错误码映射

- `400 -> bad_request`
- `401 -> unauthorized`
- `403 -> forbidden`
- `404 -> not_found`
- `409 -> conflict`
- `422 -> validation_error`
- `500 -> internal_error`

### 422 校验错误

`details.errors` 直接保留 FastAPI/Pydantic 的校验结果，前端不需要再猜 `detail` 字段。

## 4. 分页与筛选规则

### 通用分页参数

- `page`
- `page_size`

约束：

- `page >= 1`
- `1 <= page_size <= 100`

### 筛选参数命名

保持 snake_case，不混用 camelCase：

- `project_id`
- `suite_id`
- `failed_only`
- `start_at`
- `end_at`

## 5. 前端适配约定

前端 `ApiClient` 现在优先解析统一错误包络；只有在旧接口或非标准响应场景下，才回退读取 `detail`。

为避免一次性改动全部页面：

- 后端 API 正式统一为分页 envelope
- 前端 `services.ts` 对 `projects / suites / cases / environments / users / reports` 先做兼容解包，只向页面返回 `items`

这意味着页面层不需要同时承担契约迁移。

## 6. OpenAPI 说明

公共错误响应已经统一挂到主 router 上，因此 OpenAPI 会显示标准错误模型，而不是只剩下默认的 FastAPI `detail` 结构。

这一步的意义不是“文档更漂亮”，而是让前后端和测试都能基于同一份错误结构协作。

## 7. 边界说明

- 报告内容下载接口仍然返回文件流，不走 JSON success envelope
- 当前没有引入业务级子错误码枚举，只先收敛 HTTP status 到稳定 code
- 前端页面层暂时仍主要消费数组，完整分页交互会在后续产品化阶段继续推进

## 8. 关联文档

- `README.md`
- `docs/manuals/observability.md`
- `docs/manuals/execution-reliability.md`
- `docs/archive/plans/2026-03-23-v1-roadmap.md`
