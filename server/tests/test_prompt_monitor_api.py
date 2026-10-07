import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.routes import chat as chat_route, monitor as monitor_route, prompt as prompt_route
from app.core.database import Base
from app.main import app
from app.models.monitoring import ModelCall, PromptTemplate
from app.services import monitoring as monitoring_service


@pytest.fixture
def db_sessions(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'prompt-monitor.db'}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup())
    monkeypatch.setattr(prompt_route, "SessionFactory", sessions)
    monkeypatch.setattr(chat_route, "SessionFactory", sessions)
    monkeypatch.setattr(monitor_route, "SessionFactory", sessions)
    monkeypatch.setattr(monitoring_service, "SessionFactory", sessions)
    try:
        yield sessions
    finally:
        asyncio.run(engine.dispose())


def test_template_crud_builtin_protection_and_version_limit(db_sessions):
    with TestClient(app) as client:
        listed = client.get("/api/prompt/templates")
        assert listed.status_code == 200
        builtins = listed.json()["templates"]
        assert len([item for item in builtins if item["id"].startswith("t_default_")]) == 3
        builtin_id = builtins[0]["id"]
        assert client.delete(f"/api/prompt/templates/{builtin_id}").status_code == 403

        created = client.post("/api/prompt/templates", json={"name": "测试", "systemPrompt": "v1"})
        assert created.status_code == 200
        template_id = created.json()["template"]["id"]
        assert created.json()["template"]["versions"][0]["version"] == 1

        for version in range(2, 13):
            updated = client.put(
                f"/api/prompt/templates/{template_id}",
                json={"name": "测试", "systemPrompt": f"v{version}"},
            )
            assert updated.status_code == 200
        saved = updated.json()["template"]
        assert len(saved["versions"]) == 10
        assert saved["versions"][-1]["version"] == 12
        assert saved["systemPrompt"] == "v12"
        assert client.delete(f"/api/prompt/templates/{template_id}").status_code == 200


def test_ab_test_runs_two_answers_and_uses_overall_score(db_sessions, monkeypatch):
    async def fake_call(messages, **kwargs):
        text = messages[0]["content"] if messages[0]["role"] == "system" else messages[-1]["content"]
        if "System A" in text:
            return "Answer A", 10, 5, 12
        if "System B" in text:
            return "Answer B", 10, 5, 14
        raise AssertionError("Only answer generation is expected")

    async def fake_score(question, answer, label):
        return {"relevance": 4, "accuracy": 4, "clarity": 4, "conciseness": 4,
                "overall": 5 if answer == "Answer A" else 3, "reason": f"{label} reason"}

    monkeypatch.setattr(prompt_route, "_call_model", fake_call)
    monkeypatch.setattr(prompt_route, "_score_answer", fake_score)
    with TestClient(app) as client:
        response = client.post("/api/prompt/ab-test", json={
            "question": "question", "systemPromptA": "System A", "systemPromptB": "System B",
        })
    assert response.status_code == 200
    result = response.json()
    assert result["answerA"] == "Answer A"
    assert result["evaluation"]["winner"] == "A"
    assert "A 综合分 5/5" in result["evaluation"]["reason"]


def test_ab_test_tie_when_overall_scores_match(db_sessions, monkeypatch):
    async def fake_call(messages, **kwargs):
        return messages[0]["content"], 1, 1, 5

    async def fake_score(question, answer, label):
        return {"relevance": 3, "accuracy": 3, "clarity": 3, "conciseness": 3,
                "overall": 3, "reason": "相当"}

    monkeypatch.setattr(prompt_route, "_call_model", fake_call)
    monkeypatch.setattr(prompt_route, "_score_answer", fake_score)
    with TestClient(app) as client:
        response = client.post("/api/prompt/ab-test", json={"question": "Q"})
    assert response.status_code == 200
    assert response.json()["evaluation"]["winner"] == "tie"


