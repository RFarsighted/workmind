import asyncio
import ast
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from app.services.agent import tools
from app.services.agent.agent import MAX_TOOL_CALLS, _event_output, build_agent_graph


def test_calculator_only_evaluates_allowed_arithmetic():
    assert tools._evaluate_expression(ast.parse("1500 + 800", mode="eval").body) == 2300
    with pytest.raises(ValueError):
        tools._evaluate_expression(ast.parse("__import__('os').system('whoami')", mode="eval").body)


def test_calculator_returns_structured_error_for_invalid_expression():
    result = asyncio.run(tools.calculate_tool.ainvoke({"expression": "4 / 0"}))
    assert json.loads(result)["ok"] is False


def test_date_tool_uses_calendar_arithmetic():
    result = asyncio.run(
        tools.get_date_tool.ainvoke(
            {"operation": "add_days", "start_date": "2026-01-01", "days": 30}
        )
    )
    assert json.loads(result) == {"ok": True, "date": "2026-01-31"}


def test_report_is_saved_under_configured_report_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "REPORT_DIRECTORY", tmp_path)
    result = json.loads(
        asyncio.run(
            tools.write_report_tool.ainvoke(
                {"title": "Test report", "content": "A short report."}
            )
        )
    )
    report_path = tmp_path / Path(result["path"]).name
    assert result["ok"] is True
    assert report_path.read_text(encoding="utf-8").startswith("# Test report")


def test_notification_is_explicitly_simulated():
    result = asyncio.run(
        tools.send_notify_tool.ainvoke(
            {"recipient": "HR", "subject": "Summary", "message": "Done"}
        )
    )
    assert json.loads(result)["simulated"] is True


def test_read_doc_returns_shared_rag_results(monkeypatch):
    async def fake_retrieve(question, *, category=None, limit=4):
        assert question == "差旅标准"
        assert limit == 4
        return [{"title": "差旅制度", "content": "酒店上限 600 元", "score": 0.9}]

    monkeypatch.setattr(tools, "retrieve_documents", fake_retrieve)
    result = asyncio.run(tools.read_doc_tool.ainvoke({"question": "差旅标准"}))
    assert json.loads(result)["documents"][0]["title"] == "差旅制度"


def test_agent_call_limit_and_tool_result_status():
    assert MAX_TOOL_CALLS == 7
    status, output = _event_output('{"ok": false, "error": "failed"}')
    assert status == "error"
    assert "failed" in output


def test_agent_graph_caps_tool_calls_and_returns_a_final_answer(monkeypatch):
    class BoundScriptedModel:
        def __init__(self, parent):
            self.parent = parent

        async def ainvoke(self, _messages):
            index = self.parent.calls
            self.parent.calls += 1
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": f"model-call-{index}",
                        "name": "calculate",
                        "args": {"expression": "1500 + 800"},
                    }
                ],
            )

    class ScriptedModel:
        calls = 0
        final_calls = 0

        def bind_tools(self, _tools, **_kwargs):
            return BoundScriptedModel(self)

        async def ainvoke(self, _messages):
            self.final_calls += 1
            return AIMessage(content="The result is 2300.")

    monkeypatch.setattr("app.services.agent.agent.settings.agent_max_tool_calls", 7)
    model = ScriptedModel()
    graph = build_agent_graph(model=model)

    async def collect_events():
        return [
            event
            async for event in graph.astream_events(
                {"messages": [{"role": "user", "content": "Add 1500 and 800."}], "tool_calls": 0},
                version="v2",
            )
        ]

    events = asyncio.run(collect_events())
    starts = [event for event in events if event["event"] == "on_tool_start"]
    ends = [event for event in events if event["event"] == "on_tool_end"]
    start_ids = {event["run_id"] for event in starts}
    end_ids = {event["run_id"] for event in ends}

    assert len(starts) == MAX_TOOL_CALLS
    assert len(start_ids) == MAX_TOOL_CALLS
    assert start_ids == end_ids
    assert model.calls == MAX_TOOL_CALLS
    assert model.final_calls == 1


def test_agent_graph_answers_directly_without_tools():
    class DirectModel:
        async def ainvoke(self, _messages):
            return AIMessage(content="Vue 3 is a progressive JavaScript framework.")

        def bind_tools(self, _tools, **_kwargs):
            return self

    graph = build_agent_graph(model=DirectModel())

    async def collect_events():
        return [
            event
            async for event in graph.astream_events(
                {"messages": [{"role": "user", "content": "介绍一下 Vue3"}], "tool_calls": 0},
                version="v2",
            )
        ]

    events = asyncio.run(collect_events())
    assert not [event for event in events if event["event"] == "on_tool_start"]
