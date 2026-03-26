from __future__ import annotations

from backend.app.services.ai_chat_service import AiChatService


class _DummyContextService:
    pass


class _DummyHistoryService:
    pass


def _build_service() -> AiChatService:
    return AiChatService(
        context_service=_DummyContextService(),
        history_service=_DummyHistoryService(),
    )


def test_build_user_prompt_prioritizes_execution_page_context() -> None:
    service = _build_service()

    prompt = service._build_user_prompt(
        chat_mode="project",
        page_path="/executions/42",
        page_title="执行",
        latest_user_message="最近失败集中在哪里？",
        snapshot={
            "summary": "Project has recent execution failures.",
            "recent_executions": [
                {
                    "id": 42,
                    "status": "failed",
                    "scope": "suite",
                    "target_name": "Smoke Suite",
                    "error_message": "timeout",
                }
            ],
            "recent_reports": [
                {
                    "id": 7,
                    "report_type": "html",
                    "execution_id": 42,
                    "execution_target": "Smoke Suite",
                }
            ],
            "cases": [
                {
                    "id": 9,
                    "suite_name": "Smoke Suite",
                    "method": "GET",
                    "url": "/health",
                    "name": "Health check",
                }
            ],
        },
    )

    assert "Page focus: Executions" in prompt
    assert "Prioritize execution diagnosis" in prompt
    assert "project snapshot is available" in prompt
    assert "- recent_executions:" in prompt
    assert "- recent_reports:" in prompt
    assert "execution #42 status=failed" in prompt


def test_build_user_prompt_keeps_free_mode_boundary_on_execution_page() -> None:
    service = _build_service()

    prompt = service._build_user_prompt(
        chat_mode="free",
        page_path="/executions",
        page_title="执行",
        latest_user_message="帮我分析一下执行页应该怎么看",
        snapshot={
            "summary": "This snapshot should not be used in free mode.",
            "recent_executions": [
                {
                    "id": 99,
                    "status": "failed",
                    "scope": "suite",
                    "target_name": "Hidden Suite",
                    "error_message": "should not leak",
                }
            ],
        },
    )

    assert "Page focus: Executions" in prompt
    assert "free chat mode still applies" in prompt
    assert "free chat mode has no bound project snapshot for the current page" in prompt
    assert "execution #99" not in prompt
