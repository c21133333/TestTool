# Eazy Test Desktop Decommission Plan

## Goal

Retire the `PySide6` desktop client without losing the existing execution core, import flow, or report output quality.

## What Was Completed In This Refactor Slice

- Moved report generation into `requesttool.shared.reporting`.
- Moved the shared assertion engine into `requesttool.shared.assertions`.
- Updated the web backend to depend on shared modules instead of `requesttool.app.core`.
- Removed the desktop runtime, Qt UI, installer chain, and desktop-only tests.
- Removed repo-embedded desktop sample data, bundled Node runtime, and other non-product assets.

## Current Remaining Legacy Couplings

### 1. Legacy import formats

- uploaded `project.json`
- uploaded desktop run-report files referenced by `runsIndex`
- uploaded Excel sheets with historical column aliases

These are migration inputs only. They should remain supported only as long as desktop-to-web migration is still active.

### 2. Legacy compatibility wrapper

- `src/requesttool/app/core/report_generator.py`

This wrapper still exists to preserve the import path during refactor history, but the real implementation already lives in `requesttool.shared.reporting`.

### 3. Local runtime data

- `web_eazytest.db`
- `web_runs/`

These are valid web runtime artifacts, but they should stay out of version control.

## Recommended Decommission Order

### Phase 1: Retire migration shims

- Remove `requesttool.app.core.report_generator` once no internal code imports it.
- Keep shared logic only under `requesttool.shared`.

### Phase 2: Eliminate migration-only file formats

- Stop extending `project.json` and legacy Excel semantics.
- Keep migration support read-only.
- Route all authoring and execution history through database-backed web APIs only.

### Phase 3: Productize repository boundaries

- Confirm web covers case editing, processors, assertions, import, execution, cancel/retry, reports, users, audit logs.
- Keep sample data, ad-hoc exports, and runtime outputs out of the repo root.
- Require system Node or explicit `REQUESTTOOL_NODE_BIN` instead of bundling binaries in-repo.

### Phase 4: Shrink migration surface

- Decide an end date for legacy `project.json` / Excel import support.
- After that date, delete the legacy import code and related tests.

## Exit Criteria

- No production workflow requires desktop files or bundled binaries.
- No active workflow writes legacy root files such as `project.json`, `requests.json`, or `runs/`.
- Runtime outputs stay ignored and out of version control.
- Legacy imports are explicitly migration-only, not a primary data model.
