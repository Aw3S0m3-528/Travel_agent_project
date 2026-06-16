from agents.state import TravelState


BUDGET_LEVELS = {
    "低预算": {
        "meal_per_person_day": 80,
        "hotel_per_room_night": 180,
        "transport_per_person_day": 30,
    },
    "中等预算": {
        "meal_per_person_day": 150,
        "hotel_per_room_night": 350,
        "transport_per_person_day": 60,
    },
    "高预算": {
        "meal_per_person_day": 300,
        "hotel_per_room_night": 800,
        "transport_per_person_day": 120,
    },
}

TICKET_ESTIMATES = {
    "free": 0,
    "partly_free": 20,
    "paid": 60,
    "paid_or_reservation": 60,
    "unknown": 30,
}


def normalize_budget_level(budget: str) -> str:
    if "低" in budget or "省钱" in budget:
        return "低预算"
    if "高" in budget or "奢" in budget:
        return "高预算"
    return "中等预算"


def estimate_ticket_budget(retrieved_info, people_count: int):
    details = []
    total = 0

    for item in retrieved_info:
        poi = item.get("poi", "")
        ticket_type = item.get("ticket_type", "unknown")
        unit_cost = TICKET_ESTIMATES.get(ticket_type, 30)
        subtotal = unit_cost * people_count
        total += subtotal

        details.append({
            "poi": poi,
            "ticket_type": ticket_type,
            "estimated_unit_cost": unit_cost,
            "estimated_total": subtotal,
            "note": item.get("ticket", "以官方信息为准")
        })

    return total, details


def budget_agent(state: TravelState) -> TravelState:
    """
    预算 Agent：
    根据预算档位、人数、天数和门票属性生成粗略预算区间。
    """

    travel_days = int(state.get("travel_days", 1) or 1)
    people_count = int(state.get("people_count", 1) or 1)
    budget_level = normalize_budget_level(state.get("budget", "中等预算"))
    level_config = BUDGET_LEVELS[budget_level]

    meal_total = level_config["meal_per_person_day"] * people_count * travel_days
    transport_total = level_config["transport_per_person_day"] * people_count * travel_days

    room_count = max(1, (people_count + 1) // 2)
    hotel_nights = max(1, travel_days - 1)
    hotel_total = level_config["hotel_per_room_night"] * room_count * hotel_nights

    ticket_total, ticket_details = estimate_ticket_budget(
        state.get("retrieved_info", []),
        people_count
    )

    subtotal = meal_total + transport_total + hotel_total + ticket_total
    low_total = int(subtotal * 0.85)
    high_total = int(subtotal * 1.2)

    budget_plan = {
        "budget_level": budget_level,
        "people_count": people_count,
        "travel_days": travel_days,
        "meal_total": meal_total,
        "transport_total": transport_total,
        "hotel_total": hotel_total,
        "ticket_total": ticket_total,
        "estimated_total_range": [low_total, high_total],
        "ticket_details": ticket_details,
        "notes": [
            "预算为规则估算，用于行程规划参考，不代表实时价格。",
            "免费开放景点按 0 元门票估算，部分免费或未知景点保留少量弹性预算。",
            "住宿按两人一间粗略估算，实际价格会受日期、商圈和节假日影响。"
        ]
    }

    return {
        **state,
        "budget_plan": budget_plan
    }
