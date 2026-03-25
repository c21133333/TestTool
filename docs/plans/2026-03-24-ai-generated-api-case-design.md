# AI-Generated API Case Design

## Goal

Add a new Web-native module that turns Markdown API documentation into editable API case drafts, supports human review in the UI, and imports approved drafts into the existing project / suite / case model.

This feature is a new authoring pipeline. It is not an extension of legacy Excel semantics.

## Context

The current system already supports:

- project / suite / case CRUD
- Excel import as a migration bridge
- structured case editing in the Workspace UI
- legacy `ai_case` mapping during desktop `project.json` import

The compatibility policy explicitly freezes historical Excel semantics. New AI generation must therefore target the Web data model directly and only reuse import-style persistence logic where useful.

## Product Scope

### In Scope

- Upload `.md` API documentation
- Provide target project, suite name, AI provider settings, and runtime API key
- Generate standardized case drafts through LLM
- Show drafts in an editable preview table
- Allow users to edit, delete, and selectively approve rows
- Import approved drafts into a suite in the target project
- Return import results and per-row failures

### Out of Scope

- Auto-import without human approval
- Persisting user API keys in database
- Extending legacy Excel templates or alias rules
- Full doc versioning in v1
- Background async job orchestration in v1

## User Flow

1. User opens `AI 生成接口用例`.
2. User selects target project and enters target suite name.
3. User uploads Markdown documentation.
4. User enters AI provider configuration:
   - provider
   - model
   - base URL (optional)
   - API key
5. Backend parses Markdown into endpoint-oriented sections.
6. Backend calls LLM and asks for normalized case drafts.
7. Backend validates and normalizes the result, then returns preview data.
8. Frontend renders editable rows.
9. User edits fields inline or through JSON editors.
10. User checks rows to import and submits approval.
11. Backend validates again and creates the suite plus cases.
12. UI shows import summary and refreshes workspace data.

## UX Design

### Entry Placement

Add a new card in `WorkspacePage` near the existing import area:

- Title: `AI 生成接口用例`
- Position: same column as `导入 Excel` and `导入桌面端项目`

### Input Panel

Fields:

- target project
- target suite name
- Markdown file
- AI provider
- model
- base URL
- API key
- generation prompt hints (optional advanced textarea)

Buttons:

- `生成草稿`
- `清空`

### Preview Panel

Editable table columns:

- `导入`
- `用例名`
- `Method`
- `URL`
- `描述`
- `分类`
- `优先级`
- `请求头`
- `请求体`
- `断言`
- `前置条件`
- `来源片段`
- `校验状态`
- `操作`

Operations:

- edit row
- duplicate row
- delete row
- expand row for source excerpt and validation detail

Editing rules:

- primitive fields use inline input / select
- `headers_json`, `body_json`, `assertions_json`, `metadata_json` use modal JSON editors
- invalid rows are highlighted and cannot be approved until fixed

### Approval Panel

Display:

- total generated rows
- selected rows
- valid rows
- invalid rows
- warnings

Actions:

- `审批并导入`
- `仅导入已选且有效行`

## Backend Design

### New Route Module

Suggested file:

- `backend/app/api/routes/ai_case_drafts.py`

Suggested endpoints:

#### `POST /api/v1/ai-case-drafts/preview`

Purpose:

- upload Markdown and provider config
- generate normalized case drafts
- return preview payload

Request shape:

```json
{
  "project_id": 1,
  "suite_name": "用户中心 API",
  "provider": "openai_compatible",
  "model": "gpt-4.1",
  "base_url": "https://api.example.com/v1",
  "api_key": "runtime only",
  "markdown_text": "# API Docs ...",
  "prompt_hints": "优先生成 smoke + main path + 参数校验 case"
}
```

Response shape:

```json
{
  "draft_batch": {
    "suite_name": "用户中心 API",
    "doc_summary": {
      "section_count": 6,
      "endpoint_count": 4
    },
    "drafts": [
      {
        "draft_id": "uuid",
        "selected": true,
        "validation_status": "valid",
        "validation_errors": [],
        "case": {
          "name": "登录成功",
          "method": "POST",
          "url": "/api/login",
          "description": "正常登录主链路",
          "headers_json": {
            "Content-Type": "application/json"
          },
          "body_json": {
            "username": "demo",
            "password": "demo123"
          },
          "assertions_json": [
            {
              "type": "status_code",
              "operator": "==",
              "expected": 200,
              "enabled": true
            }
          ],
          "metadata_json": {
            "category": "auth",
            "precondition": "",
            "priority": "P1",
            "ai_generated": true
          }
        },
        "source_excerpt": "POST /api/login ...",
        "source_location": {
          "section_title": "1. 登录接口",
          "chunk_index": 0
        }
      }
    ],
    "warnings": []
  }
}
```

#### `POST /api/v1/ai-case-drafts/import`

Purpose:

- accept user-edited drafts
- validate again
- create suite and cases

Request shape:

```json
{
  "project_id": 1,
  "suite_name": "用户中心 API",
  "drafts": [
    {
      "draft_id": "uuid",
      "selected": true,
      "case": {
        "name": "登录成功",
        "method": "POST",
        "url": "/api/login",
        "description": "正常登录主链路",
        "headers_json": {},
        "body_json": {},
        "assertions_json": [],
        "metadata_json": {}
      }
    }
  ]
}
```

Response shape:

