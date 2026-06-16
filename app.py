import json

import pandas as pd
import pydeck as pdk
import streamlit as st
from agents.budget_agent import budget_agent
from agents.guide_writer_agent import guide_writer_agent
from agents.image_agent import image_agent
from agents.route_agent import enrich_route_with_map_api
from agents.supervisor_agent import supervisor_agent_stream
from agents.time_agent import time_agent
from agents.validator_agent import validator_agent
from database.db import get_itinerary, init_db, list_recent_itineraries, save_itinerary
from graph.travel_graph import langgraph_available, travel_graph_stream
from tools.map_tool import amap_available


st.set_page_config(
    page_title="多Agent旅游规划系统",
    page_icon="🧭",
    layout="wide"
)

EXAMPLE_PROMPTS = [
    "我想去成都玩三天，喜欢美食和人文景点，预算中等，不想太累",
    "我想去重庆玩两天，喜欢夜景和美食，行程轻松一点",
    "我想去西安玩四天，喜欢历史和博物馆，预算中等",
]

STAGE_PROGRESS = {
    "start": 5,
    "requirement_done": 18,
    "clarification_needed": 100,
    "retrieval_done": 32,
    "retrieval_retry_done": 36,
    "route_done": 48,
    "time_done": 62,
    "image_done": 74,
    "budget_done": 82,
    "guide_done": 92,
    "guide_revised": 96,
    "validation_done": 100,
}


def build_route_preview(state) -> str:
    route_plan = state.get("route_plan", {})
    if not route_plan:
        return "路线暂未生成。"

    lines = []
    for day, items in route_plan.items():
        route = " → ".join([item.get("poi", "") for item in items if item.get("poi")])
        lines.append(f"- {day}: {route or '暂无景点'}")

    return "\n".join(lines)


def build_map_points(state):
    points = []
    poi_locations = state.get("poi_locations", {})

    for day, locations in poi_locations.items():
        for index, location in enumerate(locations, start=1):
            lng = location.get("lng")
            lat = location.get("lat")

            if lng is None or lat is None:
                continue

            points.append({
                "day": day,
                "order": index,
                "name": location.get("name", ""),
                "address": location.get("formatted_address", ""),
                "lat": lat,
                "lon": lng,
            })

    return points


def build_map_lines(state):
    lines = []
    route_segments = state.get("route_segments", {})

    for day, segments in route_segments.items():
        for segment in segments:
            from_location = segment.get("from_location", "")
            to_location = segment.get("to_location", "")

            if not from_location or not to_location:
                continue

            try:
                from_lng, from_lat = [float(value) for value in from_location.split(",")]
                to_lng, to_lat = [float(value) for value in to_location.split(",")]
            except ValueError:
                continue

            lines.append({
                "day": day,
                "from": segment.get("from", ""),
                "to": segment.get("to", ""),
                "transport": segment.get("transport", ""),
                "distance_km": segment.get("distance_km"),
                "duration_min": segment.get("duration_min"),
                "from_coordinates": [from_lng, from_lat],
                "to_coordinates": [to_lng, to_lat],
            })

    return lines


def render_route_visualization(state):
    points = build_map_points(state)
    lines = build_map_lines(state)

    if not points:
        st.info("暂无可展示的地图点位。若已配置 AMAP_API_KEY，生成或重新规划后会显示景点地图。")
        return

    point_df = pd.DataFrame(points)

    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            data=point_df,
            get_position="[lon, lat]",
            get_radius=120,
            get_fill_color=[27, 126, 255, 180],
            pickable=True,
        )
    ]

    if lines:
        layers.append(
            pdk.Layer(
                "LineLayer",
                data=pd.DataFrame(lines),
                get_source_position="from_coordinates",
                get_target_position="to_coordinates",
                get_color=[255, 140, 0, 180],
                get_width=4,
                pickable=True,
            )
        )

    midpoint = point_df[["lat", "lon"]].mean()

    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(
                latitude=float(midpoint["lat"]),
                longitude=float(midpoint["lon"]),
                zoom=11,
                pitch=0,
            ),
            layers=layers,
            tooltip={
                "html": "<b>{name}</b><br/>第 {order} 站<br/>{address}",
                "style": {"fontSize": "12px"}
            },
        ),
        use_container_width=True,
    )

    st.dataframe(
        point_df[["day", "order", "name", "address"]],
        use_container_width=True,
        hide_index=True,
    )

    if lines:
        line_df = pd.DataFrame(lines)
        st.dataframe(
            line_df[["day", "from", "to", "transport", "distance_km", "duration_min"]],
            use_container_width=True,
            hide_index=True,
        )


