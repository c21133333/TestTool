from assertions import AssertionEngine


def test_status_code_pass_fail():
    engine = AssertionEngine()
    result = engine.run_assertions({"status_code": 200}, [{"type": "status_code", "expected": 200}])
    assert result[0]["result"] == "PASS"

    result = engine.run_assertions({"status_code": 500}, [{"type": "status_code", "expected": 200}])
    assert result[0]["result"] == "FAIL"
    assert result[0]["actual"] == 500


def test_json_path_equals_and_not_null():
    engine = AssertionEngine()
    response = {"response_json": {"data": {"id": 1, "name": "demo"}}}
    assertions = [
        {"type": "json_path", "path": "$.data.id", "operator": "equals", "expected": 1},
        {"type": "json_path", "path": "$.data.name", "operator": "not_null"},
    ]
    results = engine.run_assertions(response, assertions)
    assert results[0]["result"] == "PASS"
    assert results[1]["result"] == "PASS"


def test_json_path_missing_fail():
    engine = AssertionEngine()
    response = {"response_json": {"data": {}}}
    results = engine.run_assertions(
        response,
        [{"type": "json_path", "path": "$.data.missing", "operator": "equals", "expected": 1}],
    )
    assert results[0]["result"] == "FAIL"
