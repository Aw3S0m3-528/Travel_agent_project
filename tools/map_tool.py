import os
import time
import math
import requests
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv


load_dotenv()


AMAP_POI_TEXT_URL = "https://restapi.amap.com/v3/place/text"
AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
AMAP_WALKING_URL = "https://restapi.amap.com/v3/direction/walking"
AMAP_DRIVING_URL = "https://restapi.amap.com/v3/direction/driving"

POI_ALIASES = {
    "李子坝轻轨站": [
        "李子坝单轨穿楼观景平台",
        "李子坝轻轨穿楼观景平台",
        "重庆轨道交通李子坝站",
        "李子坝站",
        "李子坝"
    ],
    "洪崖洞": [
        "洪崖洞民俗风貌区",
        "洪崖洞"
    ],
    "千厮门大桥": [
        "千厮门大桥",
        "重庆千厮门大桥"
    ],
    "八一好吃街": [
        "八一好吃街",
        "八一路好吃街"
    ],
    "解放碑": [
        "解放碑步行街",
        "解放碑"
    ],
    "磁器口": [
        "磁器口古镇",
        "磁器口"
    ]
}


NEGATIVE_NAME_KEYWORDS = [
    "酒店", "宾馆", "民宿", "公寓", "客栈", "旅馆", "停车场", "售楼处"
]


POSITIVE_NAME_KEYWORDS = [
    "景区", "风景区", "风貌区", "观景", "观景台",
    "步行街", "古镇", "大桥", "车站", "轻轨", "轨道", "单轨"
]

def get_amap_key() -> str:
    key = os.getenv("AMAP_API_KEY", "").strip()
    if not key:
        raise ValueError("未配置 AMAP_API_KEY，请在 .env 文件中添加高德 Web 服务 Key。")
    return key


def amap_available() -> bool:
    return bool(os.getenv("AMAP_API_KEY", "").strip())


def haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """
    计算两个经纬度点之间的直线距离，单位：公里。
    用于提前过滤明显错误的跨城市坐标。
    """
    radius = 6371.0

    lng1, lat1, lng2, lat2 = map(math.radians, [lng1, lat1, lng2, lat2])

    dlng = lng2 - lng1
    dlat = lat2 - lat1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )

    c = 2 * math.asin(math.sqrt(a))

    return radius * c


def get_poi_search_keywords(poi_name: str) -> List[str]:
    """
    获取某个景点的搜索关键词。
    对容易误匹配的景点使用别名增强搜索。
    """
    return POI_ALIASES.get(poi_name, [poi_name])


def score_poi_candidate(
    poi: Dict[str, Any],
    poi_name: str,
    keyword: str,
    city: str
) -> int:
    """
    给 POI 候选结果打分，避免把景点误匹配成酒店、民宿、公寓等。
    """

    name = str(poi.get("name", ""))
    cityname = str(poi.get("cityname", ""))
    poi_type = str(poi.get("type", ""))
    address = str(poi.get("address", ""))

    score = 0

    # 城市匹配加分
    if city in cityname:
        score += 30

    # 名称匹配加分
    if name == keyword:
        score += 60
    elif keyword in name:
        score += 40
    elif poi_name in name:
        score += 30

    # 别名匹配加分
    for alias in get_poi_search_keywords(poi_name):
        if alias == name:
            score += 50
        elif alias in name:
            score += 35

    # 正向关键词加分
    if any(good in name for good in POSITIVE_NAME_KEYWORDS):
        score += 20

    if any(good in poi_type for good in ["风景名胜", "交通设施", "道路附属设施", "地名地址信息"]):
        score += 20

    # 酒店、民宿、公寓等强烈扣分
    if any(bad in name for bad in NEGATIVE_NAME_KEYWORDS):
        score -= 120

    if "住宿服务" in poi_type or "酒店" in poi_type:
        score -= 120

    # 针对李子坝轻轨站做特殊保护
    if poi_name == "李子坝轻轨站":
        if any(word in name for word in ["观景", "李子坝站", "轨道", "轻轨", "单轨"]):
            score += 120

        if any(bad in name for bad in ["酒店", "宾馆", "公寓", "民宿"]):
            score -= 200

    return score


