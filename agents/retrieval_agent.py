from agents.state import TravelState
from tools.rag_tool import retrieve_travel_info, format_rag_results
from tools.web_search_tool import (
    build_recent_travel_query,
    format_online_results,
    rank_search_results,
    search_recent_travel_web,
)


LOCAL_FACT_KEYWORDS = ["开放时间", "门票", "预约", "交通", "住宿", "路线", "美食"]


POI_FACTS = {
    "宽窄巷子": {
        "open_time": "开放式街区，通常全天可进入，店铺营业时间各不相同",
        "ticket": "通常免费开放，街区游览不需要门票",
        "ticket_type": "free",
        "notice": "商业店铺和展馆可能有各自营业时间，建议以现场信息为准"
    },
    "人民公园": {
        "open_time": "城市公园，通常白天至晚间开放，具体以园区公告为准",
        "ticket": "通常免费开放",
        "ticket_type": "free",
        "notice": "茶馆和游船等体验项目可能单独收费"
    },
    "锦里": {
        "open_time": "开放式古街，通常全天可进入，商铺营业时间各不相同",
        "ticket": "通常免费开放，街区游览不需要门票",
        "ticket_type": "free",
        "notice": "靠近武侯祠，可与武侯祠串联；节假日人流较多"
    },
    "春熙路": {
        "open_time": "开放式商圈，通常全天可进入，商铺营业时间各不相同",
        "ticket": "免费开放的城市商圈",
        "ticket_type": "free",
        "notice": "适合购物、餐饮和夜间活动，注意高峰时段人流"
    },
    "太古里": {
        "open_time": "开放式商业街区，商铺营业时间各不相同",
        "ticket": "免费开放的商业街区",
        "ticket_type": "free",
        "notice": "适合购物、餐饮和拍照，消费项目按店铺收费"
    },
    "解放碑": {
        "open_time": "开放式城市商圈，通常全天可到访",
        "ticket": "免费开放的城市地标和商圈",
        "ticket_type": "free",
        "notice": "周边餐饮和商业密集，夜间与节假日人流较多"
    },
    "八一好吃街": {
        "open_time": "开放式美食街，摊位和店铺营业时间各不相同",
        "ticket": "免费进入，美食消费按店铺单独付费",
        "ticket_type": "free",
        "notice": "适合安排午餐或晚餐，高峰时段排队较多"
    },
    "洪崖洞": {
        "open_time": "开放式景区和商业街区，夜景时段体验更好，具体灯光时间以现场为准",
        "ticket": "通常免费开放，进入公共区域一般不需要门票",
        "ticket_type": "free",
        "notice": "节假日人流非常密集，建议错峰前往并注意单向通行安排"
    },
    "千厮门大桥": {
        "open_time": "城市桥梁和观景点，通常全天可远观或通行",
        "ticket": "免费开放的城市观景点",
        "ticket_type": "free",
        "notice": "适合拍摄洪崖洞夜景，注意桥面通行安全和人流"
    },
    "李子坝轻轨站": {
        "open_time": "观景平台通常白天至晚间可到访，轨道交通运营时间以官方为准",
        "ticket": "观景平台通常免费；乘坐轨道交通需按票价购票",
        "ticket_type": "partly_free",
        "notice": "适合短时间打卡，建议白天前往拍摄轻轨穿楼"
    },
    "磁器口": {
        "open_time": "开放式古镇街区，通常全天可进入，商铺营业时间各不相同",
        "ticket": "通常免费开放，街区游览不需要门票",
        "ticket_type": "free",
        "notice": "节假日游客较多，建议上午或非高峰时段前往"
    },
    "武侯祠": {
        "open_time": "开放时间和入园规则建议出行前查看官方公告",
        "ticket": "通常为收费景点，建议提前确认票价和预约规则",
        "ticket_type": "paid",
        "notice": "适合喜欢三国历史文化的游客，节假日建议提前预约"
    },
    "杜甫草堂": {
        "open_time": "开放时间建议出行前查看官方公告",
        "ticket": "通常为收费景点，建议提前确认票价和预约规则",
        "ticket_type": "paid",
        "notice": "适合文学、历史和园林爱好者，建议预留 1.5-2 小时"
    }
}


