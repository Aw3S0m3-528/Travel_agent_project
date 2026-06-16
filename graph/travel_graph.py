from typing import Callable, Iterator

from agents.state import TravelState
from graph.nodes import (
    budget_node,
    clarification_node,
    guide_writer_node,
    image_node,
    requirement_node,
    retrieval_node,
    revise_guide_node,
    route_node,
    time_node,
    validator_node,
    web_search_retry_node,
)
from graph.router import route_after_requirement, route_after_retrieval, route_after_validation

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - handled at runtime for optional dependency
    END = "__end__"
    StateGraph = None


MessageBuilder = Callable[[TravelState], str]


def langgraph_available() -> bool:
    return StateGraph is not None


def build_event(stage: str, title: str, message: str, state: TravelState) -> dict:
    return {
        "stage": stage,
        "title": title,
        "message": message,
        "state": state,
        "orchestrator": "langgraph",
    }


def _requirement_message(state: TravelState) -> str:
    preferences = "、".join(state.get("preferences", [])) or "未说明"
    return (
        f"目的地：{state.get('destination', '未识别')}，"
        f"天数：{state.get('travel_days', '未识别')}，"
        f"偏好：{preferences}。"
    )


def _retrieval_message(state: TravelState) -> str:
    return (
        f"已选择 {len(state.get('selected_pois', []))} 个候选景点；"
        f"本地资料 {len(state.get('rag_sources', []))} 条，"
        f"联网资料 {len(state.get('online_sources', []))} 条。"
    )


def _route_message(state: TravelState) -> str:
    route_segments = state.get("route_segments", {})
    segment_count = sum(len(items) for items in route_segments.values()) if route_segments else 0
    return (
        f"已生成 {len(state.get('route_plan', {}))} 天路线，"
        f"地图工具补充 {segment_count} 段交通信息。"
    )


def _time_message(state: TravelState) -> str:
    return f"已生成 {len(state.get('time_plan', {}))} 天时间表。"


def _image_message(state: TravelState) -> str:
    return (
        f"已为 {len(state.get('images', {}))}/"
        f"{len(state.get('selected_pois', []))} 个景点找到可展示图片。"
    )


def _budget_message(state: TravelState) -> str:
    budget_range = state.get("budget_plan", {}).get("estimated_total_range", [])
    if len(budget_range) == 2:
        return f"预计总预算约 {budget_range[0]}-{budget_range[1]} 元。"
    return "已生成预算估算。"


def _guide_message(state: TravelState) -> str:
    return f"已生成攻略正文，长度约 {len(state.get('final_guide', ''))} 字符。"


def _validation_message(state: TravelState) -> str:
    score = state.get("review_scores", {}).get("综合评分", "未评分")
    passed = "通过" if state.get("validation_passed") else "需要优化"
    return f"已完成复核，综合评分：{score}，状态：{passed}。"


def _clarification_message(state: TravelState) -> str:
    return state.get("clarification_question", "需求信息不完整，需要追问用户。")


def _retry_message(state: TravelState) -> str:
    return (
        f"第 {state.get('retry_count', 0)} 次重试完成；"
        f"本地资料 {len(state.get('rag_sources', []))} 条，"
        f"联网资料 {len(state.get('online_sources', []))} 条。"
    )


def _revise_message(state: TravelState) -> str:
    return f"已根据复核结果自动修正攻略，当前攻略约 {len(state.get('final_guide', ''))} 字符。"


STAGE_EVENTS: dict[str, tuple[str, str, MessageBuilder]] = {
    "requirement": ("requirement_done", "需求解析完成", _requirement_message),
    "clarification": ("clarification_needed", "需要补充需求", _clarification_message),
    "retrieval": ("retrieval_done", "信息检索完成", _retrieval_message),
    "web_search_retry": ("retrieval_retry_done", "检索重试完成", _retry_message),
    "route": ("route_done", "路线规划完成", _route_message),
    "time": ("time_done", "时间规划完成", _time_message),
    "image": ("image_done", "图片检索完成", _image_message),
    "budget": ("budget_done", "预算估算完成", _budget_message),
    "guide_writer": ("guide_done", "攻略生成完成", _guide_message),
    "revise_guide": ("guide_revised", "攻略自动修正完成", _revise_message),
    "validator": ("validation_done", "结果复核完成", _validation_message),
}


def build_travel_graph():
    if StateGraph is None:
        raise RuntimeError("LangGraph 未安装，请先安装 langgraph 或切换为传统顺序调度。")

    workflow = StateGraph(TravelState)
    workflow.add_node("requirement", requirement_node)
    workflow.add_node("clarification", clarification_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("web_search_retry", web_search_retry_node)
    workflow.add_node("route", route_node)
    workflow.add_node("time", time_node)
    workflow.add_node("image", image_node)
    workflow.add_node("budget", budget_node)
    workflow.add_node("guide_writer", guide_writer_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("revise_guide", revise_guide_node)

    workflow.set_entry_point("requirement")
    workflow.add_conditional_edges(
        "requirement",
        route_after_requirement,
        {
            "clarification": "clarification",
            "retrieval": "retrieval",
        },
    )
    workflow.add_edge("clarification", END)
    workflow.add_conditional_edges(
        "retrieval",
        route_after_retrieval,
        {
            "web_search_retry": "web_search_retry",
            "route": "route",
        },
    )
    workflow.add_edge("web_search_retry", "route")
    workflow.add_edge("route", "time")
    workflow.add_edge("time", "image")
    workflow.add_edge("image", "budget")
    workflow.add_edge("budget", "guide_writer")
    workflow.add_edge("guide_writer", "validator")
    workflow.add_conditional_edges(
        "validator",
        route_after_validation,
        {
            "revise_guide": "revise_guide",
            "__end__": END,
        },
    )
    workflow.add_edge("revise_guide", "validator")

    return workflow.compile()


def travel_graph_stream(user_input: str) -> Iterator[dict]:
    state: TravelState = {
        "user_input": user_input,
        "graph_trace": [],
        "retry_count": 0,
        "missing_requirements": [],
        "validation_passed": False,
        "confidence_score": 0.0,
    }
    yield build_event(
        stage="start",
        title="开始规划",
        message="已接收用户需求，准备启动 LangGraph 多 Agent 工作流。",
        state=state,
    )

    app = build_travel_graph()
    for chunk in app.stream(state, stream_mode="updates"):
        for node_name, node_state in chunk.items():
            if isinstance(node_state, dict):
                state.update(node_state)
            stage, title, message_builder = STAGE_EVENTS.get(
                node_name,
                (node_name, node_name, lambda current_state: "节点执行完成。"),
            )
            yield build_event(stage, title, message_builder(state), state)


def run_travel_graph(user_input: str) -> TravelState:
    final_state: TravelState = {"user_input": user_input}
    for event in travel_graph_stream(user_input):
        final_state = event["state"]
    return final_state
