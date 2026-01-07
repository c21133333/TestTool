from requesttool.workers import ApiRequestWorker


def test_worker_emits_finished(monkeypatch):
    def fake_send_request(_params):
        return {"success": True}

    class FakeEngine:
        def run_assertions(self, _response, _assertions):
            return [{"result": "PASS"}]

    monkeypatch.setattr("requesttool.workers.http_client.send_request", fake_send_request)
    monkeypatch.setattr("requesttool.workers.AssertionEngine", FakeEngine)

    payloads = []
    worker = ApiRequestWorker({"method": "GET", "url": "http://x"}, [])
    worker.finished.connect(lambda payload: payloads.append(payload))
    worker.run()

    assert payloads
    assert payloads[0]["response"]["success"] is True
