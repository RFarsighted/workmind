"""Fixed-step PRD skeleton workflow."""

from typing import Any, TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.core.config import settings


class PRDState(TypedDict, total=False):
    description: str
    features: str
    constraints: str
    human_feedback: str
    prd: str


checkpointer = MemorySaver()


def _create_model(temperature: float, *, streaming: bool = False) -> ChatOpenAI:
    if not settings.deepseek_api_key:
        raise RuntimeError("Set DEEPSEEK_API_KEY in server/.env to enable workflows")
    return ChatOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        temperature=temperature,
        streaming=streaming,
    )


def build_prd_workflow(
    analysis_model: Runnable[Any, Any] | None = None,
    generation_model: Runnable[Any, Any] | None = None,
):
    """Build the PRD graph; model injection keeps the graph deterministic in tests."""
    analysis_model = analysis_model or _create_model(temperature=0)
    generation_model = generation_model or _create_model(temperature=0.7, streaming=True)
    parser = StrOutputParser()

    async def extract_features(state: PRDState) -> dict[str, str]:
        chain = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "从需求描述中提取明确提出的核心功能点，按优先级排序。"
                    "每条一行，格式为 P0/P1/P2 + 功能描述。不要添加原文没有的功能。",
                ),
                ("human", "需求描述：\n{description}"),
            ]
        ) | analysis_model | parser
        features = await chain.ainvoke({"description": state["description"]})
        return {"features": features}

    async def identify_constraints(state: PRDState) -> dict[str, str]:
        chain = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "识别需求描述中明确提到的技术约束和业务约束。\n"
                    "技术约束包括性能、兼容性和安全性；业务约束包括时间、预算和合规。\n"
                    "未提到的约束标记为‘待确认’，不要推测成已确定的事实。",
                ),
                ("human", "需求描述：\n{description}"),
            ]
        ) | analysis_model | parser
        constraints = await chain.ainvoke({"description": state["description"]})
        return {"constraints": constraints}

    async def human_review(_state: PRDState) -> dict[str, str]:
        return {}

    async def generate_prd(state: PRDState) -> dict[str, str]:
        chain = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是产品经理助手，生成有具体内容的 Markdown PRD 骨架。\n"
                    "只使用需求描述、提取结果和用户反馈中的事实。缺少的信息标记为‘待补充’或‘待确认’，"
                    "不得虚构已经确认的范围、指标、日期或约束。未给出排期时，里程碑只写建议阶段并注明待确认。\n"
                    "用户审核反馈：\n{feedback}",
                ),
                (
                    "human",
                    "需求描述：\n{description}\n\n"
                    "功能点：\n{features}\n\n"
                    "约束条件：\n{constraints}\n\n"
                    "请按以下八个章节生成 PRD：\n"
                    "## 一、背景与目标\n"
                    "## 二、范围\n"
                    "## 三、用户故事\n"
                    "## 四、功能需求\n"
                    "## 五、约束\n"
                    "## 六、验收标准\n"
                    "## 七、里程碑计划\n"
                    "## 八、待确认问题",
                ),
            ]
        ) | generation_model | parser
        prd = await chain.ainvoke(
            {
                "description": state["description"],
                "features": state.get("features", ""),
                "constraints": state.get("constraints", ""),
                "feedback": state.get("human_feedback", "") or "无",
            }
        )
        return {"prd": prd}

    builder = StateGraph(PRDState)
    builder.add_node("extract_features", extract_features)
    builder.add_node("identify_constraints", identify_constraints)
    builder.add_node("human_review", human_review)
    builder.add_node("generate_prd", generate_prd)
    builder.add_edge(START, "extract_features")
    builder.add_edge("extract_features", "identify_constraints")
    builder.add_edge("identify_constraints", "human_review")
    builder.add_edge("human_review", "generate_prd")
    builder.add_edge("generate_prd", END)
    return builder.compile(checkpointer=checkpointer, interrupt_before=["human_review"])
