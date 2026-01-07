from requesttool.batch_executor import BatchExecutor


class _HttpClient:
    def __init__(self, responses) -> None:
        self._responses = list(responses)

    def send_request(self, _request):
        return self._responses.pop(0)


class _AssertionEngine:
    def __init__(self, results) -> None:
        self._results = list(results)

    def run_assertions(self, _response, _assertions):
        return self._results.pop(0)


def test_batch_executor_results():
    responses = [
        {"success": True},
        {"success": True},
        {"success": False},
    ]
    assertion_results = [
        [{"result": "PASS"}],
        [{"result": "FAIL"}],
        [{"result": "PASS"}],
    ]
    executor = BatchExecutor(_HttpClient(responses), _AssertionEngine(assertion_results))
    cases = [
        {"case_id": "1", "name": "a", "request": {}, "assertions": []},
        {"case_id": "2", "name": "b", "request": {}, "assertions": []},
        {"case_id": "3", "name": "c", "request": {}, "assertions": []},
    ]
    results = executor.run_cases(cases)
    assert results[0]["result"] == "PASS"
    assert results[1]["result"] == "FAIL"
    assert results[2]["result"] == "FAIL"
