# Suite Shared Variables Design

## Goal

Enable one case in a suite execution to extract values from its response and make those values available to later cases in the same suite run.

## Constraints

- Keep the existing case schema and API contract unchanged.
- Reuse the current `{{variable}}` request templating and processor model.
- Scope the feature to a single suite execution only.
- Do not mutate stored case definitions or environment data.

## Design

The implementation keeps two layers of variable handling:

1. Case-local runtime variables still live inside `requesttool.processor_engine`.
2. Suite-level shared variables live only inside `ExecutionService.process_execution`.

Each case starts with merged variables:

- environment variables
- latest suite shared variables

During request execution, existing processors may update runtime variables through `set_variable`, `jsonpath_extract`, `regex_extract`, or `script`. After post-processors complete, the runtime writes the final variable snapshot into `response.runtime_variables`.

The suite executor reads that snapshot after each case completes and replaces the shared variable pool with the latest values. The next case therefore receives the extracted values through the existing `request.variables` path, and request templating resolves them with no new syntax.

## Trade-offs

- This is intentionally execution-scoped, not persisted. It avoids schema churn and side effects.
- The latest case snapshot replaces the previous shared state, which keeps deletion semantics straightforward for script processors.
- Runtime variables are now visible in execution response payloads for debugging, which is useful but should remain limited to execution data only.

## Verification

- Added an execution test that runs a two-case suite:
  - case A extracts `authToken` from response JSON
  - case B uses `Bearer {{authToken}}` in request headers
- Re-ran the full `tests/test_web_services.py` suite.
