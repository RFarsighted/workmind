"""SSE API for the PRD skeleton workflow."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.services.workflow.prd import build_prd_workflow, checkpointer
from app.services.monitoring import langchain_usage, record_model_call

logger = logging.getLogger(__name__)
router = APIRouter()

PRD_TEMPLATE = {
    "id": "prd_skeleton",
    "title": "PRD 骨架",
    "icon": "📋",
    "desc": "输入需求描述，自动提取功能点和约束，生成结构化 PRD 文档",
    "inputLabel": "需求描述",
    "inputPlaceholder": "用自然语言描述你的产品需求...",
    "nodes": [
        {"id": "extract_features", "label": "提取功能点"},
        {"id": "identify_constraints", "label": "识别约束条件"},
        {"id": "human_review", "label": "人工审核", "isHuman": True},
        {"id": "generate_prd", "label": "生成 PRD"},
    ],
    "resultKey": "prd",
}

_active_workflows: dict[str, dict] = {}
_NODE_META = {node["id"]: node for node in PRD_TEMPLATE["nodes"]}


class WorkflowInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    description: str = Field(min_length=1, max_length=20_000)


class StartWorkflowRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    workflow_id: str = Field(alias="workflowId", min_length=1)
    input: WorkflowInput


class ResumeWorkflowRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True, extra="forbid")

    thread_id: str = Field(alias="threadId", min_length=1)
    feedback: str = Field(default="", max_length=10_000)


class CancelWorkflowRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True, extra="forbid")

    thread_id: str = Field(alias="threadId", min_length=1)


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _streaming_response(generator) -> StreamingResponse:
    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _preview(output) -> str:
    if isinstance(output, dict):
        output = next(iter(output.values()), "")
    return output[:80] + ("..." if len(output) > 80 else "") if isinstance(output, str) else ""


def _intermediates(values: dict) -> list[dict[str, str]]:
    return [
        {"key": key, "label": label, "value": values[key]}
        for key, label in (("features", "功能点"), ("constraints", "约束条件"))
        if values.get(key)
    ]


async def _delete_checkpoint(thread_id: str) -> None:
    delete_thread = getattr(checkpointer, "adelete_thread", None)
    if delete_thread is not None:
        await delete_thread(thread_id)


async def _emit_graph_events(graph, config: dict, input_data=None) -> AsyncIterator[tuple[str, dict]]:
    model_call_started: dict[str, float] = {}
    async for event in graph.astream_events(input_data, config, version="v2"):
        event_type = event.get("event")
        name = event.get("name", "")
        run_id = str(event.get("run_id") or "")
        node = _NODE_META.get(name)
        if event_type == "on_chat_model_start":
            model_call_started[run_id] = time.perf_counter()
        elif event_type == "on_chat_model_end":
            input_tokens, output_tokens = langchain_usage((event.get("data") or {}).get("output"))
            started = model_call_started.pop(run_id, None)
            if started is not None:
                await record_model_call(
                    feature="workflow", model=settings.deepseek_model,
                    input_tokens=input_tokens, output_tokens=output_tokens,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                )
        elif event_type == "on_chat_model_error":
            started = model_call_started.pop(run_id, None)
            if started is not None:
                await record_model_call(
                    feature="workflow", model=settings.deepseek_model,
                    latency_ms=round((time.perf_counter() - started) * 1000), success=False,
                )
        elif node and event_type == "on_chain_start":
            yield "node_start", {"nodeId": name, "label": node["label"]}
        elif node and event_type == "on_chain_end":
            output = (event.get("data") or {}).get("output")
            yield "node_done", {"nodeId": name, "preview": _preview(output)}
        elif event_type == "on_chat_model_stream" and (event.get("metadata") or {}).get("langgraph_node") == "generate_prd":
            chunk = (event.get("data") or {}).get("chunk")
            content = getattr(chunk, "content", None) if chunk else None
            if isinstance(content, str) and content:
                yield "token", {"token": content}


@router.get("/templates")
async def list_workflow_templates() -> dict:
    return {"templates": [PRD_TEMPLATE]}


@router.post("/start/stream")
async def start_workflow(body: StartWorkflowRequest):
    if body.workflow_id != PRD_TEMPLATE["id"]:
        raise HTTPException(status_code=400, detail=f"未知工作流：{body.workflow_id}")
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="Set DEEPSEEK_API_KEY in server/.env to enable workflows")

    thread_id = f"wf_{uuid4().hex}"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        graph = build_prd_workflow()
    except Exception as exc:
        logger.exception("Unable to build PRD workflow")
        raise HTTPException(status_code=503, detail="PRD 工作流暂时不可用") from exc

    entry = {"graph": graph, "config": config, "lock": asyncio.Lock()}
    _active_workflows[thread_id] = entry

    async def generate() -> AsyncIterator[str]:
        yield _sse("start", {"threadId": thread_id, "workflowId": body.workflow_id})
        try:
            async for event, data in _emit_graph_events(graph, config, body.input.model_dump()):
                yield _sse(event, data)

            state = await graph.aget_state(config)
            if state.next:
                yield _sse(
                    "paused",
                    {
                        "threadId": thread_id,
                        "nextNode": state.next[0],
                        "intermediates": _intermediates(state.values),
                    },
                )
            else:
                yield _sse("completed", {"threadId": thread_id, "result": state.values.get("prd", "")})
                _active_workflows.pop(thread_id, None)
                await _delete_checkpoint(thread_id)
        except asyncio.CancelledError:
            _active_workflows.pop(thread_id, None)
            await _delete_checkpoint(thread_id)
            raise
        except Exception:
            logger.exception("PRD workflow failed during start: %s", thread_id)
            _active_workflows.pop(thread_id, None)
            await _delete_checkpoint(thread_id)
            yield _sse("error", {"message": "PRD 工作流执行失败，请检查输入后重试"})

    return _streaming_response(generate)


@router.post("/resume/stream")
async def resume_workflow(body: ResumeWorkflowRequest):
    entry = _active_workflows.get(body.thread_id)
    if not entry:
        raise HTTPException(status_code=404, detail="工作流不存在或已过期，请重新启动")

    async def generate() -> AsyncIterator[str]:
        lock: asyncio.Lock = entry["lock"]
        if lock.locked():
            yield _sse("error", {"message": "该工作流正在执行"})
            return

        async with lock:
            if _active_workflows.get(body.thread_id) is not entry:
                yield _sse("error", {"message": "工作流已结束或已取消"})
                return
            graph, config = entry["graph"], entry["config"]
            try:
                await graph.aupdate_state(config, {"human_feedback": body.feedback})
                yield _sse("resumed", {"threadId": body.thread_id})
                async for event, data in _emit_graph_events(graph, config, None):
                    yield _sse(event, data)

                state = await graph.aget_state(config)
                if state.next:
                    yield _sse("paused", {"threadId": body.thread_id, "nextNode": state.next[0]})
                    return
                yield _sse("completed", {"threadId": body.thread_id, "result": state.values.get("prd", "")})
                _active_workflows.pop(body.thread_id, None)
                await _delete_checkpoint(body.thread_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("PRD workflow failed during resume: %s", body.thread_id)
                yield _sse("error", {"message": "PRD 生成失败，请检查服务后重试"})

    return _streaming_response(generate)


@router.post("/cancel")
async def cancel_workflow(body: CancelWorkflowRequest) -> dict[str, bool]:
    entry = _active_workflows.get(body.thread_id)
    if not entry:
        raise HTTPException(status_code=404, detail="工作流不存在或已过期")
    if entry["lock"].locked():
        raise HTTPException(status_code=409, detail="工作流正在执行，暂时无法取消")

    _active_workflows.pop(body.thread_id, None)
    await _delete_checkpoint(body.thread_id)
    return {"cancelled": True}
