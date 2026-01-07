from requesttool.result_summary import build_summary


def test_build_summary():
    cases = [
        {"result": "PASS"},
        {"result": "FAIL"},
        {"result": "PASS"},
    ]
    summary = build_summary(cases)
    assert summary == {"total": 3, "pass": 2, "fail": 1}
