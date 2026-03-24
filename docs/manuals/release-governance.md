# Release Governance

## Goal

Make each release repeatable, reviewable, and reversible.

The minimum release gate for `v1` is:

1. `python -m pytest`
2. `frontend: npm run build`
3. API startup smoke
4. Worker startup smoke

These checks now run in CI and should also be the local pre-release checklist.

## Versioning Strategy

Use `v1.x.y` tags:

- `x`: minor release, allowed for additive features or visible operational improvements
- `y`: patch release, bug fix or low-risk governance change

Rules:

- Database migrations require explicit release notes and rollback notes.
- Configuration changes must be listed under "Operator action required".
- Legacy-compatibility removals must be called out as breaking changes for migration users.

## Release Checklist

1. Confirm CI is green on the release commit.
2. Confirm the target environment config is complete.
3. Review database migration impact.
4. Review permissions, import policy, and rollout notes.
5. Build deployment artifacts.
6. Publish release notes using the repository release template.
7. Deploy API and worker together.
8. Run post-deploy health checks:
   - `GET /api/v1/health`
   - login
   - one execution smoke
   - one report preview

## Rollback Strategy

Rollback order:

1. Stop new traffic to the current release.
2. Roll API and worker back to the previous release together.
3. If a database migration is not backward compatible, use the prepared Alembic rollback path before restoring traffic.
4. Re-run health checks.

Never release a migration without knowing whether it is:

- backward compatible
- reversible
- safe for rolling deployment

## Release Artifacts

Each release should have:

- git tag
- release notes
- operator checklist
- rollback notes
- linked CI run

## Scope Of This Baseline

This is the minimum governance baseline for `v1`, not a full CD platform.
It intentionally stops at:

- CI validation
- release documentation
- repeatable manual deployment gates

Fully automated production deploys can be added later, after the deployment topology is stable.
