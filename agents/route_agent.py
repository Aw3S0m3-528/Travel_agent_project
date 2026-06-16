from agents.state import TravelState
from tools.map_tool import amap_available, estimate_route_for_pois


def split_pois_by_days(selected_pois, travel_days, destination=None):
    """
    将景点按天数分配。
    V0.4 优化版：
    - 优先使用城市路线模板；
    - 同一区域景点安排在同一天；
    - 模板外景点再平均分配。
    """

    if travel_days <= 0:
        travel_days = 1

    city_route_templates = {
        "重庆": [
            ["解放碑", "八一好吃街", "洪崖洞", "千厮门大桥"],
            ["李子坝轻轨站", "磁器口"]
        ],
        "成都": [
            ["宽窄巷子", "人民公园", "武侯祠", "锦里"],
            ["杜甫草堂", "春熙路", "太古里"]
        ],
        "西安": [
            ["钟楼", "鼓楼", "回民街"],
            ["陕西历史博物馆", "大雁塔", "大唐不夜城"]
        ]
    }

    route_plan = {}

    for day in range(1, travel_days + 1):
        route_plan[f"day_{day}"] = []

    used_pois = set()

    # 1. 优先使用城市模板
    if destination in city_route_templates:
        templates = city_route_templates[destination]

        for day_index in range(min(travel_days, len(templates))):
            day_key = f"day_{day_index + 1}"

            for poi in templates[day_index]:
                if poi in selected_pois and poi not in used_pois:
                    route_plan[day_key].append({
                        "poi": poi,
                        "area": "城市核心区域",
                        "transport": "地铁/步行/打车",
                        "duration": "约15-30分钟",
                        "distance": "待地图 API 估算",
                        "reason": "路线模板分配：将同一区域或适合同一天游览的景点串联。"
                    })
                    used_pois.add(poi)

    # 2. 剩余景点平均补充到每日路线
    remaining_pois = [
        poi for poi in selected_pois
        if poi not in used_pois
    ]

    for poi in remaining_pois:
        # 找当前景点数量最少的一天
        target_day = min(
            route_plan.keys(),
            key=lambda day_key: len(route_plan[day_key])
        )

        route_plan[target_day].append({
            "poi": poi,
            "area": "城市核心区域",
            "transport": "地铁/步行/打车",
            "duration": "约15-30分钟",
            "distance": "待地图 API 估算",
            "reason": "补充分配：该景点不在预设路线模板中，自动补充到景点较少的一天。"
        })

    return route_plan


def enrich_route_with_map_api(route_plan, destination):
    """
    使用高德地图 API 补充路线信息。
    """

    poi_locations_by_day = {}
    route_segments_by_day = {}

    for day, items in route_plan.items():
        poi_names = [item["poi"] for item in items]

        if len(poi_names) == 0:
            poi_locations_by_day[day] = []
            route_segments_by_day[day] = []
            continue

        result = estimate_route_for_pois(
            poi_names=poi_names,
            city=destination
        )

        poi_locations = result.get("poi_locations", [])
        route_segments = result.get("route_segments", [])

        poi_locations_by_day[day] = poi_locations
        route_segments_by_day[day] = route_segments

        # 给每个景点补充经纬度
        location_map = {
            item["name"]: item
            for item in poi_locations
        }

        for item in items:
            poi = item["poi"]
            loc = location_map.get(poi)

            if loc:
                item["location"] = loc.get("location")
                item["address"] = loc.get("formatted_address")
                item["district"] = loc.get("district")

        # 给每个景点补充到下一个景点的路线信息
        segment_map = {
            segment["from"]: segment
            for segment in route_segments
        }

        for item in items:
            poi = item["poi"]
            segment = segment_map.get(poi)

            if segment:
                item["next_poi"] = segment["to"]
                item["transport"] = segment["transport"]
                item["duration"] = f"约{segment['duration_min']}分钟" if segment["duration_min"] else "约15-30分钟"
                item["distance"] = f"约{segment['distance_km']}公里" if segment["distance_km"] else "距离暂未获取"
                item["reason"] = (
                    f"地图 API 估算：从 {segment['from']} 到 {segment['to']} "
                    f"建议{segment['transport']}，距离约 {segment['distance_km']} 公里，"
                    f"用时约 {segment['duration_min']} 分钟。"
                )

    return route_plan, poi_locations_by_day, route_segments_by_day


def route_agent(state: TravelState) -> TravelState:
    """
    路径规划 Agent：
    V0.4 接入高德地图 API，获取景点经纬度和相邻景点交通时间。
    """

    selected_pois = state.get("selected_pois", [])
    travel_days = state.get("travel_days", 3)
    destination = state.get("destination", "成都")

    route_plan = split_pois_by_days(selected_pois, travel_days, destination)

    poi_locations_by_day = {}
    route_segments_by_day = {}

    if amap_available():
        try:
            route_plan, poi_locations_by_day, route_segments_by_day = enrich_route_with_map_api(
                route_plan=route_plan,
                destination=destination
            )
        except Exception as e:
            print(f"路径规划 Agent：地图 API 调用失败，使用基础估算。错误信息：{e}")
    else:
        print("路径规划 Agent：未配置 AMAP_API_KEY，使用基础路线估算。")

    return {
        **state,
        "route_plan": route_plan,
        "poi_locations": poi_locations_by_day,
        "route_segments": route_segments_by_day
    }