def render_budget_summary(state):
    budget_plan = state.get("budget_plan", {})

    if not budget_plan:
        st.info("暂无预算估算。")
        return

    budget_range = budget_plan.get("estimated_total_range", [])
    if len(budget_range) == 2:
        st.metric("预计总预算", f"{budget_range[0]}-{budget_range[1]} 元")

    col_meal, col_transport, col_hotel, col_ticket = st.columns(4)
    col_meal.metric("餐饮", f"{budget_plan.get('meal_total', 0)} 元")
    col_transport.metric("市内交通", f"{budget_plan.get('transport_total', 0)} 元")
    col_hotel.metric("住宿", f"{budget_plan.get('hotel_total', 0)} 元")
    col_ticket.metric("门票", f"{budget_plan.get('ticket_total', 0)} 元")

    ticket_details = budget_plan.get("ticket_details", [])
    if ticket_details:
        st.dataframe(
            pd.DataFrame(ticket_details),
            use_container_width=True,
            hide_index=True,
        )


def build_export_markdown(state):
    parts = [
        state.get("final_guide", ""),
        "\n---\n",
        "## 行程复核结果\n",
        state.get("validation_result", ""),
    ]

    budget_plan = state.get("budget_plan", {})
    if budget_plan:
        budget_range = budget_plan.get("estimated_total_range", [])
        parts.extend([
            "\n---\n",
            "## 预算结构化数据\n",
        ])
        if len(budget_range) == 2:
            parts.append(f"- 预计总预算：{budget_range[0]}-{budget_range[1]} 元")
        parts.extend([
            f"- 餐饮：{budget_plan.get('meal_total', 0)} 元",
            f"- 市内交通：{budget_plan.get('transport_total', 0)} 元",
            f"- 住宿：{budget_plan.get('hotel_total', 0)} 元",
            f"- 门票：{budget_plan.get('ticket_total', 0)} 元",
        ])

    return "\n".join(parts)


def render_export_button(state, label="导出 Markdown"):
    destination = state.get("destination", "travel")
    travel_days = state.get("travel_days", "")
    file_name = f"{destination}{travel_days}日游攻略.md"

    st.download_button(
        label=label,
        data=build_export_markdown(state),
        file_name=file_name,
        mime="text/markdown",
        use_container_width=True,
    )


def build_manual_route_plan(day_pois):
    route_plan = {}

    for day_index, pois in enumerate(day_pois, start=1):
        day_key = f"day_{day_index}"
        route_plan[day_key] = []

        for poi in pois:
            route_plan[day_key].append({
                "poi": poi,
                "area": "用户自定义路线",
                "transport": "地铁/步行/打车",
                "duration": "约15-30分钟",
                "distance": "待地图 API 估算",
                "reason": "用户在行程编辑器中手动调整。"
            })

    return route_plan


def ensure_retrieved_info_for_pois(state, selected_pois):
    existing_info = {
        item.get("poi"): item
        for item in state.get("retrieved_info", [])
        if item.get("poi")
    }

    updated_info = []

    for poi in selected_pois:
        updated_info.append(existing_info.get(poi, {
            "poi": poi,
            "open_time": "建议出行前查询官方开放时间",
            "ticket": "以官方信息为准",
            "ticket_type": "unknown",
            "notice": "该景点为用户手动添加，建议出行前确认开放时间、门票和交通信息。"
        }))

    return updated_info


def replan_from_editor(state, day_pois):
    selected_pois = []
    for pois in day_pois:
        for poi in pois:
            if poi and poi not in selected_pois:
                selected_pois.append(poi)

    route_plan = build_manual_route_plan(day_pois)
    poi_locations = {}
    route_segments = {}

    if amap_available():
        try:
            destination = state.get("destination", "")
            route_plan, poi_locations, route_segments = enrich_route_with_map_api(route_plan, destination)
        except Exception as exc:
            print(f"行程编辑器：地图 API 更新失败，使用基础路线。错误信息：{exc}")

    updated_state = {
        **state,
        "selected_pois": selected_pois,
        "candidate_pois": selected_pois,
        "route_plan": route_plan,
        "poi_locations": poi_locations,
        "route_segments": route_segments,
        "retrieved_info": ensure_retrieved_info_for_pois(state, selected_pois),
    }

    updated_state = time_agent(updated_state)
    updated_state = image_agent(updated_state)
    updated_state = budget_agent(updated_state)
    updated_state = guide_writer_agent(updated_state)
    updated_state = validator_agent(updated_state)

    return updated_state


