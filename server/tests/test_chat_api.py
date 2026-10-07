import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.main import app
from app.models.chat_message import ChatMessage
from app.api.routes import chat as chat_route


def test_chat_stream_and_persistence(tmp_path, monkeypatch):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'chat-test.db'}"
    test_engine = create_async_engine(database_url, poolclass=NullPool)
    test_sessions = async_sessionmaker(test_engine, expire_on_commit=False)

    async def setup_database():
        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())
    monkeypatch.setattr(chat_route, "SessionFactory", test_sessions)
    monkeypatch.setattr(chat_route.settings, "deepseek_api_key", "test-key")

    seen_messages = []

    async def fake_completion(messages, **_kwargs):
        seen_messages.extend(messages)
        yield "Hello"
        yield " from WorkMind"

    monkeypatch.setattr(chat_route, "stream_completion", fake_completion)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/chat/stream",
                json={"message": "Hi", "sessionId": "session-1", "userId": "user-1"},
            )

        assert response.status_code == 200
        assert "event: token\ndata: {\"token\":\"Hello\"}" in response.text
        assert "event: done\n" in response.text
        assert seen_messages[-1] == {"role": "user", "content": "Hi"}

        async def read_messages():
            async with test_sessions() as session:
                result = await session.execute(select(ChatMessage).order_by(ChatMessage.id))
                return result.scalars().all()

        stored = asyncio.run(read_messages())
        assert [(item.role, item.content) for item in stored] == [
            ("user", "Hi"),
            ("assistant", "Hello from WorkMind"),
        ]
    finally:
        asyncio.run(test_engine.dispose())


def test_chat_requires_api_key(monkeypatch):
    monkeypatch.setattr(chat_route.settings, "deepseek_api_key", "")
    with TestClient(app) as client:
        response = client.post("/api/chat/stream", json={"message": "Hi"})
    assert response.status_code == 503
    assert "DEEPSEEK_API_KEY" in response.json()["error"]
