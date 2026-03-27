from __future__ import annotations

import re
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import session_scope
from backend.app.main import create_application
from backend.app.models.ai_chat_message import AiChatMessage
from backend.app.models.ai_chat_session import AiChatSession
from backend.app.models.audit_log import AuditLog
from backend.app.models.base import Base
from backend.app.models.registry import load_model_metadata
from backend.app.models.user import UserRole
from backend.app.services.auth_service import AuthService


def _mock_chat_stream(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reply_text: str = "这是 AI 回复。",
    session_title: str = "自由问答说明",
) -> None:
    monkeypatch.setattr(
        "backend.app.services.ai_provider_registry.AiProviderRegistry.resolve_runtime",
        lambda self: object(),
    )
    monkeypatch.setattr(
        "backend.app.services.ai_client_service.AiClientService.stream_text",
        lambda self, **kwargs: (iter([]), {"call_mode": "llm", "failure_category": "", "trace_json": {"request_id": "chat-history-trace"}}),
    )

    def _generate_text(self, **kwargs):
        system_prompt = kwargs.get("system_prompt", "")
        if "You generate concise chat session titles." in system_prompt:
            return session_title, {
                "call_mode": "llm",
                "failure_category": "",
                "trace_json": {"request_id": "chat-title-trace"},
            }
        return reply_text, {
            "call_mode": "llm",
            "failure_category": "",
            "trace_json": {"request_id": "chat-history-fallback"},
        }

    monkeypatch.setattr("backend.app.services.ai_client_service.AiClientService.generate_text", _generate_text)


def _build_api_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, sessionmaker]:
    load_model_metadata()
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    monkeypatch.setattr("backend.app.main.bootstrap_database", lambda: None)
    monkeypatch.setattr("backend.app.main.SessionLocal", testing_session_local)

    app = create_application()

    def override_session_scope() -> Generator[Session, None, None]:
        session = testing_session_local()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[session_scope] = override_session_scope
    client = TestClient(app)
    return client, testing_session_local


def _issue_token(factory: sessionmaker, username: str) -> str:
    with factory() as session:
        auth_service = AuthService(session)
        user = auth_service.create_user(username, username, "Tester#ChatHistory2026", UserRole.tester)
        session.commit()
        auth_session = auth_service.build_session(user)
        session.commit()
        return auth_session.access_token


def _extract_session_id(body: str) -> int:
    match = re.search(r'"session_id":\s*(\d+)', body)
    assert match is not None
    return int(match.group(1))


