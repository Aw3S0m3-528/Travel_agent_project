import re
from html import unescape
from urllib.parse import quote_plus
from typing import Any, Dict, List, Optional

import requests
from database.db import get_cache, set_cache


COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
BING_IMAGE_SEARCH_URL = "https://www.bing.com/images/search"
DUCKDUCKGO_URL = "https://duckduckgo.com/"
DUCKDUCKGO_IMAGE_URL = "https://duckduckgo.com/i.js"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}


def clean_html_text(value: str) -> str:
    """
    Wikimedia extmetadata 中部分字段带 HTML，页面展示前做轻量清洗。
    """

    if not value:
        return ""

    text = re.sub(r"<[^>]+>", "", value)
    return unescape(text).strip()


def build_commons_search_query(poi_name: str, city: str = "", query_hint: str = "") -> str:
    """
    构造 Wikimedia Commons 图片搜索词。
    """

    parts = [part for part in [query_hint, city, poi_name, "landmark"] if part]
    return " ".join(parts)


def build_web_image_search_query(poi_name: str, city: str = "", query_hint: str = "") -> str:
    """
    构造网页图片搜索词。中文景点名通常比纯英文更容易命中真实图片。
    """

    parts = [part for part in [city, poi_name, query_hint, "景点 图片"] if part]
    return " ".join(parts)


def _extract_image_from_page(page: Dict[str, Any], query: str) -> Optional[Dict[str, Any]]:
    image_info_list = page.get("imageinfo") or []

    if not image_info_list:
        return None

    image_info = image_info_list[0]
    image_url = image_info.get("thumburl") or image_info.get("url")

    if not image_url:
        return None

    extmetadata = image_info.get("extmetadata") or {}

    def metadata_value(key: str) -> str:
        item = extmetadata.get(key) or {}
        return clean_html_text(item.get("value", ""))

    return {
        "url": image_url,
        "original_url": image_info.get("url", image_url),
        "description_url": image_info.get("descriptionurl", ""),
        "title": page.get("title", ""),
        "query": query,
        "source": "Wikimedia Commons",
        "artist": metadata_value("Artist"),
        "credit": metadata_value("Credit"),
        "license": metadata_value("LicenseShortName") or metadata_value("UsageTerms"),
        "license_url": metadata_value("LicenseUrl"),
        "license_note": "图片来自 Wikimedia Commons，请按原页面许可协议标注作者和来源。"
    }


def search_commons_image(query: str, limit: int = 5, timeout: int = 8) -> Optional[Dict[str, Any]]:
    """
    在 Wikimedia Commons 中搜索图片并返回第一张可展示缩略图。
    """

    cache_key = f"{query}|{limit}"
    cached = get_cache("image_commons", cache_key)
    if cached is not None:
        return cached

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|mime|mediatype|extmetadata",
        "iiurlwidth": 900,
        "origin": "*",
    }

    response = requests.get(
        COMMONS_API_URL,
        params=params,
        headers=DEFAULT_HEADERS,
        timeout=timeout
    )
    response.raise_for_status()

    data = response.json()
    pages = data.get("query", {}).get("pages", {})

    candidates: List[Dict[str, Any]] = []

    for page in pages.values():
        image = _extract_image_from_page(page, query)
        if not image:
            continue

        mime = (page.get("imageinfo") or [{}])[0].get("mime", "")
        media_type = (page.get("imageinfo") or [{}])[0].get("mediatype", "")

        if not mime.startswith("image/") and media_type != "BITMAP":
            continue

        candidates.append(image)

    result = candidates[0] if candidates else None
    set_cache("image_commons", cache_key, result)
    return result


def normalize_bing_image_url(value: str) -> str:
    value = value.replace("\\/", "/")
    value = value.replace("\\u0026", "&")
    return unescape(value).strip()


def is_supported_image_url(url: str) -> bool:
    lowered = url.lower()

    if not lowered.startswith(("http://", "https://")):
        return False

    blocked_fragments = [
        "data:image",
        "logo",
        "icon",
        "avatar",
        "sprite",
        "placeholder",
        "blank",
        "lookaside.fbsbx.com",
        "facebook.com",
        "fbcdn.net",
        "blogspot.com",
    ]

    if any(fragment in lowered for fragment in blocked_fragments):
        return False

    return True


