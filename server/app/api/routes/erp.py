import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import desc, select

from app.core.config import settings
from app.core.database import SessionFactory
from app.models.erp_application import ERPApplication
from app.services.erp import (
    ERPModelError,
    ExpenseForm,
    LeaveForm,
    approval_roles,
    applicant_known_facts,
    parse_form,
    policy_violations,
    reviewer_decision,
    reviewer_question,
    validate_and_normalize_form,
)

router = APIRouter()
SHANGHAI = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)


class ParseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(min_length=1, max_length=4000)
    form_type: str = Field(alias="formType")


class SubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    form_data: dict = Field(alias="formData")
    form_type: str = Field(alias="formType")
    applicant_name: str = Field(default="申请人", alias="applicantName", max_length=128)


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _validate_submission(form_type: str, raw_form: dict) -> dict:
    try:
        if form_type == "expense":
            form = ExpenseForm.model_validate(raw_form)
            normalized = validate_and_normalize_form(form_type, form.model_dump(by_alias=True, mode="json"))
            return normalized
        if form_type == "leave":
            form = LeaveForm.model_validate(raw_form)
            normalized = validate_and_normalize_form(form_type, form.model_dump(by_alias=True, mode="json"))
            if not normalized.get("startDate") or not normalized.get("endDate"):
                raise ValueError("请假申请需要有效的开始日期和结束日期")
            return normalized
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail="formType 仅支持 expense 或 leave")


def _list_item(record: ERPApplication) -> dict:
    form = record.form_data or {}
    amount = form.get("totalAmount") if record.form_type == "expense" else None
    days = form.get("workdays") if record.form_type == "leave" else None
    return {
        "id": record.id,
        "formType": record.form_type,
        "status": record.status,
        "reason": form.get("reason", ""),
        "amount": amount,
        "days": days,
        "createdAt": record.created_at.isoformat() if record.created_at else None,
    }


def _detail(record: ERPApplication) -> dict:
    return {
        **_list_item(record),
        "applicantName": record.applicant_name,
        "formData": record.form_data,
        "approvalSteps": record.approval_steps,
        "approvalMessages": record.approval_messages,
        "finalResult": record.final_result,
        "error": record.error_message,
        "updatedAt": record.updated_at.isoformat() if record.updated_at else None,
    }


async def _save_record(session, record: ERPApplication) -> None:
    await session.commit()
    await session.refresh(record)


@router.post("/parse")
async def parse_erp_form(body: ParseRequest) -> dict:
    text = body.text.strip()
    form_type = body.form_type.strip().lower()
    if not text:
        raise HTTPException(status_code=422, detail="申请描述不能为空")
    if form_type not in {"expense", "leave"}:
        raise HTTPException(status_code=422, detail="formType 仅支持 expense 或 leave")
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="Set DEEPSEEK_API_KEY in server/.env to enable ERP parsing")
    try:
        form = await parse_form(text, form_type)
    except ERPModelError as exc:
        raise HTTPException(status_code=502, detail=f"ERP 表单解析失败：{exc}") from exc
    return {"form": form}


@router.get("/applications")
async def list_applications() -> dict:
    async with SessionFactory() as session:
        result = await session.execute(
            select(ERPApplication).order_by(desc(ERPApplication.created_at))
        )
        return {"applications": [_list_item(record) for record in result.scalars().all()]}


@router.get("/applications/{app_id}")
async def get_application(app_id: str) -> dict:
    async with SessionFactory() as session:
        record = await session.get(ERPApplication, app_id)
        if record is None:
            raise HTTPException(status_code=404, detail="申请记录不存在")
        return {"application": _detail(record)}


