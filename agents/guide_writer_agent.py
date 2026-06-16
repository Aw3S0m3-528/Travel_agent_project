import json
from agents.state import TravelState
from tools.llm_tool import llm_available, call_llm
from tools.prompt_tool import load_prompt


def build_poi_summary(
    poi: str,
    destination: str,
    preferences,
    info,
) -> str:
    preference_text = "、".join(preferences) if preferences else "本地特色体验"
    open_time = info.get("open_time", "建议出行前以官方信息为准")
    ticket = info.get("ticket", "以官方信息为准")
    ticket_type = info.get("ticket_type", "unknown")
    notice = info.get("notice", "建议错峰出行")

    if ticket_type == "free":
        ticket_summary = (
            f"门票方面，它可以归为免费景点或开放式公共游览区域，"
            f"{ticket}，因此比较适合控制预算、临时加到路线中。"
        )
    elif ticket_type == "partly_free":
        ticket_summary = (
            f"门票方面，它属于部分免费体验：{ticket}，"
            f"如果涉及交通、展馆或消费项目，需要按实际规则单独付费。"
        )
    elif ticket_type in {"paid", "paid_or_reservation"}:
        ticket_summary = (
            f"门票方面，它更适合作为需要提前确认的收费或预约类景点，"
            f"{ticket}，建议在出行前通过官方渠道核实。"
        )
    else:
        ticket_summary = (
            f"门票方面，目前资料不够明确，{ticket}，不建议在攻略中直接写死价格。"
        )

    return (
        f"{poi} 是 {destination} 行程中值得重点关注的地点之一，适合结合"
        f"“{preference_text}”这类旅行偏好进行安排。它的价值不只在于打卡，"
        f"也适合作为理解当地城市气质、街区氛围和旅行节奏的节点。"
        f"本次将它放入路线，是因为它与用户偏好匹配度较高，且便于和周边景点、"
        f"餐饮或商圈串联。建议预留约 1-2 小时游览，实际停留时间可根据排队、"
        f"天气和体力灵活调整。开放时间方面，{open_time}。{ticket_summary}"
        f"出行前还需要注意：{notice}。"
    )


