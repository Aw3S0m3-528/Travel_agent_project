import re
from html import unescape
from typing import Any, Dict, List
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from database.db import get_cache, set_cache


BING_SEARCH_URL = "https://www.bing.com/search"
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

OFFICIAL_DOMAIN_KEYWORDS = [
    "gov.cn",
    ".gov.",
    "mct.gov",
    "ctnews.com.cn",
    "museum",
    "amap.com",
    "ctrip.com",
    "mafengwo.cn",
    "trip.com",
]

FRESHNESS_KEYWORDS = ["2026", "2025", "最新", "公告", "通知", "开放", "恢复", "预约"]
TRAVEL_FACT_KEYWORDS = ["开放时间", "门票", "票价", "预约", "公告", "营业时间", "入园", "交通"]


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def unwrap_duckduckgo_url(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    uddg = query.get("uddg", [])

    if uddg:
        return unquote(uddg[0])

    return url


def build_recent_travel_query(destination: str, poi: str = "") -> str:
    parts = [
        destination,
        poi,
        "旅游",
        "开放时间",
        "门票",
        "预约",
        "官方",
        "2025",
        "2026",
    ]
    return " ".join([part for part in parts if part])


def score_search_result(item: Dict[str, Any], destination: str = "", poi: str = "") -> Dict[str, Any]:
    title = item.get("title", "")
    snippet = item.get("snippet", "")
    url = item.get("url", "")
    query = item.get("query", "")
    text = f"{title} {snippet} {query}"
    lowered_url = url.lower()

    score = 20
    reasons = []

    if any(keyword in lowered_url for keyword in OFFICIAL_DOMAIN_KEYWORDS):
        score += 20
        reasons.append("官方/权威域名")

    if any(keyword in text for keyword in FRESHNESS_KEYWORDS):
        score += 18
        reasons.append("包含近两年或公告类新鲜度信号")

    matched_fact_keywords = [keyword for keyword in TRAVEL_FACT_KEYWORDS if keyword in text]
    if matched_fact_keywords:
        score += min(24, len(matched_fact_keywords) * 8)
        reasons.append("包含动态旅游信息：" + "、".join(matched_fact_keywords[:3]))

    if destination and destination in text:
        score += 12
        reasons.append("匹配目的地")

    if poi and poi in text:
        score += 16
        reasons.append("匹配景点名称")

    return {
        **item,
        "score": score,
        "score_reasons": reasons or ["普通旅游资料"],
    }


def rank_search_results(results: List[Dict[str, Any]], destination: str = "", poi: str = "") -> List[Dict[str, Any]]:
    scored_results = [
        score_search_result(item, destination=destination, poi=poi)
        for item in results
    ]
    return sorted(scored_results, key=lambda item: item.get("score", 0), reverse=True)


def extract_bing_results(html: str, query: str, limit: int) -> List[Dict[str, Any]]:
    results = []
    seen_urls = set()
    blocks = re.findall(r'<li class="b_algo".*?</li>', html, flags=re.S)

    for block in blocks:
        title_match = re.search(r'<h2.*?<a href="(?P<url>.*?)".*?>(?P<title>.*?)</a>.*?</h2>', block, re.S)
        if not title_match:
            continue

        snippet_match = re.search(r"<p>(?P<snippet>.*?)</p>", block, re.S)

        url = unwrap_duckduckgo_url(unescape(title_match.group("url") or "").strip())
        title = clean_text(title_match.group("title") or "")
        snippet = clean_text(snippet_match.group("snippet") if snippet_match else "")

        if not url or not title or url in seen_urls:
            continue

        seen_urls.add(url)
        results.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "query": query,
            "source": "Bing Web Search",
            "recency_hint": "query includes 2025/2026"
        })

        if len(results) >= limit:
            break

    return results


def search_recent_travel_web(query: str, limit: int = 5, timeout: int = 10) -> List[Dict[str, Any]]:
    """
    搜索近一两年旅游资料网页摘要。
    学习阶段使用网页搜索结果解析；正式项目建议替换为 SerpAPI、Tavily、Bing Search API 等稳定接口。
    """

    cache_key = f"{query}|{limit}"
    cached = get_cache("web_search", cache_key)
    if cached is not None:
        return cached

    duckduckgo_results = search_duckduckgo_web(query, limit=limit, timeout=timeout)
    if duckduckgo_results:
        set_cache("web_search", cache_key, duckduckgo_results)
        return duckduckgo_results

    response = requests.get(
        BING_SEARCH_URL,
        params={"q": query, "count": limit, "setlang": "zh-CN"},
        headers=DEFAULT_HEADERS,
        timeout=timeout
    )
    response.raise_for_status()

    results = extract_bing_results(response.text, query, limit)
    set_cache("web_search", cache_key, results)
    return results


def extract_duckduckgo_results(html: str, query: str, limit: int) -> List[Dict[str, Any]]:
    blocks = re.findall(r'<div class="result results_links.*?</div>\s*</div>', html, flags=re.S)
    results = []
    seen_urls = set()

    for block in blocks:
        title_match = re.search(
            r'<a rel="nofollow" class="result__a" href="(?P<url>.*?)".*?>(?P<title>.*?)</a>',
            block,
            re.S
        )
        if not title_match:
            continue

        snippet_match = re.search(r'<a class="result__snippet".*?>(?P<snippet>.*?)</a>', block, re.S)

        url = unwrap_duckduckgo_url(unescape(title_match.group("url") or "").strip())
        title = clean_text(title_match.group("title") or "")
        snippet = clean_text(snippet_match.group("snippet") if snippet_match else "")

        if not url or not title or url in seen_urls:
            continue

        seen_urls.add(url)
        results.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "query": query,
            "source": "DuckDuckGo Web Search",
            "recency_hint": "query includes 2025/2026"
        })

        if len(results) >= limit:
            break

    return results


def search_duckduckgo_web(query: str, limit: int = 5, timeout: int = 10) -> List[Dict[str, Any]]:
    response = requests.get(
        DUCKDUCKGO_HTML_URL,
        params={"q": query},
        headers=DEFAULT_HEADERS,
        timeout=timeout
    )
    response.raise_for_status()

    return extract_duckduckgo_results(response.text, query, limit)


def format_online_results(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "未检索到在线旅游资料。"

    parts = []

    for index, item in enumerate(results, start=1):
        parts.append(
            f"【在线资料{index}】\n"
            f"标题：{item.get('title', '')}\n"
            f"链接：{item.get('url', '')}\n"
            f"评分：{item.get('score', '未评分')}\n"
            f"评分理由：{'、'.join(item.get('score_reasons', []))}\n"
            f"摘要：{item.get('snippet', '')}\n"
            f"搜索词：{item.get('query', '')}"
        )

    return "\n\n".join(parts)


def build_search_url(query: str) -> str:
    return f"{BING_SEARCH_URL}?q={quote_plus(query)}"
