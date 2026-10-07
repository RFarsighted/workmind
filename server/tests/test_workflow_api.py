import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda

from app.api.routes import workflow as workflow_route
from app.main import app
from app.services.workflow.prd import build_prd_workflow


def _fake_graph(*, fail_analysis: bool = False, fail_generation: bool = False):
    def analyze(_prompt):
        if fail_analysis:
            raise RuntimeError("model unavailable")
        return "P0 - 用户评论；P1 - 点赞和回复"

    analysis = RunnableLambda(analyze)

    def generate(prompt):
        if fail_generation:
            raise RuntimeError("generation unavailable")
        return prompt.to_string()

    generation = RunnableLambda(generate)
    return build_prd_workflow(analysis_model=analysis, generation_model=generation)


def _events(response_text: str) -> list[tuple[str, dict]]:
    result = []
    for block in response_text.strip().split("\n\n"):
        lines = block.splitlines()
        event = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if event and data:
            result.append((event, json.loads(data)))
    return result


@pytest.fixture(autouse=True)
def configure_workflow(monkeypatch):
    monkeypatch.setattr(workflow_route.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(workflow_route, "build_prd_workflow", _fake_graph)
    workflow_route._active_workflows.clear()
    yield
    workflow_route._active_workflows.clear()


def _start(client: TestClient, description: str = "做一个用户评论功能，支持点赞和回复"):
    response = client.post(
        "/api/workflow/start/stream",
        json={"workflowId": "prd_skeleton", "input": {"description": description}},
    )
    assert response.status_code == 200
    events = _events(response.text)
    start = next(data for event, data in events if event == "start")
    return start["threadId"], events


def test_template_list_exposes_only_prd_skeleton():
    with TestClient(app) as client:
        response = client.get("/api/workflow/templates")

    assert response.status_code == 200
    templates = response.json()["templates"]
    assert [item["id"] for item in templates] == ["prd_skeleton"]
    assert [node["id"] for node in templates[0]["nodes"]] == [
        "extract_features",
        "identify_constraints",
        "human_review",
        "generate_prd",
    ]


def test_start_pauses_with_intermediates_and_resume_includes_feedback():
    with TestClient(app) as client:
        thread_id, events = _start(client)
        resume = client.post(
            "/api/workflow/resume/stream",
            json={"threadId": thread_id, "feedback": "重点说明回复权限"},
        )

    started_nodes = [data["nodeId"] for event, data in events if event == "node_start"]
    assert started_nodes == ["extract_features", "identify_constraints"]
    paused = next(data for event, data in events if event == "paused")
    assert paused["nextNode"] == "human_review"
    assert {item["key"] for item in paused["intermediates"]} == {"features", "constraints"}
    assert resume.status_code == 200
    resumed_events = _events(resume.text)
    result = next(data["result"] for event, data in resumed_events if event == "completed")
    assert "重点说明回复权限" in result
    assert "## 八、待确认问题" in result
    assert thread_id not in workflow_route._active_workflows


def test_blank_feedback_resumes_and_threads_are_isolated():
    with TestClient(app) as client:
        first_id, _ = _start(client, "第一个需求")
        second_id, _ = _start(client, "第二个需求")
        first = client.post("/api/workflow/resume/stream", json={"threadId": first_id, "feedback": ""})
        second = client.post("/api/workflow/resume/stream", json={"threadId": second_id, "feedback": ""})

    first_result = next(data["result"] for event, data in _events(first.text) if event == "completed")
    second_result = next(data["result"] for event, data in _events(second.text) if event == "completed")
    assert "第一个需求" in first_result
    assert "第二个需求" not in first_result
    assert "第二个需求" in second_result
    assert "第一个需求" not in second_result


def test_invalid_input_unknown_template_and_unknown_thread_are_rejected():
    with TestClient(app) as client:
        empty = client.post(
            "/api/workflow/start/stream",
            json={"workflowId": "prd_skeleton", "input": {"description": "   "}},
        )
        unknown = client.post(
            "/api/workflow/start/stream",
            json={"workflowId": "weekly_report", "input": {"description": "内容"}},
        )
        missing_thread = client.post(
            "/api/workflow/resume/stream", json={"threadId": "missing", "feedback": ""}
        )

    assert empty.status_code == 422
    assert unknown.status_code == 400
    assert "未知工作流" in unknown.json()["error"]
    assert missing_thread.status_code == 404


def test_model_failure_emits_error_without_success(monkeypatch):
    monkeypatch.setattr(workflow_route, "build_prd_workflow", lambda: _fake_graph(fail_analysis=True))
    with TestClient(app) as client:
        _, events = _start(client)

    names = [event for event, _ in events]
    assert "error" in names
    assert "completed" not in names
    assert "paused" not in names


def test_generation_failure_emits_error_without_success(monkeypatch):
    monkeypatch.setattr(workflow_route, "build_prd_workflow", lambda: _fake_graph(fail_generation=True))
    with TestClient(app) as client:
        thread_id, _ = _start(client)
        response = client.post(
            "/api/workflow/resume/stream", json={"threadId": thread_id, "feedback": ""}
        )

    names = [event for event, _ in _events(response.text)]
    assert "error" in names
    assert "completed" not in names


def test_cancel_discards_paused_thread():
    with TestClient(app) as client:
        thread_id, _ = _start(client)
        cancelled = client.post("/api/workflow/cancel", json={"threadId": thread_id})
        resume = client.post("/api/workflow/resume/stream", json={"threadId": thread_id, "feedback": ""})

    assert cancelled.status_code == 200
    assert cancelled.json() == {"cancelled": True}
    assert resume.status_code == 404


def test_start_requires_deepseek_api_key(monkeypatch):
    monkeypatch.setattr(workflow_route.settings, "deepseek_api_key", "")
    with TestClient(app) as client:
        response = client.post(
            "/api/workflow/start/stream",
            json={"workflowId": "prd_skeleton", "input": {"description": "需求"}},
        )

    assert response.status_code == 503
    assert "DEEPSEEK_API_KEY" in response.json()["error"]