def build_rule_guide(state: TravelState) -> str:
    """
    规则版攻略生成：
    用于保证攻略内容完整。
    """

    destination = state.get("destination", "目的地")
    travel_days = state.get("travel_days", 3)
    budget = state.get("budget", "中等预算")
    preferences = state.get("preferences", [])
    travel_intensity = state.get("travel_intensity", "适中")
    people_count = state.get("people_count", 1)
    start_date = state.get("start_date", "")
    constraints = state.get("constraints", [])
    route_plan = state.get("route_plan", {})
    time_plan = state.get("time_plan", {})
    retrieved_info = state.get("retrieved_info", [])
    images = state.get("images", {})
    image_sources = state.get("image_sources", {})
    rag_context = state.get("rag_context", "")
    route_segments = state.get("route_segments", {})
    budget_plan = state.get("budget_plan", {})

    info_map = {item["poi"]: item for item in retrieved_info}
    route_segment_count = sum(len(items) for items in route_segments.values()) if route_segments else 0

    guide = []

    guide.append(f"# {destination}{travel_days}日游智能旅游攻略\n")

    guide.append("## 一、行程概览\n")
    guide.append(f"- 目的地：{destination}")
    guide.append(f"- 出行天数：{travel_days} 天")
    guide.append(f"- 出行日期：{start_date if start_date else '用户未明确说明'}")
    guide.append(f"- 出行人数：{people_count} 人")
    guide.append(f"- 预算类型：{budget}")
    guide.append(f"- 旅行偏好：{'、'.join(preferences)}")
    guide.append(f"- 行程强度：{travel_intensity}")

    if constraints:
        guide.append(f"- 特殊限制：{'、'.join(constraints)}")

    guide.append("\n本攻略由多 Agent 协作生成，包括需求解析、信息检索、路径规划、时间规划、图片检索和攻略生成等步骤。\n")
    if rag_context:
        guide.append("### RAG 检索补充信息\n")
        guide.append("以下内容来自本地旅游知识库检索结果，用于辅助生成攻略。真实出行前仍建议以官方信息为准。\n")
        guide.append(rag_context)
        guide.append("")

    guide.append("## 二、每日行程安排\n")

    for day, schedule in time_plan.items():
        day_number = day.replace("day_", "")
        guide.append(f"### 第 {day_number} 天\n")

        route_items = route_plan.get(day, [])
        if route_items:
            route_text = " → ".join([item["poi"] for item in route_items])
            guide.append(f"**路线概览：** {route_text}\n")

            guide.append("**路径说明：**")
            for item in route_items:
                next_poi = item.get("next_poi", "")
                address = item.get("address", "")
                distance = item.get("distance", "待估算")
                duration = item.get("duration", "约15-30分钟")
                transport = item.get("transport", "地铁/步行/打车")

                if next_poi:
                    guide.append(
                        f"- {item['poi']} → {next_poi}：建议{transport}，"
                        f"距离{distance}，预计用时{duration}。"
                    )
                else:
                    guide.append(
                        f"- {item['poi']}：{address if address else '该景点地址待进一步确认'}。"
                    )
            guide.append("")

        guide.append("| 时间 | 安排 | 说明 |")
        guide.append("|---|---|---|")

        for item in schedule:
            guide.append(f"| {item['time']} | {item['activity']} | {item['note']} |")

        guide.append("")

    guide.append("## 三、景点介绍与推荐理由\n")

    for poi in state.get("selected_pois", []):
        info = info_map.get(poi, {})
        image_url = images.get(poi, "")

        guide.append(f"### {poi}\n")

        if image_url:
            guide.append(f"![{poi}]({image_url})\n")
            image_source = image_sources.get(poi, {})
            source_name = image_source.get("source", "图片来源")
            source_query = image_source.get("query", "")
            description_url = image_source.get("description_url", "")
            artist = image_source.get("artist", "")
            license_name = image_source.get("license", "")
            source_parts = [f"来源：{source_name}"]
            if description_url:
                source_parts.append(f"文件页：{description_url}")
            if artist:
                source_parts.append(f"作者：{artist}")
            if license_name:
                source_parts.append(f"许可：{license_name}")
            if source_query:
                source_parts.append(f"搜索词：{source_query}")
            guide.append(f"- 图片信息：{'；'.join(source_parts)}。\n")
        else:
            image_source = image_sources.get(poi, {})
            status = image_source.get("status", "not_found")
            query = image_source.get("query", "")
            if status in {"not_found", "error"}:
                guide.append(f"- 图片信息：未搜索到可直接展示的图片。搜索词：{query}。\n")

        guide.append(build_poi_summary(poi, destination, preferences, info))
        guide.append("")
        guide.append("**关键信息：**")
        guide.append("- 推荐属性：城市代表性景点 / 与用户偏好匹配 / 适合串联周边行程")
        guide.append("- 建议游玩时间：约 1-2 小时，具体可根据排队、天气和个人体力调整。")
        guide.append(f"- 开放时间：{info.get('open_time', '建议出行前以官方信息为准')}")
        guide.append(f"- 门票信息：{info.get('ticket', '以官方信息为准')}")
        guide.append(f"- 门票属性：{info.get('ticket_type', 'unknown')}")
        guide.append(f"- 出行提醒：{info.get('notice', '建议错峰出行')}\n")

    guide.append("## 四、餐饮与住宿建议\n")
    guide.append("- 餐饮建议：优先选择靠近当日景点的餐厅，减少跨区域移动时间。")
    guide.append("- 如果用户偏好美食，可将晚餐安排在当地特色街区或核心商圈附近。")
    guide.append(f"- 住宿建议：建议住在 {destination} 的核心商圈或交通便利区域，方便前往各景点。")
    guide.append(f"- 预算建议：当前方案按照“{budget}”进行规划。\n")

    if budget_plan:
        budget_range = budget_plan.get("estimated_total_range", [])
        guide.append("### 预算估算\n")
        if len(budget_range) == 2:
            guide.append(
                f"本次行程按“{budget_plan.get('budget_level', budget)}”、"
                f"{budget_plan.get('people_count', people_count)} 人、"
                f"{budget_plan.get('travel_days', travel_days)} 天粗略估算，"
                f"总预算约为 **{budget_range[0]}-{budget_range[1]} 元**。"
            )
        guide.append(f"- 餐饮估算：约 {budget_plan.get('meal_total', 0)} 元")
        guide.append(f"- 市内交通估算：约 {budget_plan.get('transport_total', 0)} 元")
        guide.append(f"- 住宿估算：约 {budget_plan.get('hotel_total', 0)} 元")
        guide.append(f"- 门票估算：约 {budget_plan.get('ticket_total', 0)} 元")
        guide.append("- 说明：该预算为规则估算，不代表实时价格；免费开放景点按 0 元门票估算。\n")

    guide.append("## 五、注意事项\n")
    guide.append("1. 景点开放时间、门票和预约规则可能变化，建议出行前再次查看官方信息。")
    guide.append("2. 节假日热门景点可能排队较长，建议提前预约。")
    if route_segment_count:
        guide.append("3. 当前路线已参考地图工具估算景点间距离和交通时间，但实际用时仍会受拥堵、排队和天气影响。")
    else:
        guide.append("3. 当前未获得地图路线段，交通时间为基础估算，建议出行前用地图 App 再次确认。")
    guide.append("4. 图片优先来自 Wikimedia Commons；若未命中，会使用 DuckDuckGo/Bing 图片搜索结果爬取相关图片。当前仅用于学习演示，正式发布前需要逐张确认授权、作者和来源。")
    guide.append("5. 后续版本可继续增强预算计算、历史行程保存、重新规划和真实图片检索能力。")

    return "\n".join(guide)


