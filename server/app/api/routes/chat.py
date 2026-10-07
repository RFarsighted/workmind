import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionFactory
from app.models.chat_message import ChatMessage

router = APIRouter()

SYSTEM_PROMPTS = {
    "default": "You are WorkMind AI, a concise and helpful workplace assistant.",
    "tech": "You are a senior software engineering assistant. Explain technical answers clearly.",
    "hr": "You are an HR assistant. Give considerate answers and flag policy uncertainty.",
    "legal": "You are a legal information assistant. Be careful and distinguish information from advice.",
}

CHAT_ROLES = [
    {"id": "default", "label": "通用助手", "desc": "日常问答与通用工作任务", "icon": "💬"},
    {"id": "tech", "label": "技术顾问", "desc": "软件工程与技术问题", "icon": "💻"},
    {"id": "hr", "label": "HR 助手", "desc": "人力资源与职场问题", "icon": "👥"},
    {"id": "legal", "label": "法律顾问", "desc": "法律信息与合同问题", "icon": "⚖️"},
]


class ChatStreamRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default="default", alias="sessionId", max_length=128)
    user_id: str = Field(default="user-demo", alias="userId", max_length=128)
    role: str = Field(default="default", max_length=32)


@router.get("/roles")
async def get_chat_roles() -> dict[str, list[dict[str, str]]]:
    return {"roles": CHAT_ROLES}


@router.get("/profile/{user_id}")
async def get_profile(user_id: str) -> dict[str, Any]:
    """Return the user's profile, or an empty profile when none is stored yet."""
    # Profile persistence is not implemented yet; keep the API contract available
    # so the chat UI can load its empty state without generating a 404.
    return {}


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


async def stream_completion(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    if not settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    endpoint = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.deepseek_api_key}"}
    body = {"model": settings.deepseek_model, "messages": messages, "stream": True}

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        async with client.stream("POST", endpoint, headers=headers, json=body) as response:
            if response.is_error:
                await response.aread()
                raise RuntimeError(f"DeepSeek returned HTTP {response.status_code}")

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if value == "[DONE]":
                    break
                try:
                    chunk = json.loads(value)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if choices:
                    token = choices[0].get("delta", {}).get("content")
                    if token:
                        yield token


@router.post("/stream")
async def chat_stream(body: ChatStreamRequest):
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="Set DEEPSEEK_API_KEY in server/.env to enable chat")

    async def generate() -> AsyncIterator[str]:
        async with SessionFactory() as session:
            try:
                result = await session.execute(
                    select(ChatMessage)
                    .where(
                        ChatMessage.user_id == body.user_id,
                        ChatMessage.session_id == body.session_id,
                    )
                    .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                    .limit(20)
                )
                history = list(reversed(result.scalars().all()))
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPTS.get(body.role, SYSTEM_PROMPTS["default"])},
                    *({"role": item.role, "content": item.content} for item in history),
                    {"role": "user", "content": body.message},
                ]
                yield _sse("start", {"sessionId": body.session_id})

                reply_parts: list[str] = []
                async for token in stream_completion(messages):
                    reply_parts.append(token)
                    yield _sse("token", {"token": token})

                reply = "".join(reply_parts)
                session.add_all(
                    [
                        ChatMessage(
                            user_id=body.user_id,
                            session_id=body.session_id,
                            role="user",
                            content=body.message,
                        ),
                        ChatMessage(
                            user_id=body.user_id,
                            session_id=body.session_id,
                            role="assistant",
                            content=reply,
                        ),
                    ]
                )
                await session.commit()
                yield _sse("done", {"fromCache": False, "inputTokens": 0, "outputTokens": 0})
            except Exception:
                await session.rollback()
                yield _sse("error", {"message": "Chat request failed. Check the API key and backend logs."})

    from fastapi.responses import StreamingResponse

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