def has_image_extension(url: str) -> bool:
    lowered = url.lower().split("?", 1)[0]
    return lowered.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))


def sort_image_urls(urls: List[str]) -> List[str]:
    """
    优先选择直接图片文件，降低代理页、社交平台链接导致的展示失败概率。
    """

    return sorted(
        urls,
        key=lambda url: (
            0 if has_image_extension(url) else 1,
            len(url)
        )
    )


def extract_bing_image_urls(html: str) -> List[str]:
    """
    从 Bing 图片搜索结果页中提取原图 murl。
    Bing 页面会把图片地址放在 JSON 片段或 HTML 转义字段里。
    """

    patterns = [
        r'"murl"\s*:\s*"(.*?)"',
        r"murl&quot;\s*:\s*&quot;(.*?)&quot;",
    ]

    urls = []
    seen = set()

    for pattern in patterns:
        for match in re.finditer(pattern, html):
            url = normalize_bing_image_url(match.group(1))
            if url in seen or not is_supported_image_url(url):
                continue
            seen.add(url)
            urls.append(url)

    return urls


def extract_duckduckgo_vqd(html: str) -> Optional[str]:
    patterns = [
        r'vqd="([^"]+)"',
        r"vqd='([^']+)'",
        r"vqd=([^&\"']+)&",
    ]

    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)

    return None


def search_duckduckgo_image(query: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    使用 DuckDuckGo 图片搜索结果获取原图地址。
    该方法用于学习演示场景；正式项目建议替换为授权图片 API 或本地图片库。
    """

    cached = get_cache("image_duckduckgo", query)
    if cached is not None:
        return cached

    session = requests.Session()
    response = session.get(
        DUCKDUCKGO_URL,
        params={"q": query},
        headers=DEFAULT_HEADERS,
        timeout=timeout
    )
    response.raise_for_status()

    vqd = extract_duckduckgo_vqd(response.text)
    if not vqd:
        return None

    image_response = session.get(
        DUCKDUCKGO_IMAGE_URL,
        params={
            "l": "wt-wt",
            "o": "json",
            "q": query,
            "vqd": vqd,
            "f": ",,,",
            "p": "1",
        },
        headers={
            **DEFAULT_HEADERS,
            "Referer": str(response.url),
        },
        timeout=timeout
    )
    image_response.raise_for_status()

    data = image_response.json()
    results = data.get("results", [])

    for item in results:
        image_url = item.get("image", "")
        if not is_supported_image_url(image_url):
            continue

        result = {
            "url": image_url,
            "original_url": image_url,
            "description_url": item.get("url", ""),
            "title": item.get("title", query),
            "query": query,
            "source": "DuckDuckGo Images 网页爬取",
            "artist": "",
            "credit": item.get("source", ""),
            "license": "未校验",
            "license_url": "",
            "license_note": "网络爬取图片，仅用于学习演示；非商业展示也建议保留来源并避免再分发。"
        }
        set_cache("image_duckduckgo", query, result)
        return result

    set_cache("image_duckduckgo", query, None)
    return None


def search_bing_image(query: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    从 Bing 图片搜索结果中爬取第一张原图地址。
    该方法用于学习演示场景；正式项目建议替换为有授权的图片 API 或自建图片库。
    """

    cached = get_cache("image_bing", query)
    if cached is not None:
        return cached

    params = {
        "q": query,
        "form": "HDRSC2",
        "first": "1",
        "cw": "1280",
        "ch": "720",
    }

    response = requests.get(
        BING_IMAGE_SEARCH_URL,
        params=params,
        headers=DEFAULT_HEADERS,
        timeout=timeout
    )
    response.raise_for_status()

    urls = sort_image_urls(extract_bing_image_urls(response.text))

    if not urls:
        set_cache("image_bing", query, None)
        return None

    result = {
        "url": urls[0],
        "original_url": urls[0],
        "description_url": f"{BING_IMAGE_SEARCH_URL}?q={quote_plus(query)}",
        "title": query,
        "query": query,
        "source": "Bing Images 网页爬取",
        "artist": "",
        "credit": "",
        "license": "未校验",
        "license_url": "",
        "license_note": "网络爬取图片，仅用于学习演示；非商业展示也建议保留来源并避免再分发。"
    }
    set_cache("image_bing", query, result)
    return result