def search_poi_by_text(poi_name: str, city: str) -> Optional[Dict[str, Any]]:
    """
    使用高德 POI 关键字搜索接口查询景点。
    优先使用别名搜索，并通过打分机制避免误匹配酒店。
    """

    if not amap_available():
        return None

    try:
        key = get_amap_key()
        keywords = get_poi_search_keywords(poi_name)

        all_candidates = []

        for keyword in keywords:
            params = {
                "key": key,
                "keywords": keyword,
                "city": city,
                "citylimit": "true",
                "extensions": "base",
                "offset": 10,
                "page": 1,
                "output": "json"
            }

            response = requests.get(
                AMAP_POI_TEXT_URL,
                params=params,
                timeout=10
            )

            data = response.json()

            if data.get("status") != "1":
                print(f"POI搜索失败：{keyword}，返回：{data}")
                continue

            pois = data.get("pois", [])

            for poi in pois:
                score = score_poi_candidate(
                    poi=poi,
                    poi_name=poi_name,
                    keyword=keyword,
                    city=city
                )

                all_candidates.append({
                    "score": score,
                    "keyword": keyword,
                    "poi": poi
                })

            time.sleep(0.1)

        if not all_candidates:
            print(f"POI搜索未找到：{city} {poi_name}")
            return None

        all_candidates.sort(key=lambda x: x["score"], reverse=True)

        best = all_candidates[0]
        best_poi = best["poi"]

        location = best_poi.get("location", "")

        if not location:
            return None

        lng, lat = location.split(",")

        print(
            f"POI候选选择：{poi_name} -> {best_poi.get('name')}，"
            f"得分：{best['score']}，搜索词：{best['keyword']}"
        )

        return {
            "name": poi_name,
            "amap_name": best_poi.get("name", poi_name),
            "formatted_address": best_poi.get("address", ""),
            "province": best_poi.get("pname", ""),
            "city": best_poi.get("cityname", city),
            "district": best_poi.get("adname", ""),
            "location": location,
            "lng": float(lng),
            "lat": float(lat),
            "source": "poi_search"
        }

    except Exception as e:
        print(f"POI搜索异常：{poi_name}，错误：{e}")
        return None


def geocode_poi_fallback(poi_name: str, city: str) -> Optional[Dict[str, Any]]:
    """
    地理编码兜底。
    注意：这个接口可能把 POI 匹配到错误城市，所以只作为兜底。
    """

    if not amap_available():
        return None

    try:
        key = get_amap_key()

        address = f"{city}{poi_name}"

        params = {
            "key": key,
            "address": address,
            "city": city,
            "output": "json"
        }

        response = requests.get(
            AMAP_GEOCODE_URL,
            params=params,
            timeout=10
        )

        data = response.json()

        if data.get("status") != "1":
            print(f"地理编码失败：{address}，返回：{data}")
            return None

        geocodes = data.get("geocodes", [])

        if not geocodes:
            print(f"未找到经纬度：{address}")
            return None

        item = geocodes[0]
        location = item.get("location", "")

        if not location:
            return None

        lng, lat = location.split(",")

        return {
            "name": poi_name,
            "amap_name": item.get("formatted_address", poi_name),
            "formatted_address": item.get("formatted_address", poi_name),
            "province": item.get("province", ""),
            "city": item.get("city", city),
            "district": item.get("district", ""),
            "location": location,
            "lng": float(lng),
            "lat": float(lat),
            "source": "geocode_fallback"
        }

    except Exception as e:
        print(f"地理编码异常：{poi_name}，错误：{e}")
        return None


def geocode_poi(poi_name: str, city: str) -> Optional[Dict[str, Any]]:
    """
    景点经纬度查询总入口：
    优先使用 POI 搜索，失败后使用地理编码兜底。
    """

    result = search_poi_by_text(poi_name, city)

    if result:
        return result

    return geocode_poi_fallback(poi_name, city)


