import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.agent.agent import run_agent
from app.services.agent.tools import get_tool_list

router = APIRouter()
SHANGHAI = ZoneInfo("Asia/Shanghai")
EXAMPLES = [
    {
        "title": "金额计算",
        "task": "计算 1500 + 800 的总和，并用一句话说明结果。",
    },
    {
        "title": "知识库查询",
        "task": "从公司知识库查询差旅报销标准，并总结最重要的两点。",
    },
    {
        "title": "日期计算",
        "task": "今天是几号？从今天起 30 天后是什么日期？",
    },
    {
        "title": "生成报告",
        "task": "根据你掌握的信息生成一份简短的 WorkMind 模块介绍报告并保存。",
    },
    {
        "title": "年假查询",
        "task": "从知识库查询公司的年假政策，计算今年还剩多少年假（假设已用6天、总共15天），并生成一条给 HR 的模拟通知。",
    },
]


class AgentRunRequest(BaseModel):
    task: str = Field(min_length=1, max_length=2000)


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/tools")
async def list_agent_tools() -> dict:
    return {"tools": get_tool_list()}


@router.get("/examples")
async def list_agent_examples() -> dict:
    return {"examples": EXAMPLES}


@router.post("/run")
async def run_task(body: AgentRunRequest):
    task_text = body.task.strip()
    if not task_text:
        raise HTTPException(status_code=422, detail="任务不能为空")
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="Set DEEPSEEK_API_KEY in server/.env to enable the Agent")

    async def generate() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

        async def on_event(event: str, data: dict) -> None:
            await queue.put((event, data))

        run_task = asyncio.create_task(run_agent(task_text, on_event))
        yield _sse("start", {"task": task_text, "startedAt": datetime.now(SHANGHAI).isoformat(timespec="seconds")})
        try:
            while True:
                event, data = await queue.get()
                yield _sse(event, data)
                if event in {"done", "error"}:
                    await run_task
                    break
        finally:
            if not run_task.done():
                run_task.cancel()
                await asyncio.gather(run_task, return_exceptions=True)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
