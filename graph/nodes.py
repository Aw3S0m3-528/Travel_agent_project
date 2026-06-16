import time
from typing import Optional

from agents.budget_agent import budget_agent
from agents.guide_writer_agent import guide_writer_agent
from agents.image_agent import image_agent
from agents.requirement_agent import requirement_agent
from agents.retrieval_agent import retrieval_agent
from agents.route_agent import route_agent
from agents.state import TravelState
from agents.time_agent import time_agent
from agents.validator_agent import validator_agent


NODE_TITLES = {
    "requirement": "需求解析",
    "retrieval": "信息检索",
    "web_search_retry": "联网检索重试",
    "route": "路线规划",
    "time": "时间规划",
    "image": "图片检索",
    "budget": "预算估算",
    "guide_writer": "攻略生成",
    "validator": "结果复核",
    "revise_guide": "攻略修正",
    "clarification": "需求追问",
}


def _append_trace(state: TravelState, node: str, status: str, summary: str, elapsed_ms: Optional[int] = None) -> TravelState:
    trace = list(state.get("graph_trace", []))
    item = {
        "node": node,
        "title": NODE_TITLES.get(node, node),
        "status": status,
        "summary": summary,
    }
    if elapsed_ms is not None:
        item["elapsed_ms"] = elapsed_ms
    trace.append(item)
    return {
        **state,
        "graph_trace": trace,
    }


def _summarize_state(node: str, state: TravelState) -> str:
    if node == "requirement":
        preferences = "、".join(state.get("preferences", [])) or "未说明"
        return (
            f"目的地：{state.get('destination', '未识别')}；"
            f"天数：{state.get('travel_days', '未识别')}；"
            f"偏好：{preferences}"
        )
    if node in {"retrieval", "web_search_retry"}:
        return (
            f"候选景点 {len(state.get('selected_pois', []))} 个；"
            f"本地资料 {len(state.get('rag_sources', []))} 条；"
            f"联网资料 {len(state.get('online_sources', []))} 条"
        )
    if node == "route":
        return f"已生成 {len(state.get('route_plan', {}))} 天路线"
    if node == "time":
        return f"已生成 {len(state.get('time_plan', {}))} 天时间表"
    if node == "image":
        return f"图片命中 {len(state.get('images', {}))}/{len(state.get('selected_pois', []))}"
    if node == "budget":
        budget_range = state.get("budget_plan", {}).get("estimated_total_range", [])
        if len(budget_range) == 2:
            return f"预算区间 {budget_range[0]}-{budget_range[1]} 元"
        return "预算估算完成"
    if node in {"guide_writer", "revise_guide"}:
        return f"攻略正文约 {len(state.get('final_guide', ''))} 字符"
    if node == "validator":
        score = state.get("review_scores", {}).get("综合评分", "未评分")
        return f"综合评分：{score}"
    if node == "clarification":
        return state.get("clarification_question", "需要补充旅行需求")
    return "节点执行完成"


def _run_traced_node(state: TravelState, node: str, agent_func) -> TravelState:
    working_state = _append_trace(dict(state), node, "start", f"进入{NODE_TITLES.get(node, node)}节点")
    started_at = time.perf_counter()
    result = agent_func(working_state)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000)
    return _append_trace(result, node, "success", _summarize_state(node, result), elapsed_ms)


def _detect_missing_requirements(state: TravelState) -> list[str]:
    user_input = state.get("user_input", "")
    destination = state.get("destination", "")
    missing = []

    known_cities = [
        "北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "南京", "西安", "长沙",
        "武汉", "东京", "大阪", "京都", "首尔", "曼谷",
    ]
    has_destination_hint = any(city in user_input for city in known_cities)
    if destination and destination in user_input:
        has_destination_hint = True
    if not has_destination_hint:
        missing.append("destination")

    day_keywords = [
        "一天", "两天", "三天", "四天", "五天", "六天", "七天",
        "1天", "2天", "3天", "4天", "5天", "6天", "7天",
        "1 天", "2 天", "3 天", "4 天", "5 天", "6 天", "7 天",
    ]
    if not any(keyword in user_input for keyword in day_keywords):
        missing.append("travel_days")

    return missing


def _build_clarification_question(missing_requirements: list[str]) -> str:
    labels = {
        "destination": "目的地",
        "travel_days": "出行天数",
    }
    missing_text = "、".join(labels.get(item, item) for item in missing_requirements)
    return (
        f"我还需要确认 {missing_text} 后才能继续生成可靠攻略。"
        "请补充一句，例如：我想去成都玩三天，喜欢美食和人文景点，预算中等。"
    )


def requirement_node(state: TravelState) -> TravelState:
    result = _run_traced_node(state, "requirement", requirement_agent)
    missing_requirements = _detect_missing_requirements(result)
    confidence_score = 0.55 if missing_requirements else 0.9
    return {
        **result,
        "missing_requirements": missing_requirements,
        "confidence_score": confidence_score,
    }


def retrieval_node(state: TravelState) -> TravelState:
    return _run_traced_node(state, "retrieval", retrieval_agent)


def web_search_retry_node(state: TravelState) -> TravelState:
    retry_count = int(state.get("retry_count", 0) or 0) + 1

    def retry_agent(current_state: TravelState) -> TravelState:
        return retrieval_agent({
            **current_state,
            "retry_count": retry_count,
        })

    result = _run_traced_node(
        {
            **state,
            "retry_count": retry_count,
        },
        "web_search_retry",
        retry_agent,
    )
    return {
        **result,
        "retry_count": retry_count,
    }


def route_node(state: TravelState) -> TravelState:
    return _run_traced_node(state, "route", route_agent)


def time_node(state: TravelState) -> TravelState:
    return _run_traced_node(state, "time", time_agent)


def image_node(state: TravelState) -> TravelState:
    return _run_traced_node(state, "image", image_agent)


def budget_node(state: TravelState) -> TravelState:
    return _run_traced_node(state, "budget", budget_agent)


def guide_writer_node(state: TravelState) -> TravelState:
    return _run_traced_node(state, "guide_writer", guide_writer_agent)


def validator_node(state: TravelState) -> TravelState:
    result = _run_traced_node(state, "validator", validator_agent)
    score = result.get("review_scores", {}).get("综合评分", 0)
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        score_value = 0
    return {
        **result,
        "confidence_score": round(score_value / 100, 2),
        "validation_passed": score_value >= 75,
    }


def clarification_node(state: TravelState) -> TravelState:
    missing_requirements = state.get("missing_requirements", [])
    question = _build_clarification_question(missing_requirements)
    result = {
        **state,
        "clarification_question": question,
        "final_guide": question,
        "validation_result": "### 风险提示\n- 需求信息不完整，已暂停后续规划，等待用户补充。",
        "validation_passed": False,
    }
    result = _append_trace(result, "clarification", "start", "进入需求追问节点")
    return _append_trace(result, "clarification", "success", question, 0)


def revise_guide_node(state: TravelState) -> TravelState:
    retry_count = int(state.get("retry_count", 0) or 0) + 1

    def revise_agent(current_state: TravelState) -> TravelState:
        revised = guide_writer_agent(current_state)
        guide = revised.get("final_guide", "")
        note = "\n\n---\n\n> 已根据 Validator 评分偏低的结果自动进行一次修正。"
        return {
            **revised,
            "final_guide": guide + note,
            "retry_count": retry_count,
        }

    return _run_traced_node(
        {
            **state,
            "retry_count": retry_count,
        },
        "revise_guide",
        revise_agent,
    )
