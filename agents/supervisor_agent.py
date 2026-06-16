from typing import Iterator

from agents.state import TravelState
from agents.requirement_agent import requirement_agent
from agents.retrieval_agent import retrieval_agent
from agents.route_agent import route_agent
from agents.time_agent import time_agent
from agents.image_agent import image_agent
from agents.budget_agent import budget_agent
from agents.guide_writer_agent import guide_writer_agent
from agents.validator_agent import validator_agent


def build_event(stage: str, title: str, message: str, state: TravelState) -> dict:
    return {
        "stage": stage,
        "title": title,
        "message": message,
        "state": state
    }


def supervisor_agent_stream(user_input: str) -> Iterator[dict]:
    """
    主 Agent：
    按阶段返回事件，便于前端实时展示多 Agent 协作过程。
    """

    state: TravelState = {
        "user_input": user_input
    }

    yield build_event(
        stage="start",
        title="开始规划",
        message="已接收用户需求，准备启动多 Agent 协作。",
        state=state
    )

    # 1. 需求解析
    state = requirement_agent(state)
    yield build_event(
        stage="requirement_done",
        title="需求解析完成",
        message=(
            f"目的地：{state.get('destination', '未识别')}；"
            f"天数：{state.get('travel_days', '未识别')}；"
            f"偏好：{'、'.join(state.get('preferences', [])) or '未说明'}。"
        ),
        state=state
    )

    # 2. 信息检索
    state = retrieval_agent(state)
    yield build_event(
        stage="retrieval_done",
        title="信息检索完成",
        message=(
            f"已选择 {len(state.get('selected_pois', []))} 个候选景点；"
            f"RAG 命中 {len(state.get('rag_sources', []))} 条资料。"
        ),
        state=state
    )

    # 3. 路径规划
    state = route_agent(state)
    route_days = len(state.get("route_plan", {}))
    route_segments = state.get("route_segments", {})
    route_segment_count = sum(len(items) for items in route_segments.values()) if route_segments else 0
    yield build_event(
        stage="route_done",
        title="路径规划完成",
        message=f"已生成 {route_days} 天路线，地图工具补充 {route_segment_count} 段交通信息。",
        state=state
    )

    # 4. 时间规划
    state = time_agent(state)
    yield build_event(
        stage="time_done",
        title="时间规划完成",
        message=f"已生成 {len(state.get('time_plan', {}))} 天时间表。",
        state=state
    )

    # 5. 图片检索
    state = image_agent(state)
    image_count = len(state.get("images", {}))
    yield build_event(
        stage="image_done",
        title="图片检索完成",
        message=f"已为 {image_count}/{len(state.get('selected_pois', []))} 个景点找到可展示图片。",
        state=state
    )

    # 6. 预算估算
    state = budget_agent(state)
    budget_range = state.get("budget_plan", {}).get("estimated_total_range", [])
    budget_message = "已生成预算估算。"
    if len(budget_range) == 2:
        budget_message = f"预计总预算约 {budget_range[0]}-{budget_range[1]} 元。"
    yield build_event(
        stage="budget_done",
        title="预算估算完成",
        message=budget_message,
        state=state
    )

    # 7. 攻略生成
    state = guide_writer_agent(state)
    yield build_event(
        stage="guide_done",
        title="攻略生成完成",
        message=f"已生成攻略正文，长度约 {len(state.get('final_guide', ''))} 字符。",
        state=state
    )

    # 8. 结果校验
    state = validator_agent(state)
    yield build_event(
        stage="validation_done",
        title="结果复核完成",
        message="已完成行程密度、RAG、地图、图片和攻略完整性复核。",
        state=state
    )


def supervisor_agent(user_input: str) -> TravelState:
    """
    主 Agent：
    按照技术文档中的流程，统一调度多个子 Agent。
    """

    final_state: TravelState = {
        "user_input": user_input
    }

    for event in supervisor_agent_stream(user_input):
        final_state = event["state"]

    return final_state
