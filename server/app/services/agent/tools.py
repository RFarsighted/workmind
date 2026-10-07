import ast
import asyncio
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.services.rag.retrieval import retrieve_documents

REPORT_DIRECTORY = Path(__file__).resolve().parents[3] / "data" / "reports"
SHANGHAI = ZoneInfo("Asia/Shanghai")


class ReadDocArgs(BaseModel):
    question: str = Field(min_length=1, max_length=1000, description="要查询的知识库问题或关键词")


@tool("read_doc", args_schema=ReadDocArgs)
async def read_doc_tool(question: str) -> str:
    """检索公司知识库中的制度、产品资料或技术文档；不要用于互联网最新信息。"""
    try:
        documents = await retrieve_documents(question, limit=4)
        if not documents:
            return json.dumps({"ok": True, "found": False, "message": "知识库中未找到相关内容。"}, ensure_ascii=False)
        return json.dumps({"ok": True, "found": True, "documents": documents}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"知识库检索失败：{exc}"}, ensure_ascii=False)


class CalculateArgs(BaseModel):
    expression: str = Field(min_length=1, max_length=512, description="只支持数字、括号和 + - * / // % ** 运算")


_BINARY_OPERATORS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left**right,
}
_UNARY_OPERATORS = {ast.UAdd: lambda value: value, ast.USub: lambda value: -value}


def _evaluate_expression(node: ast.AST, *, depth: int = 0) -> int | float:
    if depth > 32:
        raise ValueError("表达式嵌套过深")
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate_expression(node.operand, depth=depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate_expression(node.left, depth=depth + 1)
        right = _evaluate_expression(node.right, depth=depth + 1)
        if isinstance(node.op, ast.Pow) and abs(right) > 12:
            raise ValueError("乘方指数不能超过 12")
        return _BINARY_OPERATORS[type(node.op)](left, right)
    raise ValueError("表达式包含不支持的语法")


@tool("calculate", args_schema=CalculateArgs)
async def calculate_tool(expression: str) -> str:
    """精确计算简单算术表达式，用于金额、数量和工期的数字运算。"""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _evaluate_expression(tree.body)
        if type(result) not in (int, float):
            raise ValueError("计算结果必须是实数")
        if isinstance(result, int) and result.bit_length() > 1024:
            raise ValueError("计算结果超出允许范围")
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("计算结果不是有限数值")
        return json.dumps({"ok": True, "expression": expression, "result": result}, ensure_ascii=False)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as exc:
        return json.dumps({"ok": False, "error": f"无法计算该表达式：{exc}"}, ensure_ascii=False)


class GetDateArgs(BaseModel):
    operation: Literal["today", "add_days", "diff"] = Field(description="today=今天；add_days=日期加天数；diff=计算两个日期相差天数")
    start_date: str | None = Field(default=None, description="起始日期，格式 YYYY-MM-DD")
    days: int | None = Field(default=None, description="要增加的天数，可为负数")
    end_date: str | None = Field(default=None, description="结束日期，格式 YYYY-MM-DD")


@tool("get_date", args_schema=GetDateArgs)
async def get_date_tool(
    operation: str,
    start_date: str | None = None,
    days: int | None = None,
    end_date: str | None = None,
) -> str:
    """查询上海时区的今天日期，或进行日期加减和日期差计算。"""
    try:
        today = datetime.now(SHANGHAI).date()
        if operation == "today":
            result = {"ok": True, "date": today.isoformat(), "timezone": "Asia/Shanghai"}
        elif operation == "add_days" and start_date is not None and days is not None:
            result = {"ok": True, "date": (date.fromisoformat(start_date) + timedelta(days=days)).isoformat()}
        elif operation == "diff" and start_date is not None and end_date is not None:
            result = {"ok": True, "days": abs((date.fromisoformat(end_date) - date.fromisoformat(start_date)).days)}
        else:
            raise ValueError("参数与日期操作不匹配")
        return json.dumps(result, ensure_ascii=False)
    except (ValueError, OverflowError) as exc:
        return json.dumps({"ok": False, "error": f"日期操作失败：{exc}"}, ensure_ascii=False)


class WriteReportArgs(BaseModel):
    title: str = Field(min_length=1, max_length=160, description="报告标题")
    content: str = Field(min_length=1, max_length=100_000, description="Markdown 格式的报告正文")


def _report_path(title: str) -> Path:
    slug = re.sub(r"[^\w\-]+", "-", title, flags=re.UNICODE).strip("-")[:60] or "report"
    timestamp = datetime.now(SHANGHAI).strftime("%Y%m%d-%H%M%S")
    return REPORT_DIRECTORY / f"{timestamp}-{slug}-{uuid4().hex[:8]}.md"


@tool("write_report", args_schema=WriteReportArgs)
async def write_report_tool(title: str, content: str) -> str:
    """将已完成的分析整理为 Markdown 报告并保存到项目限定的报告目录。"""
    if not title.strip() or not content.strip():
        return json.dumps({"ok": False, "error": "报告标题和正文不能为空。"}, ensure_ascii=False)
    timestamp = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    report = f"# {title.strip()}\n\n> 生成时间：{timestamp}（Asia/Shanghai）\n\n{content.strip()}\n"
    path = _report_path(title)
    try:
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_text, report, encoding="utf-8")
        return json.dumps(
            {
                "ok": True,
                "title": title.strip(),
                "path": path.relative_to(REPORT_DIRECTORY.parent.parent).as_posix(),
                "message": "报告已保存。",
            },
            ensure_ascii=False,
        )
    except OSError as exc:
        return json.dumps({"ok": False, "error": f"报告保存失败：{exc}"}, ensure_ascii=False)


class SendNotifyArgs(BaseModel):
    recipient: str = Field(min_length=1, max_length=120, description="通知接收人或团队名称")
    subject: str = Field(min_length=1, max_length=200, description="通知主题")
    message: str = Field(min_length=1, max_length=4000, description="通知正文")


@tool("send_notify", args_schema=SendNotifyArgs)
async def send_notify_tool(recipient: str, subject: str, message: str) -> str:
    """模拟生成一条通知结果；当前版本不会联系外部人员或发送真实消息。"""
    return json.dumps(
        {
            "ok": True,
            "simulated": True,
            "recipient": recipient,
            "subject": subject,
            "message": message,
            "sentAt": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
        },
        ensure_ascii=False,
    )


all_tools = [read_doc_tool, calculate_tool, get_date_tool, write_report_tool, send_notify_tool]
TOOL_LABELS = {
    "read_doc": "检索知识库",
    "calculate": "数学计算",
    "get_date": "日期查询",
    "write_report": "生成报告",
    "send_notify": "模拟通知",
}


def get_tool_list() -> list[dict[str, str]]:
    return [
        {"name": item.name, "label": TOOL_LABELS[item.name], "description": item.description or ""}
        for item in all_tools
    ]
