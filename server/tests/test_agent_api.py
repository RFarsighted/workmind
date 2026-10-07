from fastapi.testclient import TestClient

from app.api.routes import agent as agent_route
from app.main import app


def test_agent_tools_and_examples_endpoints():
    with TestClient(app) as client:
        tools_response = client.get("/api/agent/tools")
        examples_response = client.get("/api/agent/examples")

    assert tools_response.status_code == 200
    assert {item["name"] for item in tools_response.json()["tools"]} == {
        "read_doc",
        "calculate",
        "get_date",
        "write_report",
        "send_notify",
    }
    assert examples_response.status_code == 200
    assert examples_response.json()["examples"]


def test_agent_run_requires_deepseek_key(monkeypatch):
    monkeypatch.setattr(agent_route.settings, "deepseek_api_key", "")
    with TestClient(app) as client:
        response = client.post("/api/agent/run", json={"task": "Calculate 1 + 1"})
    assert response.status_code == 503
    assert "DEEPSEEK_API_KEY" in response.json()["error"]


def test_agent_run_streams_correlated_tool_events(monkeypatch):
    monkeypatch.setattr(agent_route.settings, "deepseek_api_key", "test-key")

    async def fake_run_agent(task, on_event):
        await on_event(
            "tool_call",
            {"callId": "tool-run-1", "toolName": "calculate", "label": "数学计算", "args": {"expression": "1 + 1"}},
        )
        await on_event(
            "tool_result",
            {"callId": "tool-run-1", "toolName": "calculate", "status": "done", "resultText": "2"},
        )
        await on_event("token", {"token": "2"})
        await on_event("done", {"toolCalls": 1})

    monkeypatch.setattr(agent_route, "run_agent", fake_run_agent)
    with TestClient(app) as client:
        response = client.post("/api/agent/run", json={"task": "Calculate 1 + 1"})

    assert response.status_code == 200
    assert 'event: start\n' in response.text
    assert '"callId":"tool-run-1"' in response.text
    assert 'event: tool_result\n' in response.text
    assert 'event: token\n' in response.text
    assert 'event: done\n' in response.text
