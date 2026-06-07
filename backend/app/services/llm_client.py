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
