from agents.state import TravelState


def time_agent(state: TravelState) -> TravelState:
    """
    时间规划 Agent：
    根据路径规划生成每天的时间表。
    """

    route_plan = state.get("route_plan", {})
    travel_intensity = state.get("travel_intensity", "适中")

    if travel_intensity == "轻松":
        start_activity = {
            "time": "10:00-10:30",
            "activity": "从酒店出发",
            "note": "轻松游建议晚一点出发，避免行程过累。"
        }
        max_pois = 3
        current_slots = [
            "10:30-12:00",
            "12:00-13:30",
            "13:30-15:00",
            "15:00-16:30",
            "16:30-18:00",
            "18:00-19:30",
            "19:30-21:00"
        ]

    elif travel_intensity == "紧凑":
        start_activity = {
            "time": "08:30-09:00",
            "activity": "从酒店出发",
            "note": "紧凑行程建议早点出发，提高游玩效率。"
        }
        max_pois = 5
        current_slots = [
            "09:00-10:30",
            "10:30-12:00",
            "12:00-13:30",
            "13:30-15:00",
            "15:00-16:30",
            "16:30-18:00",
            "18:00-19:30",
            "19:30-21:00"
        ]

    elif travel_intensity == "特种兵":
        start_activity = {
            "time": "07:30-08:00",
            "activity": "从酒店出发",
            "note": "特种兵式行程强度较高，请注意体力分配。"
        }
        max_pois = 6
        current_slots = [
            "08:00-09:30",
            "09:30-11:00",
            "11:00-12:30",
            "12:30-13:30",
            "13:30-15:00",
            "15:00-16:30",
            "16:30-18:00",
            "18:00-19:30",
            "19:30-21:00"
        ]

    else:
        start_activity = {
            "time": "09:00-09:30",
            "activity": "从酒店出发",
            "note": "根据住宿位置选择地铁、公交或打车。"
        }
        max_pois = 4
        current_slots = [
            "09:30-11:00",
            "11:00-12:00",
            "12:00-13:30",
            "13:30-15:00",
            "15:00-16:30",
            "16:30-18:00",
            "18:00-19:30",
            "19:30-21:00"
        ]

    time_plan = {}

    for day, pois in route_plan.items():
        day_schedule = []
        day_schedule.append(start_activity)

        limited_pois = pois[:max_pois]
        slot_index = 0
        lunch_added = False

        for poi_item in limited_pois:
            if slot_index >= len(current_slots):
                break

            # 到午餐时间时插入午餐
            if not lunch_added and slot_index >= 2:
                day_schedule.append({
                    "time": current_slots[slot_index],
                    "activity": "午餐与休息",
                    "note": "优先选择景点附近餐饮，减少跨区域移动时间。"
                })
                lunch_added = True
                slot_index += 1

                if slot_index >= len(current_slots):
                    break

            day_schedule.append({
                "time": current_slots[slot_index],
                "activity": f"游览 {poi_item['poi']}",
                "note": "建议根据现场排队情况和体力灵活调整。"
            })
            slot_index += 1

        if not lunch_added and slot_index < len(current_slots):
            day_schedule.append({
                "time": current_slots[slot_index],
                "activity": "午餐与休息",
                "note": "优先选择当日路线附近餐厅。"
            })
            slot_index += 1

        day_schedule.append({
            "time": "18:00以后",
            "activity": "晚餐/夜景/自由活动",
            "note": "根据当天体力选择是否继续游玩，夜景城市可安排晚间打卡。"
        })

        time_plan[day] = day_schedule

    return {
        **state,
        "time_plan": time_plan
    }