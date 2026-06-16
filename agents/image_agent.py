from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.state import TravelState
from tools.image_search_tool import (
    build_commons_search_query,
    build_web_image_search_query,
    search_bing_image,
    search_commons_image,
    search_duckduckgo_image,
)


POI_IMAGE_QUERIES = {
    "宽窄巷子": "Chengdu Kuanzhai Alley travel",
    "人民公园": "Chengdu People's Park tea house",
    "武侯祠": "Chengdu Wuhou Shrine",
    "锦里": "Chengdu Jinli Ancient Street",
    "杜甫草堂": "Chengdu Du Fu Thatched Cottage",
    "春熙路": "Chengdu Chunxi Road",
    "太古里": "Chengdu Taikoo Li",
    "解放碑": "Chongqing Jiefangbei",
    "八一好吃街": "Chongqing food street",
    "洪崖洞": "Chongqing Hongyadong night view",
    "千厮门大桥": "Chongqing Qiansimen Bridge night",
    "磁器口": "Chongqing Ciqikou Ancient Town",
    "李子坝轻轨站": "Chongqing Liziba monorail",
    "钟楼": "Xi'an Bell Tower",
    "鼓楼": "Xi'an Drum Tower",
    "回民街": "Xi'an Muslim Quarter food street",
    "陕西历史博物馆": "Shaanxi History Museum Xi'an",
    "大雁塔": "Xi'an Giant Wild Goose Pagoda",
    "大唐不夜城": "Xi'an Grand Tang Mall night",
}


def search_image_for_poi(poi: str, destination: str):
    query_hint = POI_IMAGE_QUERIES.get(poi, "")
    commons_query = build_commons_search_query(
        poi_name=poi,
        city=destination,
        query_hint=query_hint
    )
    web_query = build_web_image_search_query(
        poi_name=poi,
        city=destination,
        query_hint=query_hint
    )

    image_source = {}

    try:
        image_result = search_commons_image(commons_query)
    except Exception as exc:
        image_result = None
        image_source = {
            "query": commons_query,
            "source": "Wikimedia Commons",
            "status": "error",
            "error": str(exc),
            "license_note": "Wikimedia Commons 图片搜索失败。"
        }

    if not image_result:
        try:
            image_result = search_duckduckgo_image(web_query)
        except Exception as exc:
            image_result = None
            previous_error = image_source.get("error", "")
            image_source = {
                "query": web_query,
                "source": "DuckDuckGo Images 网页爬取",
                "status": "error",
                "error": f"{previous_error}; {exc}".strip("; "),
                "license_note": "网页图片爬取失败，未展示占位图。"
            }

    if not image_result:
        try:
            image_result = search_bing_image(web_query)
        except Exception as exc:
            image_result = None
            previous_error = image_source.get("error", "")
            image_source = {
                "query": web_query,
                "source": "Bing Images 网页爬取",
                "status": "error",
                "error": f"{previous_error}; {exc}".strip("; "),
                "license_note": "网页图片爬取失败，未展示占位图。"
            }

    if image_result:
        return poi, image_result["url"], {
            **image_result,
            "status": "found"
        }

    if not image_source:
        image_source = {
            "query": web_query,
            "source": "Bing Images 网页爬取",
            "status": "not_found",
            "license_note": "未搜索到可直接展示的网络图片。"
        }

    return poi, "", image_source


def image_agent(state: TravelState) -> TravelState:
    """
    图片检索 Agent：
    优先通过 Wikimedia Commons 搜索景点图片。
    如果命中率不足，则通过 DuckDuckGo / Bing 图片搜索结果爬取相关原图，用于学习演示。
    """

    selected_pois = state.get("selected_pois", [])
    destination = state.get("destination", "")

    images = {}
    image_sources = {}

    max_workers = min(4, max(1, len(selected_pois)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(search_image_for_poi, poi, destination)
            for poi in selected_pois
        ]

        for future in as_completed(futures):
            poi, image_url, image_source = future.result()
            if image_url:
                images[poi] = image_url
            image_sources[poi] = image_source

    return {
        **state,
        "images": images,
        "image_sources": image_sources
    }