def test_ai_chat_history_persists_and_is_user_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_chat_stream(monkeypatch, session_title="自由模式能力边界")
    client, factory = _build_api_client(monkeypatch)
    token_alice = _issue_token(factory, "alice")
    token_bob = _issue_token(factory, "bob")

    with client.stream(
        "POST",
        "/api/v1/ai-copilot/chat/stream",
        json={
            "chat_mode": "free",
            "page_path": "/workspace",
            "page_title": "工作台",
            "messages": [{"role": "user", "content": "你是谁，可以帮我做什么，我可以问除了测试之外的工作吗"}],
        },
        headers={"Authorization": f"Bearer {token_alice}"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    session_id = _extract_session_id(body)

    with client.stream(
        "POST",
        "/api/v1/ai-copilot/chat/stream",
        json={
            "session_id": session_id,
            "chat_mode": "free",
            "page_path": "/workspace",
            "page_title": "工作台",
            "messages": [
                {"role": "user", "content": "你是谁，可以帮我做什么，我可以问除了测试之外的工作吗"},
                {"role": "assistant", "content": "这是 AI 回复。"},
                {"role": "user", "content": "那你帮我列个会议纪要模板"},
            ],
        },
        headers={"Authorization": f"Bearer {token_alice}"},
    ) as second_response:
        second_body = "".join(second_response.iter_text())

    assert second_response.status_code == 200
    assert f'"session_id": {session_id}' in second_body

    alice_headers = {"Authorization": f"Bearer {token_alice}"}
    bob_headers = {"Authorization": f"Bearer {token_bob}"}

    with client:
        list_response = client.get("/api/v1/ai-copilot/chat/sessions", headers=alice_headers)
        detail_response = client.get(f"/api/v1/ai-copilot/chat/sessions/{session_id}", headers=alice_headers)
        bob_list_response = client.get("/api/v1/ai-copilot/chat/sessions", headers=bob_headers)
        bob_detail_response = client.get(f"/api/v1/ai-copilot/chat/sessions/{session_id}", headers=bob_headers)

    assert list_response.status_code == 200
    list_payload = list_response.json()["data"]["items"]
    assert len(list_payload) == 1
    assert list_payload[0]["session_id"] == session_id
    assert list_payload[0]["title"] == "自由模式能力边界"
    assert list_payload[0]["message_count"] == 4

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()["data"]
    assert detail_payload["title"] == "自由模式能力边界"
    assert [item["role"] for item in detail_payload["messages"]] == ["user", "assistant", "user", "assistant"]
    assert detail_payload["messages"][-1]["content"] == "这是 AI 回复。"

    assert bob_list_response.status_code == 200
    assert bob_list_response.json()["data"]["items"] == []
    assert bob_detail_response.status_code == 404

    with factory() as session:
        stored_session = session.query(AiChatSession).filter(AiChatSession.id == session_id).one()
        stored_messages = session.query(AiChatMessage).filter(AiChatMessage.session_id == session_id).order_by(AiChatMessage.order_index.asc()).all()
        assert stored_session.title == "自由模式能力边界"
        assert stored_session.message_count == 4
        assert [item.role for item in stored_messages] == ["user", "assistant", "user", "assistant"]


def test_ai_chat_history_delete_is_physical_and_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_chat_stream(monkeypatch)
    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "charlie")
    headers = {"Authorization": f"Bearer {token}"}

    with client.stream(
        "POST",
        "/api/v1/ai-copilot/chat/stream",
        json={
            "chat_mode": "free",
            "page_path": "/workspace",
            "page_title": "工作台",
            "messages": [{"role": "user", "content": "删除我"}],
        },
        headers=headers,
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    session_id = _extract_session_id(body)

    with client:
        delete_response = client.delete(f"/api/v1/ai-copilot/chat/sessions/{session_id}", headers=headers)

    assert delete_response.status_code == 200

    with factory() as session:
        assert session.query(AiChatSession).filter(AiChatSession.id == session_id).count() == 0
        assert session.query(AiChatMessage).filter(AiChatMessage.session_id == session_id).count() == 0
        latest_log = session.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert latest_log is not None
        assert latest_log.action == "ai_chat.delete"
        assert latest_log.resource_type == "ai_chat_session"
        assert latest_log.resource_id == str(session_id)
        assert latest_log.details_json["session_id"] == session_id


def test_ai_chat_stream_retries_empty_model_response_until_content_arrives(monkeypatch: pytest.MonkeyPatch) -> None:
    call_counter = {"stream": 0, "reply_generate": 0, "title_generate": 0}

    monkeypatch.setattr(
        "backend.app.services.ai_provider_registry.AiProviderRegistry.resolve_runtime",
        lambda self: object(),
    )

    def _stream_text(self, **kwargs):
        call_counter["stream"] += 1
        return iter([]), {"call_mode": "llm", "failure_category": "", "trace_json": {"request_id": f"stream-{call_counter['stream']}"}}

    def _generate_text(self, **kwargs):
        system_prompt = kwargs.get("system_prompt", "")
        if "You generate concise chat session titles." in system_prompt:
            call_counter["title_generate"] += 1
            return "重试成功摘要", {
                "call_mode": "llm",
                "failure_category": "",
                "trace_json": {"request_id": "title-success"},
            }

        call_counter["reply_generate"] += 1
        if call_counter["reply_generate"] < 4:
            return "", {"call_mode": "llm", "failure_category": "", "trace_json": {"request_id": f"fallback-{call_counter['reply_generate']}"}}
        return "第 4 次重试拿到内容。", {
            "call_mode": "llm",
            "failure_category": "",
            "trace_json": {"request_id": f"fallback-{call_counter['reply_generate']}"},
        }

    monkeypatch.setattr("backend.app.services.ai_client_service.AiClientService.stream_text", _stream_text)
    monkeypatch.setattr("backend.app.services.ai_client_service.AiClientService.generate_text", _generate_text)

    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "retry-success")

    with client.stream(
        "POST",
        "/api/v1/ai-copilot/chat/stream",
        json={
            "chat_mode": "free",
            "page_path": "/workspace",
            "page_title": "工作台",
            "messages": [{"role": "user", "content": "测试重试成功"}],
        },
        headers={"Authorization": f"Bearer {token}"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "第 4 次重试拿到内容。" in body
    assert "当前模型未返回可展示内容。" not in body
    assert call_counter["stream"] == 4
    assert call_counter["reply_generate"] == 4
    assert call_counter["title_generate"] == 1


def test_ai_chat_stream_returns_fallback_after_three_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    call_counter = {"stream": 0, "reply_generate": 0, "title_generate": 0}

    monkeypatch.setattr(
        "backend.app.services.ai_provider_registry.AiProviderRegistry.resolve_runtime",
        lambda self: object(),
    )

    def _stream_text(self, **kwargs):
        call_counter["stream"] += 1
        return iter([]), {"call_mode": "llm", "failure_category": "", "trace_json": {"request_id": f"stream-{call_counter['stream']}"}}

    def _generate_text(self, **kwargs):
        system_prompt = kwargs.get("system_prompt", "")
        if "You generate concise chat session titles." in system_prompt:
            call_counter["title_generate"] += 1
            return "重试兜底摘要", {
                "call_mode": "llm",
                "failure_category": "",
                "trace_json": {"request_id": "title-fallback"},
            }

        call_counter["reply_generate"] += 1
        return "", {"call_mode": "llm", "failure_category": "", "trace_json": {"request_id": f"fallback-{call_counter['reply_generate']}"}}

    monkeypatch.setattr("backend.app.services.ai_client_service.AiClientService.stream_text", _stream_text)
    monkeypatch.setattr("backend.app.services.ai_client_service.AiClientService.generate_text", _generate_text)

    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "retry-fallback")

    with client.stream(
        "POST",
        "/api/v1/ai-copilot/chat/stream",
        json={
            "chat_mode": "free",
            "page_path": "/workspace",
            "page_title": "工作台",
            "messages": [{"role": "user", "content": "测试重试兜底"}],
        },
        headers={"Authorization": f"Bearer {token}"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "当前模型未返回可展示内容。" in body
    assert call_counter["stream"] == 4
    assert call_counter["reply_generate"] == 4
    assert call_counter["title_generate"] == 1
