from functools import lru_cache
from app.core.config import settings


@lru_cache(maxsize=1)
def get_llm_client():
    if settings.LLM_PROVIDER == "anthropic":
        import anthropic
        return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    # Default: Ollama via OpenAI-compatible API
    from openai import AsyncOpenAI
    return AsyncOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key="ollama",
    )


def is_anthropic() -> bool:
    return settings.LLM_PROVIDER == "anthropic"


async def llm_complete(prompt: str, max_tokens: int = 600, system: str | None = None) -> str:
    """Single-shot completion against whichever provider is configured."""
    client = get_llm_client()
    if is_anthropic():
        kwargs = {"system": system} if system else {}
        resp = await client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return resp.content[0].text
    import httpx
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    resp = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        max_tokens=max_tokens,
        stream=False,
        messages=messages,
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
    )
    return resp.choices[0].message.content