def check_guide_complete(text: str):
    """
    检查大模型生成的攻略是否完整。
    使用关键词组进行判断，避免因为模型换了说法而误判。
    """

    reasons = []

    if not text:
        reasons.append("大模型输出为空")
        return False, reasons

    if len(text) < 1200:
        reasons.append(f"输出内容过短，当前长度为 {len(text)} 字符，少于 1200 字符")

    required_keyword_groups = {
        "行程概览": ["行程概览", "行程总览", "整体概览"],
        "每日行程": ["每日行程", "每日安排", "每日路线", "每日行程安排"],
        "景点介绍": ["景点介绍", "景点特色", "景点推荐", "推荐理由"],
        "餐饮": ["餐饮", "美食", "用餐", "午餐", "晚餐"],
        "住宿": ["住宿", "酒店", "入住", "住在", "住宿建议", "酒店建议"],
        "注意事项": ["注意事项", "出行提醒", "温馨提示", "游玩提醒"]
    }

    for group_name, keywords in required_keyword_groups.items():
        if not any(keyword in text for keyword in keywords):
            reasons.append(f"缺少关键章节或关键词组：{group_name}，可接受关键词：{keywords}")

    if reasons:
        return False, reasons

    return True, []



def llm_guide_generate(state: TravelState, draft_guide: str) -> str:
    """
    大模型版攻略生成：
    只能在完整草稿基础上扩写和润色，不能压缩。
    """

    destination = state.get("destination", "目的地")
    travel_days = state.get("travel_days", 3)

    compact_state = {
        "destination": state.get("destination"),
        "travel_days": state.get("travel_days"),
        "start_date": state.get("start_date"),
        "people_count": state.get("people_count"),
        "budget": state.get("budget"),
        "preferences": state.get("preferences"),
        "travel_intensity": state.get("travel_intensity"),
        "transport_preference": state.get("transport_preference", ""),
        "accommodation_preference": state.get("accommodation_preference", ""),
        "constraints": state.get("constraints", []),
        "selected_pois": state.get("selected_pois", []),
        "route_plan": state.get("route_plan", {}),
        "time_plan": state.get("time_plan", {}),
        "retrieved_info": state.get("retrieved_info", []),
        "rag_context": state.get("rag_context", ""),
        "rag_sources": state.get("rag_sources", []),
        "online_sources": state.get("online_sources", []),
        "images": state.get("images", {}),
        "image_sources": state.get("image_sources", {}),
        "poi_locations": state.get("poi_locations", {}),
        "route_segments": state.get("route_segments", {})
    }

    system_prompt = load_prompt("guide_writer_prompt.txt")

    user_prompt = f"""
请根据以下信息，生成完整的 {destination}{travel_days}日游攻略。

【结构化状态】
{json.dumps(compact_state, ensure_ascii=False, indent=2)}

【完整草稿】
{draft_guide}

请在保留完整结构的基础上润色扩写，不要压缩。
"""

    return call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=8000
    )


def guide_writer_agent(state: TravelState) -> TravelState:
    """
    攻略生成 Agent 总入口：
    规则版保证完整，大模型负责润色。
    如果大模型输出不完整，自动回退到规则版。
    """

    draft_guide = build_rule_guide(state)

    if llm_available():
        try:
            final_guide = llm_guide_generate(state, draft_guide)

            is_complete, reasons = check_guide_complete(final_guide)

            if is_complete:
                return {
                **state,
                "final_guide": final_guide
                }

            print("攻略生成 Agent：大模型输出不完整，已回退到规则版完整攻略。")
            print("不完整原因：")
            for reason in reasons:
                print(f"- {reason}")

        except Exception as e:
            print(f"攻略生成 Agent 大模型调用失败，使用规则版兜底。错误信息：{e}")

    return {
        **state,
        "final_guide": draft_guide
    }
