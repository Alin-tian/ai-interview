import json
from openai import AsyncOpenAI
from app.config import get_settings

settings = get_settings()


def _clean_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型未返回 JSON")
    return json.loads(raw[start:end + 1])


async def ask_json(system: str, user: str) -> dict | None:
    if not (settings.llm_api_key and settings.llm_base_url and settings.llm_model):
        return None
    try:
        # The SDK default timeout is several minutes.  That leaves the browser
        # showing a pending evaluation long after a provider has stopped making
        # useful progress, so keep this bounded and fall back to rule scoring.
        client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_request_timeout_seconds,
        )
        result = await client.chat.completions.create(
            model=settings.llm_model,
            temperature=0.25,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return _clean_json(result.choices[0].message.content or "")
    except Exception:
        return None
