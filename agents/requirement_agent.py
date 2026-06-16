from agents.state import TravelState
from tools.llm_tool import llm_available, call_llm, extract_json
from tools.prompt_tool import load_prompt


def rule_requirement_parse(state: TravelState) -> TravelState:
    """
    规则版需求解析：
    当没有配置大模型，或者大模型解析失败时使用。
    """

    user_input = state.get("user_input", "")

    destination = "成都"
    travel_days = 3
    budget = "中等预算"
    people_count = 1
    travel_intensity = "适中"
    preferences = []

    city_candidates = [
        "北京", "上海", "广州", "深圳", "成都", "重庆",
        "杭州", "南京", "西安", "长沙", "武汉",
        "东京", "大阪", "京都", "首尔", "曼谷"
    ]

    for city in city_candidates:
        if city in user_input:
            destination = city
            break

    if "一天" in user_input or "1天" in user_input:
        travel_days = 1
    elif "两天" in user_input or "2天" in user_input:
        travel_days = 2
    elif "三天" in user_input or "3天" in user_input:
        travel_days = 3
    elif "四天" in user_input or "4天" in user_input:
        travel_days = 4
    elif "五天" in user_input or "5天" in user_input:
        travel_days = 5
    elif "六天" in user_input or "6天" in user_input:
        travel_days = 6
    elif "七天" in user_input or "7天" in user_input:
        travel_days = 7

    preference_keywords = {
        "美食": "美食",
        "夜景": "夜景",
        "人文": "人文历史",
        "历史": "人文历史",
        "自然": "自然风光",
        "拍照": "拍照打卡",
        "博物馆": "博物馆",
        "亲子": "亲子游",
        "购物": "购物",
        "轻松": "轻松游",
        "寺庙": "寺庙古迹",
        "古镇": "古镇古街",
        "海边": "海滨度假",
        "山": "自然风光"
    }

    for keyword, value in preference_keywords.items():
        if keyword in user_input and value not in preferences:
            preferences.append(value)

    if not preferences:
        preferences = ["经典景点", "当地特色"]

    if "低预算" in user_input or "便宜" in user_input or "省钱" in user_input:
        budget = "低预算"
    elif "高预算" in user_input or "奢华" in user_input or "不差钱" in user_input:
        budget = "高预算"
    elif "中等" in user_input or "适中" in user_input:
        budget = "中等预算"

    if "轻松" in user_input or "不累" in user_input or "慢" in user_input:
        travel_intensity = "轻松"
    elif "紧凑" in user_input or "多玩" in user_input:
        travel_intensity = "紧凑"
    elif "特种兵" in user_input:
        travel_intensity = "特种兵"

    return {
        **state,
        "destination": destination,
        "travel_days": travel_days,
        "people_count": people_count,
        "budget": budget,
        "preferences": preferences,
        "travel_intensity": travel_intensity,
        "start_date": "",
    }


def llm_requirement_parse(state: TravelState) -> TravelState:
    """
    大模型版需求解析：
    要求模型只输出 JSON。
    """

    user_input = state.get("user_input", "")

    system_prompt = load_prompt("requirement_prompt.txt")

    user_prompt = f"""
用户旅游需求如下：

{user_input}
"""

    response = call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=1000
    )

    data = extract_json(response)

    if not data:
        raise ValueError("大模型需求解析失败，未获得有效 JSON")

    destination = data.get("destination") or "成都"
    travel_days = int(data.get("travel_days") or 3)
    people_count = int(data.get("people_count") or 1)
    budget = data.get("budget") or "中等预算"
    preferences = data.get("preferences") or ["经典景点", "当地特色"]
    travel_intensity = data.get("travel_intensity") or "适中"

    return {
        **state,
        "destination": destination,
        "travel_days": travel_days,
        "start_date": data.get("start_date", ""),
        "people_count": people_count,
        "budget": budget,
        "preferences": preferences,
        "travel_intensity": travel_intensity,
        "transport_preference": data.get("transport_preference", ""),
        "accommodation_preference": data.get("accommodation_preference", ""),
        "constraints": data.get("constraints", [])
    }


def requirement_agent(state: TravelState) -> TravelState:
    """
    需求解析 Agent 总入口：
    优先使用大模型解析，失败后使用规则兜底。
    """

    if llm_available():
        try:
            return llm_requirement_parse(state)
        except Exception as e:
            print(f"需求解析 Agent 大模型调用失败，使用规则兜底。错误信息：{e}")

    return rule_requirement_parse(state)
