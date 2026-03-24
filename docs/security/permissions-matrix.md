# Security Baseline Matrix

## Token lifecycle

- Access token TTL is fixed by `EAZYTEST_AUTH_TOKEN_TTL_HOURS` and returned to clients as `issued_at`, `expires_at`, and `expires_in_seconds`.
- `logout` revokes the current token immediately.
- A user keeps at most `EAZYTEST_AUTH_MAX_ACTIVE_TOKENS_PER_USER` live tokens. New logins revoke the oldest active tokens first.
- Disabling a user revokes all live tokens for that user immediately.

## Account state rules

- Only `admin` can create users or change user active state.
- `admin` cannot disable their own account.
- The last active `admin` cannot be disabled.
- Disabled users cannot log in and cannot use previously issued tokens.
- New passwords must satisfy the configured strength policy and cannot match the built-in weak-password denylist.

## Permission matrix

| Capability | admin | tester | developer |
| --- | --- | --- | --- |
| View projects / suites / cases / environments | Yes | Yes | Yes |
| Change projects / suites / cases / environments | Yes | Yes | No |
| Run / cancel / retry executions | Yes | Yes | No |
| View executions / reports | Yes | Yes | Yes |
| Import Excel / legacy project data | Yes | Yes | No |
| List users / create users / enable-disable users | Yes | No | No |
| View audit logs | Yes | No | No |

## Production guardrail

- `EAZYTEST_BOOTSTRAP_ADMIN_ENABLED=true` is rejected when `EAZYTEST_DEPLOYMENT_ENV=production`.
- Production initialization must provision the first administrator explicitly instead of relying on startup bootstrap behavior.
