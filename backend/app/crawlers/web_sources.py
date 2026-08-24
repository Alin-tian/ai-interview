import hashlib
import re
import httpx
from bs4 import BeautifulSoup
from app.config import get_settings
from app.utils.security import validate_public_url
from app.services.cache import get_cached, set_cached

settings = get_settings()


async def search_public_sources(query: str) -> list[dict]:
    """通过 Tavily 搜索公开岗位和面试资料，不直接模拟搜索引擎页面。"""
    if not settings.tavily_api_key:
        return []
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 8,
                "include_answer": False,
                "include_raw_content": False,
            },
        )
        response.raise_for_status()
        body = response.json()
    return [
        {"title": item.get("title", "网页资料"), "url": item["url"], "snippet": item.get("content", "")}
        for item in body.get("results", [])
        if item.get("url")
    ]


async def fetch_public_page(url: str) -> dict:
    validate_public_url(url)
    cache_key = "interview:page:" + hashlib.sha256(url.encode("utf-8")).hexdigest()
    cached = await get_cached(cache_key)
    if cached:
        return cached
    headers = {"User-Agent": "AI-Interview-Agent/1.0 (public-source-summary)"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, headers=headers) as client:
        response = await client.get(url)
        # Validate every redirect target before following it to prevent SSRF.
        redirects = 0
        while response.is_redirect and redirects < 5:
            target = str(response.headers.get("location", ""))
            if not target:
                break
            from urllib.parse import urljoin
            target = urljoin(str(response.url), target)
            validate_public_url(target)
            response = await client.get(target)
            redirects += 1
        if response.is_redirect:
            raise ValueError("网页重定向次数过多")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            raise ValueError("资料链接不是 HTML 页面")
        if len(response.content) > 2 * 1024 * 1024:
            raise ValueError("网页内容超过 2MB 限制")
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    if len(text) < 50:
        raise ValueError("网页未提取到可用公开内容")
    result = {
        "title": (soup.title.string.strip() if soup.title and soup.title.string else "网页资料")[:512],
        "url": str(response.url),
        "content": text[:12000],
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    await set_cached(cache_key, result)
    return result