def test_monitor_stats_budget_percentiles_and_retention(db_sessions):
    now = datetime.now(timezone.utc)
    async def seed():
        async with db_sessions() as session:
            session.add_all([
                ModelCall(feature="chat", model="m", input_tokens=100, output_tokens=50, latency_ms=100, created_at=now),
                ModelCall(feature="agent", model="m", input_tokens=200, output_tokens=100, latency_ms=300, created_at=now - timedelta(minutes=1)),
                ModelCall(feature="prompt", model="m", input_tokens=None, output_tokens=None, latency_ms=200, created_at=now - timedelta(minutes=2)),
                ModelCall(feature="workflow", model="m", input_tokens=None, output_tokens=None, latency_ms=500, success=False, created_at=now - timedelta(minutes=3)),
                ModelCall(feature="chat", model="m", input_tokens=999, output_tokens=999, latency_ms=999, created_at=now - timedelta(days=91)),
            ])
            await session.commit()
    asyncio.run(seed())

    with TestClient(app) as client:
        response = client.get("/api/monitor/stats")
        assert response.status_code == 200
        stats = response.json()
        assert stats["overview"]["apiCallsToday"] == 4
        assert stats["overview"]["successfulCallsToday"] == 3
        assert stats["overview"]["failedCallsToday"] == 1
        assert stats["overview"]["inputTokensToday"] == 300
        assert stats["overview"]["outputTokensToday"] == 150
        assert stats["overview"]["unknownUsageToday"] == 1
        assert stats["overview"]["dailyBudgetTokens"] == 1_000_000
        assert stats["latency"] == {"avg": 200, "p50": 200, "p90": 300, "p99": 300}
        assert len(stats["last7Days"]) == 7
        assert {item["feature"] for item in stats["byFeature"]} == {"chat", "agent", "prompt", "workflow"}
        assert stats["recentCalls"][0]["inputT"] == 100
        updated = client.put("/api/monitor/budget", json={"dailyBudgetTokens": 500})
        assert updated.status_code == 200
        assert client.get("/api/monitor/stats").json()["overview"]["dailyBudgetTokens"] == 500

    async def check_expired_removed():
        async with db_sessions() as session:
            rows = (await session.execute(select(ModelCall))).scalars().all()
            return len(rows)
    assert asyncio.run(check_expired_removed()) == 4


def test_invalid_prompt_parameters_are_rejected():
    with TestClient(app) as client:
        temperature = client.post("/api/prompt/test/stream", json={"userMessage": "hi", "temperature": 2.1})
        max_tokens = client.post("/api/prompt/test/stream", json={"userMessage": "hi", "maxTokens": 4097})
    assert temperature.status_code == 422
    assert max_tokens.status_code == 422


def test_prompt_stream_returns_usage_and_persists_completed_call(db_sessions, monkeypatch):
    class FakeResponse:
        is_error = False

        async def aread(self):
            return b""

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"hello"}}]}'
            yield 'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":2}}'
            yield "data: [DONE]"

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *_args):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return FakeStream()

    monkeypatch.setattr(prompt_route.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(prompt_route.settings, "deepseek_api_key", "test-key")
    with TestClient(app) as client:
        response = client.post("/api/prompt/test/stream", json={"userMessage": "hello"})
    assert response.status_code == 200
    assert 'event: token\ndata: {"token":"hello"}' in response.text
    assert '"inputTokens":7' in response.text
    assert '"outputTokens":2' in response.text

    async def read_calls():
        async with db_sessions() as session:
            return (await session.execute(select(ModelCall))).scalars().all()

    calls = asyncio.run(read_calls())
    assert len(calls) == 1
    assert (calls[0].feature, calls[0].input_tokens, calls[0].output_tokens) == ("prompt", 7, 2)


def test_chat_stream_usage_is_recorded_and_missing_usage_stays_unknown(db_sessions, monkeypatch):
    class FakeResponse:
        is_error = False

        async def aread(self):
            return b""

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"ok"}}]}'
            yield "data: [DONE]"

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *_args):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return FakeStream()

    monkeypatch.setattr(chat_route.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(chat_route.settings, "deepseek_api_key", "test-key")

    async def consume():
        return [chunk async for chunk in chat_route.stream_completion([{"role": "user", "content": "hello"}])]

    assert asyncio.run(consume()) == ["ok"]

    async def read_calls():
        async with db_sessions() as session:
            return (await session.execute(select(ModelCall))).scalars().all()

    calls = asyncio.run(read_calls())
    assert len(calls) == 1
    assert calls[0].feature == "chat"
    assert calls[0].input_tokens is None and calls[0].output_tokens is None