def find_poi_context_from_rag(poi: str, rag_results):
    matched_parts = []

    for item in rag_results:
        content = item.get("content", "")
        if poi not in content:
            continue

        start = max(content.find(poi) - 80, 0)
        end = min(content.find(poi) + 220, len(content))
        matched_parts.append(content[start:end])

    return "\n".join(matched_parts)


def infer_ticket_from_text(text: str):
    if not text:
        return {}

    free_keywords = ["免费开放", "免费进入", "免门票", "无需门票", "不需要门票", "免费"]
    paid_keywords = ["收费", "购票", "门票", "票价", "需预约", "预约"]

    if any(keyword in text for keyword in free_keywords):
        return {
            "ticket": "RAG 资料显示为免费或免门票景点，建议出行前再次确认",
            "ticket_type": "free"
        }

    if any(keyword in text for keyword in paid_keywords):
        return {
            "ticket": "RAG 资料提示涉及门票或预约信息，建议出行前查看官方渠道确认",
            "ticket_type": "paid_or_reservation"
        }

    return {}


def build_poi_info(poi: str, rag_results):
    base_info = {
        "poi": poi,
        "open_time": "建议出行前查询官方开放时间",
        "ticket": "以官方信息为准",
        "ticket_type": "unknown",
        "notice": "节假日建议提前预约或错峰出行"
    }

    if poi in POI_FACTS:
        base_info.update(POI_FACTS[poi])

    poi_context = find_poi_context_from_rag(poi, rag_results)
    inferred_ticket = infer_ticket_from_text(poi_context)
    base_info.update(inferred_ticket)

    if poi_context:
        base_info["rag_evidence"] = poi_context

    return base_info


def score_local_rag_results(rag_results, destination: str):
    scored_results = []

    for item in rag_results:
        content = item.get("content", "")
        metadata = item.get("metadata", {})
        score = int(item.get("score", 0) or 0)
        reasons = []

        if metadata.get("city") == destination:
            score += 20
            reasons.append("匹配目的地本地资料")

        matched_keywords = [keyword for keyword in LOCAL_FACT_KEYWORDS if keyword in content]
        if matched_keywords:
            score += min(21, len(matched_keywords) * 7)
            reasons.append("包含结构化旅游信息：" + "、".join(matched_keywords[:3]))

        scored_results.append({
            **item,
            "score": score,
            "score_reasons": reasons or ["本地知识库资料"],
        })

    return sorted(scored_results, key=lambda current: current.get("score", 0), reverse=True)


def build_source_summary(rag_sources, online_sources, limit: int = 8):
    summary = []

    for item in rag_sources:
        metadata = item.get("metadata", {})
        summary.append({
            "type": "local_rag",
            "title": metadata.get("filename") or metadata.get("source", "本地知识库资料"),
            "url": "",
            "source": metadata.get("source", ""),
            "score": item.get("score", 0),
            "score_reasons": item.get("score_reasons", []),
        })

    for item in online_sources:
        summary.append({
            "type": "online",
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "source": item.get("source", ""),
            "score": item.get("score", 0),
            "score_reasons": item.get("score_reasons", []),
        })

    summary.sort(key=lambda item: item.get("score", 0), reverse=True)
    return summary[:limit]


def build_retrieval_quality(rag_sources, online_sources, selected_pois):
    high_score_sources = [
        item for item in [*rag_sources, *online_sources]
        if item.get("score", 0) >= 50
    ]
    has_dynamic_info = any(
        any(keyword in " ".join(item.get("score_reasons", [])) for keyword in ["动态旅游信息", "新鲜度", "公告"])
        for item in online_sources
    )

    return {
        "local_source_count": len(rag_sources),
        "online_source_count": len(online_sources),
        "high_score_source_count": len(high_score_sources),
        "selected_poi_count": len(selected_pois),
        "has_dynamic_info": has_dynamic_info,
        "freshness_note": (
            "已优先检索近两年、官方、公告、门票和开放时间相关资料。"
            if online_sources
            else "未命中联网资料，动态信息需要出行前再次确认。"
        ),
    }


