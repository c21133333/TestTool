from requesttool.batch_thread_executor import BatchThreadExecutor


class _HttpClient:
    def send_request(self, _request):
        return {"success": True}


class _AssertionEngine:
    def run_assertions(self, _response, _assertions):
        return [{"result": "PASS"}]


def test_batch_thread_executor_run_cases():
    executor = BatchThreadExecutor(_HttpClient(), _AssertionEngine(), max_workers=2)
    cases = [
        {"case_id": "1", "name": "a", "request": {}, "assertions": []},
        {"case_id": "2", "name": "b", "request": {}, "assertions": []},
    ]
    results = executor.run_cases(cases)
    assert len(results) == 2
    assert all(item["result"] == "PASS" for item in results)