@router.post("/submit/stream")
async def submit_erp_application(body: SubmitRequest):
    form_type = body.form_type.strip().lower()
    form = _validate_submission(form_type, body.form_data)
    applicant_name = body.applicant_name.strip() or "申请人"
    app_id = str(uuid4())
    approvers = approval_roles(form_type, form)
    steps = [
        {"roleId": role["id"], "role": role, "status": "pending"}
        for role in approvers
    ]
    record = ERPApplication(
        id=app_id,
        form_type=form_type,
        applicant_name=applicant_name,
        status="pending",
        form_data=form,
        approval_steps=steps,
        approval_messages=[],
    )
    async with SessionFactory() as session:
        session.add(record)
        await session.commit()

    async def generate() -> AsyncIterator[str]:
        async with SessionFactory() as session:
            stored = await session.get(ERPApplication, app_id)
            if stored is None:
                yield _sse("error", {"message": "申请记录无法读取"})
                return

            yield _sse("start", {"appId": app_id, "startedAt": datetime.now(SHANGHAI).isoformat(timespec="seconds")})
            yield _sse("plan", {"approvers": approvers})

            async def mark_failed(message: str) -> None:
                await session.rollback()
                failed = await session.get(ERPApplication, app_id)
                if failed is not None:
                    failed.status = "failed"
                    failed.error_message = message[:1000] or "审批流程失败"
                    failed.final_result = {
                        "appId": app_id,
                        "approved": False,
                        "status": "failed",
                        "comment": "审批流程中断，请查看申请记录并重试。",
                    }
                    await session.commit()

            try:
                all_messages: list[dict] = []
                violations = policy_violations(ExpenseForm.model_validate(form)) if form_type == "expense" else []
                for index, role in enumerate(approvers):
                    next_steps = [dict(step) for step in stored.approval_steps]
                    next_steps[index]["status"] = "running"
                    stored.approval_steps = next_steps
                    await _save_record(session, stored)
                    yield _sse("approver_start", {"roleId": role["id"]})

                    question = await reviewer_question(role, form_type, form, all_messages)
                    question_message = {
                        "id": str(uuid4()),
                        "from": role["id"],
                        "role": role,
                        "content": question,
                        "type": "question",
                        "time": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
                    }
                    all_messages.append(question_message)
                    stored.approval_messages = list(all_messages)
                    await _save_record(session, stored)
                    yield _sse("message", question_message)

                    answer_message = {
                        "id": str(uuid4()),
                        "from": "applicant",
                        "role": None,
                        "content": applicant_known_facts(form_type, form),
                        "type": "answer",
                        "time": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
                    }
                    all_messages.append(answer_message)
                    stored.approval_messages = list(all_messages)
                    await _save_record(session, stored)
                    yield _sse("message", answer_message)

                    role_violations = violations if role["id"] == "finance" else []
                    if role_violations:
                        approved, comment = False, "；".join(role_violations)[:80]
                    else:
                        approved, comment = await reviewer_decision(
                            role, form_type, form, all_messages, violations
                        )
                    decision_message = {
                        "id": str(uuid4()),
                        "from": role["id"],
                        "role": role,
                        "content": comment,
                        "type": "decision",
                        "time": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
                    }
                    all_messages.append(decision_message)
                    stored.approval_messages = list(all_messages)
                    next_steps = [dict(step) for step in stored.approval_steps]
                    next_steps[index]["status"] = "approved" if approved else "rejected"
                    stored.approval_steps = next_steps
                    await _save_record(session, stored)
                    yield _sse("message", decision_message)
                    yield _sse("approver_done", {"roleId": role["id"], "approved": approved})

                    if not approved:
                        final = {"appId": app_id, "approved": False, "status": "rejected", "comment": comment}
                        stored.status = "rejected"
                        stored.final_result = final
                        stored.error_message = None
                        await _save_record(session, stored)
                        yield _sse("final", final)
                        yield _sse("done", {"appId": app_id})
                        return

                final = {"appId": app_id, "approved": True, "status": "approved", "comment": "所有审批角色均已通过"}
                stored.status = "approved"
                stored.final_result = final
                stored.error_message = None
                await _save_record(session, stored)
                yield _sse("final", final)
                yield _sse("done", {"appId": app_id})
            except asyncio.CancelledError:
                await mark_failed("客户端断开，审批流已中断")
                raise
            except Exception as exc:
                logger.exception("ERP approval failed for app_id=%s", app_id)
                await mark_failed(str(exc))
                yield _sse(
                    "final",
                    {
                        "appId": app_id,
                        "approved": False,
                        "status": "failed",
                        "comment": "审批流程中断，请查看申请记录并重试。",
                    },
                )
                yield _sse("error", {"message": "审批流程失败，请检查模型配置或查看服务端日志。"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