def retrieve_online_travel_info(destination: str, selected_pois, max_pois: int = 3):
    online_results = []

    search_queries = [
        build_recent_travel_query(destination)
    ]

    for poi in selected_pois[:max_pois]:
        search_queries.append(build_recent_travel_query(destination, poi))

    query_poi_map = {build_recent_travel_query(destination): ""}
    for poi in selected_pois[:max_pois]:
        query_poi_map[build_recent_travel_query(destination, poi)] = poi

    for query in search_queries:
        try:
            results = search_recent_travel_web(query, limit=3)
        except Exception as exc:
            print(f"联网检索失败：{query}，错误：{exc}")
            continue

        ranked_results = rank_search_results(
            results,
            destination=destination,
            poi=query_poi_map.get(query, ""),
        )

        for result in ranked_results:
            if result.get("url") not in {item.get("url") for item in online_results}:
                online_results.append(result)

    return sorted(online_results, key=lambda item: item.get("score", 0), reverse=True)


def retrieval_agent(state: TravelState) -> TravelState:
    """
    信息检索 Agent：
    V0.3 版本接入本地 RAG 知识库。
    同时保留基础候选景点兜底，防止 RAG 未构建时系统无法运行。
    """

    destination = state.get("destination", "成都")
    preferences = state.get("preferences", [])
    budget = state.get("budget", "中等预算")
    travel_intensity = state.get("travel_intensity", "适中")

    city_pois = {
        "成都": ["宽窄巷子", "人民公园", "武侯祠", "锦里", "杜甫草堂", "春熙路", "太古里"],
        "重庆": ["解放碑", "八一好吃街", "洪崖洞", "千厮门大桥", "磁器口", "李子坝轻轨站"],
        "西安": ["钟楼", "鼓楼", "回民街", "陕西历史博物馆", "大雁塔", "大唐不夜城"],
        "北京": ["天安门广场", "故宫", "景山公园", "南锣鼓巷", "颐和园", "天坛"],
        "杭州": ["西湖", "断桥残雪", "雷峰塔", "灵隐寺", "河坊街", "南宋御街"],
        "东京": ["浅草寺", "上野公园", "秋叶原", "银座", "东京塔", "涩谷"]
    }

    selected_pois = city_pois.get(destination, ["城市核心景点", "当地美食街", "代表性博物馆"])

    # RAG 检索 query
    rag_query = (
        f"{destination} 旅游攻略 景点 开放时间 门票 预约 "
        f"美食 住宿 路线 行程安排 "
        f"用户偏好：{'、'.join(preferences)} "
        f"预算：{budget} "
        f"强度：{travel_intensity}"
    )

    rag_results = score_local_rag_results(
        retrieve_travel_info(rag_query, k=6),
        destination=destination,
    )
    local_rag_context = format_rag_results(rag_results)

    online_sources = retrieve_online_travel_info(destination, selected_pois)
    online_rag_context = format_online_results(online_sources)

    rag_context = (
        "【本地知识库检索】\n"
        f"{local_rag_context}\n\n"
        "【近两年联网资料检索】\n"
        f"{online_rag_context}"
    )

    retrieved_info = [
        build_poi_info(poi, rag_results)
        for poi in selected_pois
    ]
    source_summary = build_source_summary(rag_results, online_sources)
    retrieval_quality = build_retrieval_quality(rag_results, online_sources, selected_pois)

    return {
        **state,
        "candidate_pois": selected_pois,
        "selected_pois": selected_pois,
        "retrieved_info": retrieved_info,
        "rag_context": rag_context,
        "rag_sources": rag_results,
        "online_sources": online_sources,
        "source_summary": source_summary,
        "retrieval_quality": retrieval_quality
    }