def get_route_between(
    origin_location: str,
    destination_location: str,
    mode: str = "walking"
) -> Optional[Dict[str, Any]]:
    """
    查询两个地点之间的路线。
    """

    if not amap_available():
        return None

    try:
        key = get_amap_key()

        if mode == "driving":
            url = AMAP_DRIVING_URL
        else:
            url = AMAP_WALKING_URL

        params = {
            "key": key,
            "origin": origin_location,
            "destination": destination_location,
            "output": "json"
        }

        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        data = response.json()

        if data.get("status") != "1":
            print(f"路径规划失败：{origin_location} -> {destination_location}，返回：{data}")
            return None

        route = data.get("route", {})
        paths = route.get("paths", [])

        if not paths:
            return None

        path = paths[0]

        distance_m = int(float(path.get("distance", 0)))
        duration_s = int(float(path.get("duration", 0)))

        return {
            "mode": "驾车" if mode == "driving" else "步行",
            "distance_m": distance_m,
            "distance_km": round(distance_m / 1000, 2),
            "duration_s": duration_s,
            "duration_min": max(1, round(duration_s / 60)),
            "raw": path
        }

    except Exception as e:
        print(f"路径规划异常：{origin_location} -> {destination_location}，错误：{e}")
        return None


def choose_transport_by_distance(distance_km: float) -> str:
    if distance_km <= 1.2:
        return "步行"
    elif distance_km <= 5:
        return "地铁/公交/打车"
    else:
        return "打车/地铁"


def estimate_route_for_pois(
    poi_names: List[str],
    city: str
) -> Dict[str, Any]:
    """
    对一天中的多个景点进行经纬度查询，并估算相邻景点之间的路线。
    """

    poi_locations = []
    route_segments = []

    for poi in poi_names:
        location = geocode_poi(poi, city)

        if location:
            poi_locations.append(location)
            print(
                f"地图定位成功：{poi} -> {location.get('amap_name')}，"
                f"{location.get('location')}，来源：{location.get('source')}"
            )
        else:
            print(f"地图定位失败：{city} {poi}")

        time.sleep(0.15)

    for index in range(len(poi_locations) - 1):
        current_poi = poi_locations[index]
        next_poi = poi_locations[index + 1]

        straight_distance = haversine_km(
            current_poi["lng"],
            current_poi["lat"],
            next_poi["lng"],
            next_poi["lat"]
        )

        # 如果两个点直线距离超过 80 公里，基本可以认为坐标识别错了，不调用路径规划
        if straight_distance > 80:
            print(
                f"跳过异常路线：{current_poi['name']} -> {next_poi['name']}，"
                f"直线距离约 {round(straight_distance, 2)} 公里，疑似坐标识别错误。"
            )

            route_segments.append({
                "from": current_poi["name"],
                "to": next_poi["name"],
                "from_location": current_poi["location"],
                "to_location": next_poi["location"],
                "transport": "地铁/公交/打车",
                "route_mode": "坐标异常，基础估算",
                "distance_km": None,
                "duration_min": None
            })

            continue

        origin = current_poi["location"]
        destination = next_poi["location"]

        walking_route = get_route_between(origin, destination, mode="walking")
        time.sleep(0.15)

        if walking_route:
            distance_km = walking_route["distance_km"]

            if distance_km > 2.0:
                driving_route = get_route_between(origin, destination, mode="driving")
                time.sleep(0.15)

                if driving_route:
                    route_info = driving_route
                else:
                    route_info = walking_route
            else:
                route_info = walking_route

            recommended_transport = choose_transport_by_distance(route_info["distance_km"])

            route_segments.append({
                "from": current_poi["name"],
                "to": next_poi["name"],
                "from_location": current_poi["location"],
                "to_location": next_poi["location"],
                "transport": recommended_transport,
                "route_mode": route_info["mode"],
                "distance_km": route_info["distance_km"],
                "duration_min": route_info["duration_min"]
            })
        else:
            route_segments.append({
                "from": current_poi["name"],
                "to": next_poi["name"],
                "from_location": current_poi["location"],
                "to_location": next_poi["location"],
                "transport": "地铁/公交/打车",
                "route_mode": "路径规划失败，基础估算",
                "distance_km": None,
                "duration_min": None
            })

    return {
        "poi_locations": poi_locations,
        "route_segments": route_segments
    }