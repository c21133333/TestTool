# Legacy Compatibility Retirement

## Goal

Make the remaining desktop-era compatibility surface explicit, temporary, and removable.

`v1` keeps several legacy import paths only as a migration bridge:

- Excel import with historical column aliases
- Desktop `project.json` import
- Desktop `runsIndex` / HTML / JSON historical run import

These capabilities are not part of the long-term product model.

## Current Policy

- Compatibility mode: `migration_bridge`
- Source of truth: database-backed Web APIs and Web UI
- Allowed operator scope: `admin` and `tester`
- Default state: enabled, but marked as migration-only
- Runtime kill switch: `EAZYTEST_LEGACY_IMPORTS_ENABLED`
- Planned retirement date: `EAZYTEST_LEGACY_IMPORTS_SUNSET_DATE` if configured

When legacy imports are disabled, the backend returns `410 Gone` for migration import routes.

## Frozen Scope

The following rules now apply:

1. No new fields, aliases, or write-back behavior may be added for `project.json`.
2. No new semantics may be added for historical Excel templates.
3. Legacy formats remain read-only migration inputs.
4. All new authoring, editing, execution, and reporting features must target the Web data model only.

## Capability Inventory

| Capability | Status | Purpose | Removal trigger |
| --- | --- | --- | --- |
| Excel import | migration-only | Seed suites/cases from historical spreadsheets | No active spreadsheet migration remains |
| Desktop `project.json` import | migration-only | Seed suites/cases/environments/history from desktop exports | No active desktop migration remains |
| Desktop run/report import | migration-only | Backfill historical executions and reports | Historical backfill completed |
| Legacy import-path wrapper | remove-when-unused | Preserve refactor-time import compatibility | No internal code imports remain |

## Recommended Operating Model

- Keep migration imports enabled only in environments that are still onboarding legacy assets.
- Set `EAZYTEST_LEGACY_IMPORTS_SUNSET_DATE` before entering the final migration window.
- Disable imports by config first.
- Remove code and tests in a later `v1.x` cleanup only after the disabled state has run cleanly.

## Exit Criteria

- Team members agree that legacy imports are a migration bridge, not a product feature.
- No production workflow depends on desktop file formats.
- New requirements are rejected if they extend desktop-era schemas.
- Legacy imports can be disabled without blocking day-to-day Web usage.