def route_plan_signature(state):
    return json.dumps(state.get("route_plan", {}), ensure_ascii=False, sort_keys=True)


def sync_editor_state(state):
    signature = route_plan_signature(state)

    if st.session_state.get("editor_signature") == signature:
        return

    st.session_state.editor_signature = signature
    st.session_state.editor_day_texts = {}

    route_plan = state.get("route_plan", {})
    travel_days = int(state.get("travel_days", 1) or 1)

    for day_index in range(1, travel_days + 1):
        day_key = f"day_{day_index}"
        pois = [
            item.get("poi", "")
            for item in route_plan.get(day_key, [])
            if item.get("poi")
        ]
        text = "\n".join(pois)
        st.session_state.editor_day_texts[day_key] = text
        st.session_state[f"editor_text_{day_key}"] = text


def parse_editor_day_pois(state):
    travel_days = int(state.get("travel_days", 1) or 1)
    day_pois = []

    for day_index in range(1, travel_days + 1):
        day_key = f"day_{day_index}"
        text = st.session_state.editor_day_texts.get(day_key, "")
        pois = []

        for line in text.splitlines():
            poi = line.strip()
            if poi and poi not in pois:
                pois.append(poi)

        day_pois.append(pois)

    return day_pois


def build_requirement_preview(state) -> str:
    return "\n".join([
        f"- 目的地：{state.get('destination', '未识别')}",
        f"- 天数：{state.get('travel_days', '未识别')}",
        f"- 预算：{state.get('budget', '未说明')}",
        f"- 偏好：{'、'.join(state.get('preferences', [])) or '未说明'}",
        f"- 强度：{state.get('travel_intensity', '未说明')}",
    ])


def render_validation_result(validation_result: str):
    if not validation_result:
        st.info("暂无复核结果。")
        return

    sections = {
        "评分总览": [],
        "通过项": [],
        "风险提示": [],
        "优化建议": [],
    }
    current_section = None

    for raw_line in validation_result.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### "):
            current_section = line.replace("### ", "", 1).strip()
            sections.setdefault(current_section, [])
            continue
        if line.startswith("- ") and current_section:
            sections[current_section].append(line[2:])

    if sections.get("评分总览"):
        score_cols = st.columns(min(5, len(sections["评分总览"])))
        for index, item in enumerate(sections["评分总览"]):
            name, _, value = item.partition("：")
            with score_cols[index % len(score_cols)]:
                st.metric(name, value)
    if sections.get("通过项"):
        st.success("\n".join([f"- {item}" for item in sections["通过项"]]))
    if sections.get("风险提示"):
        st.warning("\n".join([f"- {item}" for item in sections["风险提示"]]))
    if sections.get("优化建议"):
        st.info("\n".join([f"- {item}" for item in sections["优化建议"]]))


