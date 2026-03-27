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
        page_title="Executions",
        latest_user_message="Where are the recent failures concentrated?",
        snapshot={
            "summary": "Project has recent execution failures.",
            "product_knowledge": {
                "summary": "Eazy Test Web is a web-first API testing platform.",
                "workflow": ["Project -> Suite -> Case -> Environment -> Execution -> Report -> Review"],
                "page_guides": {
                    "executions": {
                        "purpose": "Run cases or suites and diagnose execution outcomes.",
                        "capabilities": [
                            "Trigger case immediate execution.",
                            "Queue suite execution for worker consumption.",
                        ],
                        "ai_capabilities": [
                            "AI diagnosis helps with first-pass failure triage.",
                        ],
                    }
                },
                "ai_operating_model": {
                    "summary": "AI is copilot, not autopilot.",
                    "rules": ["AI suggests, supplements, diagnoses, and summarizes."],
                },
                "known_limits": ["AI mock support is not a complete runtime mock platform."],
                "role_boundaries": ["developer is mainly read-only for workspace, executions, and reports."],
            },
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
    assert "Product knowledge relevant to current page:" in prompt
    assert "page_purpose: Run cases or suites and diagnose execution outcomes." in prompt
    assert "AI is copilot, not autopilot." in prompt
    assert "project snapshot is available" in prompt
    assert "- recent_executions:" in prompt
    assert "- recent_reports:" in prompt
    assert "execution #42 status=failed" in prompt


def test_build_user_prompt_keeps_free_mode_boundary_on_execution_page() -> None:
    service = _build_service()

    prompt = service._build_user_prompt(
        chat_mode="free",
        page_path="/executions",
        page_title="Executions",
        latest_user_message="Help me analyze what this execution page is for.",
        snapshot={
            "summary": "This snapshot should not be used in free mode.",
            "product_knowledge": {
                "summary": "Should stay out of free chat.",
                "workflow": ["Project -> Suite -> Case -> Environment -> Execution -> Report -> Review"],
                "page_guides": {
                    "executions": {
                        "purpose": "Should not appear in free chat.",
                        "capabilities": ["Should not appear in free chat."],
                        "ai_capabilities": ["Should not appear in free chat."],
                    }
                },
            },
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
    assert "Product knowledge relevant to current page:" not in prompt
    assert "Should stay out of free chat." not in prompt
    assert "execution #99" not in prompt