```json
{
  "suite_id": 12,
  "suite_name": "用户中心 API",
  "created_cases": 8,
  "skipped_cases": 2,
  "failures": [
    {
      "draft_id": "uuid",
      "reason": "URL is empty."
    }
  ]
}
```

## Service Layout

Suggested services:

- `backend/app/services/markdown_endpoint_parser.py`
- `backend/app/services/llm_case_generation_service.py`
- `backend/app/services/ai_case_draft_service.py`
- `backend/app/services/ai_case_import_service.py`

Responsibilities:

- `markdown_endpoint_parser`
  - split Markdown into manageable endpoint chunks
  - extract headings, methods, paths, example payloads, response blocks
- `llm_case_generation_service`
  - build provider-specific request
  - call LLM
  - enforce JSON-only output contract
- `ai_case_draft_service`
  - orchestrate parsing, generation, normalization, and validation
  - produce preview batch
- `ai_case_import_service`
  - map approved drafts into `ApiCaseCreate`
  - reuse `WorkspaceService` for persistence

## Draft Schema

### Internal Draft Model

```text
AiCaseDraftBatch
  - suite_name: str
  - doc_summary: dict
  - drafts: list[AiCaseDraft]
  - warnings: list[str]

AiCaseDraft
  - draft_id: str
  - selected: bool
  - validation_status: "valid" | "warning" | "invalid"
  - validation_errors: list[str]
  - case: AiCaseDraftPayload
  - source_excerpt: str
  - source_location: dict

AiCaseDraftPayload
  - name: str
  - method: str
  - url: str
  - description: str
  - headers_json: dict[str, str]
  - body_json: Any | None
  - assertions_json: list[dict[str, Any]]
  - metadata_json: dict[str, Any]
```

### Validation Rules

Required:

- `name`
- `method`
- `url`

Normalized defaults:

- `method`: default `GET`
- `headers_json`: default `{}`
- `assertions_json`: default `[]`
- `metadata_json.ai_generated = true`
- `metadata_json.source_type = "markdown_ai"`

Business rules:

- reject empty URL
- method must be one of known HTTP verbs
- headers must stringify to `dict[str, str]`
- assertions must be list of dict
- no row may be imported when `validation_status = invalid`

## LLM Prompt Contract

Model instructions must force:

- JSON-only response
- array of drafts
- no markdown fences
- no commentary
- no invented auth token values unless explicitly documented
- prefer main path, error path, and boundary path cases

Prompt skeleton:

```text
You are generating API test case drafts for an existing test platform.
Return JSON only.
For each documented endpoint, generate a small but useful set of cases.
Each case must follow the provided schema exactly.
Do not invent undocumented fields or response contracts.
If information is missing, leave fields empty and add a warning.
```

## Frontend Design

### Suggested File Layout

- `frontend/src/components/ai/AiCaseGenerationPanel.tsx`
- `frontend/src/components/ai/AiCaseDraftTable.tsx`
- `frontend/src/components/ai/AiJsonEditorModal.tsx`
- `frontend/src/api/services.ts` add preview/import methods
- `frontend/src/api/types.ts` add draft types

### State Shape

```text
generationForm
  - projectId
  - suiteName
  - provider
  - model
  - baseUrl
  - apiKey
  - markdownFile
  - promptHints

draftBatch
  - suiteName
  - drafts[]
  - warnings[]
  - loading
  - importSubmitting
```

### Interaction Rules

- `生成草稿` disabled when project, suite name, file, provider, model, or API key is empty
- preview table shown only after successful generation
- edited content updates local draft state immediately
- invalid JSON editor changes are blocked before save
- import sends only selected rows
- import success clears preview and refreshes workspace list

## Security

- API key is runtime-only and must not be persisted
- audit log should record generation/import action but never include raw API key
- redact provider secrets in error logs
- keep role scope aligned with existing import behavior: `admin` and `tester`

## Observability

Add structured events:

- `ai_case.preview.started`
- `ai_case.preview.completed`
- `ai_case.preview.failed`
- `ai_case.import.started`
- `ai_case.import.completed`
- `ai_case.import.failed`

Suggested fields:

- `project_id`
- `suite_name`
- `provider`
- `model`
- `draft_count`
- `valid_count`
- `invalid_count`
- `failure_reason`

## Failure Handling

Preview-time failures:

- invalid Markdown file encoding
- provider timeout
- invalid JSON returned by model
- schema mismatch
- no endpoint-like content found

Import-time failures:

- project not found
- suite creation failure
- invalid edited draft payload
- partial row failure during batch create

Return partial failure detail per row instead of failing the whole batch when possible.

## Delivery Plan

### Phase 1

- backend preview endpoint
- backend import endpoint
- Markdown parser
- LLM adapter for one provider style
- editable preview table
- import approved drafts

### Phase 2

- richer source excerpt mapping
- duplicate detection warnings
- generation prompt presets
- better JSON editors for headers / body / assertions

### Phase 3

- generation history
- re-run from previous draft batch
- optional export to compatible Excel if still needed

## Recommended Implementation Notes

- Do not extend `ImportService.import_excel` semantics.
- Reuse `WorkspaceService.create_suite` and `WorkspaceService.create_case`.
- Keep the first version synchronous unless generation latency becomes unacceptable.
- Prefer schema-first validation with Pydantic models before any import.

## Open Questions

1. Which AI provider should be the first-class v1 target?
2. Does the product need draft persistence before import, or is in-memory preview enough for v1?
3. Should one Markdown file create one suite only, or optionally split by top-level heading into multiple suites?