def render_graph_trace(state):
    graph_trace = state.get("graph_trace", [])

    if not graph_trace:
        st.info("当前编排模式未记录图执行轨迹。")
        return

    rows = []
    for index, item in enumerate(graph_trace, start=1):
        rows.append({
            "序号": index,
            "节点": item.get("title") or item.get("node", ""),
            "状态": item.get("status", ""),
            "耗时(ms)": item.get("elapsed_ms", ""),
            "摘要": item.get("summary", ""),
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    col_confidence, col_retry, col_validation = st.columns(3)
    col_confidence.metric("置信度", f"{state.get('confidence_score', 0):.2f}")
    col_retry.metric("重试次数", state.get("retry_count", 0))
    col_validation.metric("复核状态", "通过" if state.get("validation_passed") else "待优化/未通过")

    missing_requirements = state.get("missing_requirements", [])
    if missing_requirements:
        st.warning(f"缺失需求字段：{'、'.join(missing_requirements)}")


def get_orchestrator_stream():
    if st.session_state.get("orchestrator_mode") == "LangGraph":
        return travel_graph_stream
    return supervisor_agent_stream


def run_planning(user_input: str):
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        progress_bar = st.progress(0)
        stage_box = st.empty()
        event_log_box = st.container()
        preview_box = st.empty()
        events = []
        state = None

        try:
            stream_runner = get_orchestrator_stream()
            for event in stream_runner(user_input):
                events.append(event)
                state = event["state"]
                progress_bar.progress(STAGE_PROGRESS.get(event["stage"], 5))
                stage_box.info(f"{event['title']}：{event['message']}")

                with event_log_box:
                    st.write(f"**{event['title']}**：{event['message']}")

                if event["stage"] == "requirement_done":
                    preview_box.markdown("#### 需求解析\n" + build_requirement_preview(state))
                elif event["stage"] == "clarification_needed":
                    preview_box.markdown(
                        "#### 需要补充需求\n"
                        + state.get("clarification_question", "请补充旅行需求。")
                    )
                elif event["stage"] == "retrieval_retry_done":
                    preview_box.markdown(
                        "#### 检索重试\n"
                        f"当前资料来源：本地 {len(state.get('rag_sources', []))} 条，"
                        f"联网 {len(state.get('online_sources', []))} 条。"
                    )
                elif event["stage"] == "route_done":
                    preview_box.markdown("#### 路线草案\n" + build_route_preview(state))
                elif event["stage"] == "image_done":
                    preview_box.markdown(
                        f"#### 图片检索\n已找到 {len(state.get('images', {}))}/"
                        f"{len(state.get('selected_pois', []))} 张景点图片。"
                    )
                elif event["stage"] == "budget_done":
                    budget_range = state.get("budget_plan", {}).get("estimated_total_range", [])
                    if len(budget_range) == 2:
                        preview_box.markdown(f"#### 预算估算\n预计总预算约 {budget_range[0]}-{budget_range[1]} 元。")
                elif event["stage"] == "guide_revised":
                    preview_box.markdown("#### 攻略自动修正\nValidator 评分偏低，已完成一次修正。")
                elif event["stage"] == "validation_done":
                    preview_box.markdown("#### 复核完成\n正在展示最终攻略。")
        except Exception as exc:
            st.error("生成旅游规划时出现异常，请检查 API Key、网络连接或本地知识库配置。")
            st.exception(exc)
            return

        if state is None:
            st.error("生成旅游规划失败：未获得任何 Agent 输出。")
            return

        final_guide = state.get("final_guide", "")
        validation_result = state.get("validation_result", "")

        progress_bar.empty()
        orchestrator_name = "LangGraph" if st.session_state.get("orchestrator_mode") == "LangGraph" else "顺序调度"
        stage_box.success(f"多 Agent 协作完成。当前编排模式：{orchestrator_name}。")

        tab_guide, tab_map, tab_budget, tab_trace = st.tabs(["攻略正文", "路线地图", "预算估算", "执行轨迹"])
        with tab_guide:
            st.markdown(final_guide)
        with tab_map:
            render_route_visualization(state)
        with tab_budget:
            render_budget_summary(state)
        with tab_trace:
            render_graph_trace(state)

        render_export_button(state)

        st.divider()
        st.subheader("行程校验结果")
        render_validation_result(validation_result)

        st.session_state.last_state = state

        try:
            itinerary_id = save_itinerary(state)
            st.success(f"已保存到历史行程，编号：{itinerary_id}")
        except Exception as exc:
            st.warning(f"行程已生成，但保存历史记录失败：{exc}")

        assistant_content = final_guide + "\n\n---\n\n**行程校验结果：**\n" + validation_result

    st.session_state.messages.append({
        "role": "assistant",
        "content": assistant_content
    })


try:
    init_db()
except Exception as exc:
    st.warning(f"历史行程数据库初始化失败：{exc}")


st.title("基于多 Agent 辅助的旅游规划系统")

st.markdown("""
输入自然语言旅游需求，系统会通过多个 Agent 协作完成需求解析、资料检索、路线规划、时间安排、攻略生成与结果校验。

当前版本：V0.4 多 Agent + RAG + 地图工具 Demo
""")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_state" not in st.session_state:
    st.session_state.last_state = None

if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = ""

if "selected_itinerary_id" not in st.session_state:
    st.session_state.selected_itinerary_id = None

if "replan_note" not in st.session_state:
    st.session_state.replan_note = ""

if "editor_signature" not in st.session_state:
    st.session_state.editor_signature = ""

if "editor_day_texts" not in st.session_state:
    st.session_state.editor_day_texts = {}

if "orchestrator_mode" not in st.session_state:
    st.session_state.orchestrator_mode = "LangGraph" if langgraph_available() else "顺序调度"


with st.sidebar:
    st.header("系统说明")
    st.markdown("""
    ### 当前已实现
    - LangGraph / 顺序调度双编排模式
    - 需求解析、RAG 检索、路径规划、时间规划
    - 攻略生成与结果校验
    - 高德地图 POI 与路线估算工具
    - 本地 RAG + 近两年联网资料检索
    - 景点图片联网检索与缓存
    - SQLite 历史行程保存
    - 交互式行程编辑与局部重新规划

    ### 后续待实现
    - 更细粒度的图状态监控
    - 自动化评测集与观测面板
    """)

    orchestrator_options = ["LangGraph", "顺序调度"] if langgraph_available() else ["顺序调度"]
    st.session_state.orchestrator_mode = st.radio(
        "Agent 编排模式",
        options=orchestrator_options,
        index=orchestrator_options.index(st.session_state.orchestrator_mode)
        if st.session_state.orchestrator_mode in orchestrator_options
        else 0,
        help="LangGraph 更适合展示可扩展的多 Agent 工作流；顺序调度保留为兼容模式。",
    )

    if not langgraph_available():
        st.caption("当前环境未安装 LangGraph，已自动使用顺序调度。")

    if st.button("清空对话", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_state = None
        st.rerun()

    st.header("示例输入")
    for index, prompt in enumerate(EXAMPLE_PROMPTS, start=1):
        if st.button(prompt, key=f"example_{index}", use_container_width=True):
            st.session_state.pending_prompt = prompt
            st.rerun()

    if st.session_state.last_state:
        with st.expander("最近一次解析结果", expanded=False):
            state = st.session_state.last_state
            st.write(f"目的地：{state.get('destination', '未识别')}")
            st.write(f"天数：{state.get('travel_days', '未识别')}")
            st.write(f"预算：{state.get('budget', '未说明')}")
            st.write(f"偏好：{'、'.join(state.get('preferences', []))}")
            st.write(f"强度：{state.get('travel_intensity', '未说明')}")

    with st.expander("历史行程", expanded=False):
        try:
            recent_itineraries = list_recent_itineraries(limit=5)
            if not recent_itineraries:
                st.caption("暂无历史行程。")
            for item in recent_itineraries:
                preferences = "、".join(item.get("preferences", [])) or "未说明"
                st.markdown(
                    f"**#{item['id']} {item.get('destination') or '未知目的地'} "
                    f"{item.get('travel_days') or '-'} 天**  \n"
                    f"预算：{item.get('budget') or '未说明'}  \n"
                    f"偏好：{preferences}  \n"
                    f"时间：{item.get('created_at')}"
                )
                col_view, col_replan = st.columns(2)
                with col_view:
                    if st.button("查看", key=f"view_itinerary_{item['id']}", use_container_width=True):
                        st.session_state.selected_itinerary_id = item["id"]
                        st.rerun()
                with col_replan:
                    if st.button("重规划", key=f"replan_itinerary_{item['id']}", use_container_width=True):
                        detail = get_itinerary(item["id"])
                        if detail:
                            st.session_state.pending_prompt = detail.get("user_input", "")
                            st.session_state.selected_itinerary_id = item["id"]
                            st.rerun()
                st.divider()
        except Exception as exc:
            st.caption(f"读取历史行程失败：{exc}")


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


if st.session_state.selected_itinerary_id:
    selected_itinerary = get_itinerary(st.session_state.selected_itinerary_id)
    if selected_itinerary:
        with st.expander(
            f"历史行程详情 #{selected_itinerary['id']}：{selected_itinerary.get('destination') or '未知目的地'}",
            expanded=True
        ):
            st.caption(f"创建时间：{selected_itinerary.get('created_at')}")
            st.markdown(f"**原始需求：** {selected_itinerary.get('user_input', '')}")

            col_summary, col_action = st.columns([2, 1])
            with col_summary:
                preferences = "、".join(selected_itinerary.get("preferences", [])) or "未说明"
                st.write(f"天数：{selected_itinerary.get('travel_days') or '未说明'}")
                st.write(f"预算：{selected_itinerary.get('budget') or '未说明'}")
                st.write(f"偏好：{preferences}")
            with col_action:
                st.session_state.replan_note = st.text_area(
                    "修改要求",
                    value=st.session_state.replan_note,
                    placeholder="例如：减少博物馆，多安排美食和夜景",
                    height=120,
                )
                if st.button("按修改要求重新规划", use_container_width=True):
                    base_input = selected_itinerary.get("user_input", "")
                    note = st.session_state.replan_note.strip()
                    if note:
                        st.session_state.pending_prompt = f"{base_input}\n补充修改要求：{note}"
                    else:
                        st.session_state.pending_prompt = base_input
                    st.session_state.replan_note = ""
                    st.rerun()

            tab_guide, tab_validation = st.tabs(["攻略正文", "校验结果"])
            with tab_guide:
                st.markdown(selected_itinerary.get("final_guide", ""))
            with tab_validation:
                render_validation_result(selected_itinerary.get("validation_result", ""))
            detail_state = selected_itinerary.get("state_json") or selected_itinerary
            render_export_button(detail_state, label="导出历史攻略 Markdown")
    else:
        st.warning("未找到选中的历史行程。")


user_input = st.chat_input("请输入你的旅游需求，例如：我想去成都玩三天，喜欢美食和人文景点")
pending_prompt = st.session_state.pending_prompt

if user_input or pending_prompt:
    current_input = user_input or pending_prompt
    st.session_state.pending_prompt = ""

    st.session_state.messages.append({
        "role": "user",
        "content": current_input
    })

    run_planning(current_input)


if st.session_state.last_state:
    st.divider()
    st.subheader("行程编辑器")
    st.caption("每行一个景点。可以删除、改顺序或新增景点，然后只重新生成路线、时间表、图片、攻略和复核结果。")

    sync_editor_state(st.session_state.last_state)

    travel_days = int(st.session_state.last_state.get("travel_days", 1) or 1)

    with st.expander("编辑每日景点", expanded=False):
        editor_columns = st.columns(min(3, max(1, travel_days)))

        for day_index in range(1, travel_days + 1):
            day_key = f"day_{day_index}"
            column = editor_columns[(day_index - 1) % len(editor_columns)]

            with column:
                st.text_area(
                    f"第 {day_index} 天",
                    key=f"editor_text_{day_key}",
                    height=180,
                    help="每行一个景点，系统会按从上到下的顺序重新生成当天路线。"
                )
                st.session_state.editor_day_texts[day_key] = st.session_state[f"editor_text_{day_key}"]

        col_apply, col_reset = st.columns(2)

        with col_apply:
            if st.button("应用编辑并重新生成", use_container_width=True):
                day_pois = parse_editor_day_pois(st.session_state.last_state)

                if not any(day_pois):
                    st.warning("请至少保留或添加一个景点。")
                else:
                    with st.status("正在根据编辑内容重新规划...", expanded=True):
                        st.write("正在重建路线顺序...")
                        updated_state = replan_from_editor(st.session_state.last_state, day_pois)
                        st.write("正在生成新的时间表、图片和攻略...")

                    st.session_state.last_state = updated_state
                    st.session_state.editor_signature = ""

                    try:
                        itinerary_id = save_itinerary(updated_state)
                        st.success(f"编辑后的行程已保存，编号：{itinerary_id}")
                    except Exception as exc:
                        st.warning(f"编辑后的行程已生成，但保存失败：{exc}")

                    tab_edited_guide, tab_edited_map, tab_edited_budget, tab_edited_validation = st.tabs([
                        "编辑后攻略",
                        "编辑后地图",
                        "编辑后预算",
                        "编辑后复核"
                    ])
                    with tab_edited_guide:
                        st.markdown(updated_state.get("final_guide", ""))
                    with tab_edited_map:
                        render_route_visualization(updated_state)
                    with tab_edited_budget:
                        render_budget_summary(updated_state)
                    with tab_edited_validation:
                        render_validation_result(updated_state.get("validation_result", ""))
                    render_export_button(updated_state, label="导出编辑后攻略 Markdown")

        with col_reset:
            if st.button("恢复为当前行程", use_container_width=True):
                st.session_state.editor_signature = ""
                st.rerun()
