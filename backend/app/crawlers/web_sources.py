import hashlib
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings
from app.services.cache import get_cached, set_cached
from app.utils.security import validate_public_url

settings = get_settings()


async def search_public_sources(query: str) -> list[dict]:
    """Search public sources and retain provider-extracted text as a fallback."""
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
                "include_raw_content": True,
            },
        )
        response.raise_for_status()
        body = response.json()
    return [
        {
            "title": item.get("title", "网页资料"),
            "url": item["url"],
            "snippet": item.get("content", ""),
            "raw_content": item.get("raw_content", ""),
        }
        for item in body.get("results", [])
        if item.get("url")
    ]


async def fetch_public_page(url: str) -> dict:
    """Fetch a public HTML page with SSRF checks, browser headers and retries."""
    validate_public_url(url)
    cache_key = "interview:page:" + hashlib.sha256(url.encode("utf-8")).hexdigest()
    cached = await get_cached(cache_key)
    if cached:
        return cached
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    timeout = httpx.Timeout(connect=10, read=25, write=10, pool=10)
    transport = httpx.AsyncHTTPTransport(retries=2)
    async with httpx.AsyncClient(timeout=timeout, transport=transport, follow_redirects=False, headers=headers) as client:
        response = await client.get(url)
        redirects = 0
        while response.is_redirect and redirects < 5:
            target = str(response.headers.get("location", ""))
            if not target:
                break
            target = urljoin(str(response.url), target)
            validate_public_url(target)
            response = await client.get(target)
            redirects += 1
        if response.is_redirect:
            raise ValueError("网页重定向次数过多")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
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
