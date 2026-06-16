from agents.state import TravelState


INTENSITY_LIMITS = {
    "轻松": 3,
    "适中": 4,
    "紧凑": 5,
    "特种兵": 6,
}

REQUIRED_GUIDE_KEYWORDS = [
    "行程概览",
    "每日行程",
    "景点介绍",
    "餐饮",
    "住宿",
    "注意事项",
    "资料来源",
]


def _count_route_pois(route_plan):
    return {
        day: len(items)
        for day, items in route_plan.items()
    }


def _count_schedule_activities(time_plan):
    return {
        day: len(items)
        for day, items in time_plan.items()
    }


def _format_items(title, items):
    if not items:
        return f"### {title}\n- 无"

    lines = [f"### {title}"]
    lines.extend([f"- {item}" for item in items])
    return "\n".join(lines)


def _clamp_score(score: int) -> int:
    return max(0, min(100, score))


def build_review_scores(state, warnings, suggestions):
    route_plan = state.get("route_plan", {})
    time_plan = state.get("time_plan", {})
    route_segments = state.get("route_segments", {})
    rag_sources = state.get("rag_sources", [])
    online_sources = state.get("online_sources", [])
    retrieval_quality = state.get("retrieval_quality", {})
    images = state.get("images", {})
    selected_pois = state.get("selected_pois", [])
    budget_plan = state.get("budget_plan", {})

    executability = 90
    comfort = 88
    credibility = 78
    budget_reasonability = 80

    if not route_plan:
        executability -= 25
    if not time_plan:
        executability -= 25
    if not route_segments:
        executability -= 10
    if warnings:
        executability -= min(20, len(warnings) * 4)

    if any("超过" in warning or "偏多" in warning for warning in warnings):
        comfort -= 18
    if any("没有安排景点" in warning for warning in warnings):
        comfort -= 15

    if rag_sources:
        credibility += 8
    if online_sources:
        credibility += 10
    if retrieval_quality.get("high_score_source_count", 0):
        credibility += min(10, retrieval_quality.get("high_score_source_count", 0) * 2)
    if retrieval_quality.get("has_dynamic_info"):
        credibility += 5
    if not rag_sources and not online_sources:
        credibility -= 20
    if selected_pois and len(images) < len(selected_pois):
        credibility -= 8

    if budget_plan:
        budget_reasonability += 12
    else:
        budget_reasonability -= 20
    if any("门票" in suggestion and "确认" in suggestion for suggestion in suggestions):
        budget_reasonability -= 5

    scores = {
        "可执行性": _clamp_score(executability),
        "舒适度": _clamp_score(comfort),
        "信息可信度": _clamp_score(credibility),
        "预算合理性": _clamp_score(budget_reasonability),
    }
    scores["综合评分"] = round(sum(scores.values()) / len(scores))

    return scores


def format_review_scores(scores):
    lines = ["### 评分总览"]
    for key, value in scores.items():
        lines.append(f"- {key}：{value}/100")
    return "\n".join(lines)


