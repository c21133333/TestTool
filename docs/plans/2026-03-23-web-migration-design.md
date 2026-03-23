# Eazy Test Web Migration Design

## Goal

Migrate the legacy `PySide6` desktop client into a multi-user web platform based on:

- FastAPI backend
- React + TypeScript frontend
- SQLAlchemy persistence
- Background suite execution
- Role-based access control

## Phase Strategy

1. Build the new backend and frontend skeleton in-place.
2. Reuse the existing request execution and assertion core through backend services.
3. Move project, suite, case, environment, execution, and report state into database-backed models.
4. Replace desktop-only workflows with HTTP APIs and a browser UI.
5. Retire the desktop shell after the web flow reaches parity.

## Backend Modules

- `backend/app/api`: REST routes and auth dependencies
- `backend/app/core`: settings, database, security, generic API response
- `backend/app/models`: SQLAlchemy models for users, tokens, workspace entities, executions, reports
- `backend/app/repositories`: thin persistence access layer
- `backend/app/services`: auth, workspace, execution, import, report orchestration
- `backend/app/testing`: adapter layer reusing the existing execution engine

## Frontend Modules

- `frontend/src/api`: typed API client and service wrappers
- `frontend/src/auth`: auth state and local token persistence
- `frontend/src/components/shell`: main navigation shell
- `frontend/src/pages`: overview, workspace, environments, executions, reports, users

## Data Model

- `users`
- `access_tokens`
- `projects`
- `suites`
- `api_cases`
- `environments`
- `executions`
- `execution_items`
- `reports`

## Current Scope Delivered

- Login and bootstrap admin flow
- Project / suite / case / environment CRUD APIs
- Single case execution
- Queue-backed suite execution processed by a standalone worker
- HTML and JSON report generation
- Excel import endpoint
- React shell with core management pages
- JSON editors for case assertions, headers, body, metadata, and processors
- Environment JSON editors for headers and variables
- Online report preview through authenticated report content endpoints
- Execution control panel with polling, cancel, retry, and detail drawer

## Next Work

1. Add update/delete APIs and richer editors for headers, assertions, and processors.
2. Move execution off in-process background tasks into a dedicated worker.
3. Add audit logging and permission-aware frontend guards.
4. Build a richer report viewer instead of exposing file paths only.
5. Decommission desktop-specific persistence and packaging paths.
