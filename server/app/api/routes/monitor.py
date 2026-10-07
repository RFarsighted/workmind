from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.models.monitoring import ModelCall, MonitorSetting

router = APIRouter()
SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_BUDGET = 1_000_000
FEATURE_LABELS = {
    "chat": "对话助手",
    "knowledge": "RAG 知识库",
    "knowledge_embedding": "知识库向量化",
    "agent": "任务 Agent",
    "workflow": "内容工作流",
    "erp": "ERP 审批",
    "prompt": "Prompt 调试",
    "prompt_ab": "A/B 回答",
    "prompt_eval": "A/B 评分",
}


class BudgetRequest(BaseModel):
    dailyBudgetTokens: int = Field(ge=1, le=2_000_000_000)


def _local_midnight_utc(now: datetime) -> datetime:
    local = now.astimezone(SHANGHAI)
    return datetime.combine(local.date(), time.min, tzinfo=SHANGHAI).astimezone(timezone.utc)


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, (len(ordered) * percentile + 99) // 100 - 1)
    return ordered[index]


def _as_local(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc).astimezone(SHANGHAI) if value.tzinfo is None else value.astimezone(SHANGHAI)


async def _get_budget(session) -> int:
    setting = await session.get(MonitorSetting, "global")
    if setting is None:
        setting = MonitorSetting(key="global", daily_token_budget=DEFAULT_BUDGET)
        session.add(setting)
        await session.flush()
    return setting.daily_token_budget


@router.get("/stats")
async def get_stats() -> dict:
    now = datetime.now(timezone.utc)
    today_start = _local_midnight_utc(now)
    week_start = today_start - timedelta(days=6)
    retention_start = now - timedelta(days=90)

    async with SessionFactory() as session:
        await session.execute(delete(ModelCall).where(ModelCall.created_at < retention_start))
        budget = await _get_budget(session)
        result = await session.execute(
            select(ModelCall).where(ModelCall.created_at >= week_start).order_by(ModelCall.created_at.desc())
        )
        calls = list(result.scalars().all())
        await session.commit()

    local_calls = [(_as_local(call.created_at), call) for call in calls]
    today_calls = [(local_time, call) for local_time, call in local_calls if local_time >= today_start.astimezone(SHANGHAI)]
    successful_today = [(local_time, call) for local_time, call in today_calls if call.success]
    failed_today = len(today_calls) - len(successful_today)
    input_today = sum(call.input_tokens or 0 for _, call in successful_today)
    output_today = sum(call.output_tokens or 0 for _, call in successful_today)
    unknown_today = sum(call.input_tokens is None or call.output_tokens is None for _, call in successful_today)
    used_today = input_today + output_today

    daily = {}
    for offset in range(7):
        date = (today_start.astimezone(SHANGHAI).date() - timedelta(days=6 - offset))
        daily[date.isoformat()] = {
            "date": date.isoformat(),
            "label": f"{date.month}/{date.day}",
            "inputT": 0,
            "outputT": 0,
            "unknownCalls": 0,
        }

    by_feature = {}
    latencies = []
    for local_time, call in local_calls:
        day = daily.get(local_time.date().isoformat())
        if day and call.success:
            day["inputT"] += call.input_tokens or 0
            day["outputT"] += call.output_tokens or 0
            if call.input_tokens is None or call.output_tokens is None:
                day["unknownCalls"] += 1
        if local_time.date() == today_start.astimezone(SHANGHAI).date():
            if call.success and call.latency_ms > 0:
                latencies.append(call.latency_ms)
            aggregate = by_feature.setdefault(
                call.feature,
                {"feature": call.feature, "label": FEATURE_LABELS.get(call.feature, call.feature), "calls": 0,
                 "inputT": 0, "outputT": 0, "unknownCalls": 0},
            )
            aggregate["calls"] += 1
            aggregate["inputT"] += call.input_tokens or 0
            aggregate["outputT"] += call.output_tokens or 0
            if call.success and (call.input_tokens is None or call.output_tokens is None):
                aggregate["unknownCalls"] += 1
            if not call.success:
                aggregate["failedCalls"] = aggregate.get("failedCalls", 0) + 1

    recent_calls = [
        {
            "time": _as_local(call.created_at).isoformat(),
            "feature": call.feature,
            "inputT": call.input_tokens,
            "outputT": call.output_tokens,
            "latencyMs": call.latency_ms,
            "model": call.model,
            "success": call.success,
        }
        for _, call in local_calls[:100]
    ]
    percent = round(used_today / budget * 100, 1) if budget else 0
    return {
        "overview": {
            "apiCallsToday": len(today_calls),
            "successfulCallsToday": len(successful_today),
            "failedCallsToday": failed_today,
            "inputTokensToday": input_today,
            "outputTokensToday": output_today,
            "unknownUsageToday": unknown_today,
            "dailyBudgetTokens": budget,
            "budgetUsedPct": percent,
        },
        "last7Days": list(daily.values()),
        "byFeature": sorted(by_feature.values(), key=lambda item: item["calls"], reverse=True),
        "latency": {
            "avg": round(sum(latencies) / len(latencies)) if latencies else 0,
            "p50": _percentile(latencies, 50),
            "p90": _percentile(latencies, 90),
            "p99": _percentile(latencies, 99),
        },
        "recentCalls": recent_calls,
    }


@router.put("/budget")
async def update_budget(body: BudgetRequest) -> dict[str, int]:
    async with SessionFactory() as session:
        setting = await session.get(MonitorSetting, "global")
        if setting is None:
            setting = MonitorSetting(key="global", daily_token_budget=body.dailyBudgetTokens)
            session.add(setting)
        else:
            setting.daily_token_budget = body.dailyBudgetTokens
        await session.commit()
    return {"dailyBudgetTokens": body.dailyBudgetTokens}