def validator_agent(state: TravelState) -> TravelState:
    """
    校验 Agent：
    检查行程密度、路线完整性、RAG 命中、地图补充和最终攻略完整性。
    """

    travel_days = state.get("travel_days", 3)
    selected_pois = state.get("selected_pois", [])
    travel_intensity = state.get("travel_intensity", "适中")
    route_plan = state.get("route_plan", {})
    time_plan = state.get("time_plan", {})
    rag_sources = state.get("rag_sources", [])
    online_sources = state.get("online_sources", [])
    source_summary = state.get("source_summary", [])
    retrieval_quality = state.get("retrieval_quality", {})
    rag_context = state.get("rag_context", "")
    poi_locations = state.get("poi_locations", {})
    route_segments = state.get("route_segments", {})
    images = state.get("images", {})
    image_sources = state.get("image_sources", {})
    final_guide = state.get("final_guide", "")

    passed = []
    warnings = []
    suggestions = []

    if travel_days <= 0:
        warnings.append("出行天数小于等于 0，已无法形成可靠的每日行程。")
    else:
        passed.append(f"已识别出行天数：{travel_days} 天。")

    if selected_pois:
        passed.append(f"已选择 {len(selected_pois)} 个候选景点。")
    else:
        warnings.append("未识别到候选景点，需要补充目的地资料或扩展景点库。")

    if not route_plan:
        warnings.append("缺少 route_plan，路径规划 Agent 可能未正常返回结果。")
    else:
        route_counts = _count_route_pois(route_plan)
        empty_days = [day for day, count in route_counts.items() if count == 0]

        if empty_days:
            warnings.append(f"以下日期没有安排景点：{', '.join(empty_days)}。")
        else:
            passed.append("每日路线均已安排景点。")

        max_pois = INTENSITY_LIMITS.get(travel_intensity, 4)

        for day, count in route_counts.items():
            if count > max_pois:
                warnings.append(
                    f"{day} 安排了 {count} 个景点，超过“{travel_intensity}”强度建议上限 {max_pois} 个。"
                )

        if travel_days and selected_pois:
            avg_pois = len(selected_pois) / travel_days
            if avg_pois > max_pois:
                warnings.append(
                    f"平均每日约 {avg_pois:.1f} 个景点，超过“{travel_intensity}”强度建议上限。"
                )
            else:
                passed.append(f"平均每日景点数量约 {avg_pois:.1f} 个，符合“{travel_intensity}”强度。")

    if not time_plan:
        warnings.append("缺少 time_plan，时间规划 Agent 可能未正常返回结果。")
    else:
        schedule_counts = _count_schedule_activities(time_plan)
        empty_schedules = [day for day, count in schedule_counts.items() if count == 0]

        if empty_schedules:
            warnings.append(f"以下日期没有时间表：{', '.join(empty_schedules)}。")
        else:
            passed.append("每日时间表均已生成。")

        missing_route_days = sorted(set(route_plan.keys()) - set(time_plan.keys()))
        if missing_route_days:
            warnings.append(f"这些路线日期缺少对应时间表：{', '.join(missing_route_days)}。")

    if rag_sources:
        passed.append(f"RAG 知识库命中 {len(rag_sources)} 条资料。")
    elif "未从本地 RAG 知识库中检索到相关资料" in rag_context:
        warnings.append("本地 RAG 知识库未命中相关资料，攻略主要依赖规则和模型常识。")
        suggestions.append("建议补充当前目的地的 raw_docs 文档后重新构建向量库。")
    else:
        suggestions.append("未检测到 RAG 来源列表，可检查检索工具是否返回 rag_sources。")

    if online_sources:
        passed.append(f"联网检索命中 {len(online_sources)} 条近两年相关资料。")
    else:
        suggestions.append("未命中联网资料或联网检索失败，动态信息仍需出行前再次确认。")

    if source_summary:
        passed.append(f"已生成 {len(source_summary)} 条资料来源摘要，并按相关性评分排序。")
    else:
        suggestions.append("未生成资料来源摘要，建议检查 Retrieval Agent 的 source_summary 输出。")

    if retrieval_quality.get("has_dynamic_info"):
        passed.append("检索结果包含开放时间、门票、预约或公告等动态旅游信息。")
    else:
        suggestions.append("动态旅游信息覆盖不足，开放时间和门票规则仍需出行前确认官方公告。")

    route_segment_count = sum(len(items) for items in route_segments.values()) if route_segments else 0
    location_count = sum(len(items) for items in poi_locations.values()) if poi_locations else 0

    if route_segment_count:
        passed.append(f"地图工具已补充 {route_segment_count} 段景点间路线。")
    else:
        suggestions.append("未检测到地图路线段，可能未配置 AMAP_API_KEY 或地图 API 未命中。")

    if selected_pois and location_count and location_count < len(selected_pois):
        warnings.append(
            f"地图工具仅定位到 {location_count}/{len(selected_pois)} 个景点，部分景点地址或交通时间可能不准确。"
        )
    elif selected_pois and location_count >= len(selected_pois):
        passed.append("地图工具已为所有选中景点补充位置信息。")

    if selected_pois and images:
        image_count = sum(1 for poi in selected_pois if images.get(poi))
        if image_count == len(selected_pois):
            passed.append("已为所有选中景点搜索到可展示图片。")
        else:
            warnings.append(f"仅为 {image_count}/{len(selected_pois)} 个景点搜索到可展示图片。")

        if image_sources:
            suggestions.append("图片来自 Wikimedia Commons 或 DuckDuckGo/Bing 图片搜索爬取结果，仅适合学习演示；正式发布前建议逐张确认授权、作者和来源标注。")
    elif selected_pois:
        warnings.append("未搜索到景点图片链接，图文攻略展示效果会受影响。")

    if image_sources:
        failed_images = [
            poi for poi, source in image_sources.items()
            if source.get("status") in {"not_found", "error"}
        ]
        if failed_images:
            warnings.append(f"以下景点图片搜索未命中或失败：{'、'.join(failed_images)}。")

    if not final_guide:
        warnings.append("最终攻略内容为空。")
    else:
        missing_keywords = [
            keyword for keyword in REQUIRED_GUIDE_KEYWORDS
            if keyword not in final_guide
        ]

        if missing_keywords:
            warnings.append(f"最终攻略缺少关键内容：{'、'.join(missing_keywords)}。")
        else:
            passed.append("最终攻略包含行程、景点、餐饮住宿和注意事项等关键内容。")

    if not warnings:
        warnings.append("未发现明显行程风险。")

    if not suggestions:
        suggestions.append("可根据用户反馈继续微调景点数量、住宿区域和餐饮安排。")

    review_scores = build_review_scores(state, warnings, suggestions)

    validation_result = "\n\n".join([
        format_review_scores(review_scores),
        _format_items("通过项", passed),
        _format_items("风险提示", warnings),
        _format_items("优化建议", suggestions),
    ])

    return {
        **state,
        "validation_result": validation_result,
        "review_scores": review_scores
    }
