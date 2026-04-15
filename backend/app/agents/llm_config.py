"""AutoGen LLM configuration for Kimi K2.5 (OpenAI-compatible API)."""

from autogen_ext.models.openai import OpenAIChatCompletionClient

from app.config import settings


# Check if using Kimi K2.5 which has tool calling limitations
_IS_KIMI_K25 = "kimi-k2.5" in settings.KIMI_MODEL_NAME.lower()


def get_model_client() -> OpenAIChatCompletionClient:
    """Create an OpenAI-compatible model client for Kimi K2.5."""
    # Use custom client for Kimi K2.5 to inject disable_thinking
    if _IS_KIMI_K25:
        return OpenAIChatCompletionClient(
            model=settings.KIMI_MODEL_NAME,
            api_key=settings.KIMI_API_KEY,
            base_url=settings.KIMI_BASE_URL,
            temperature=0.6,
            extra_body={
                "thinking": {"type": "disabled"}
            }, 
            model_info={
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": "unknown",
                "structured_output": False,
            },
        )

    # Default client for other models
    return OpenAIChatCompletionClient(
        model=settings.KIMI_MODEL_NAME,
        api_key=settings.KIMI_API_KEY,
        base_url=settings.KIMI_BASE_URL,
        temperature=1,
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
            "structured_output": False,
        },
    )


def is_kimi_k25() -> bool:
    """Check if using Kimi K2.5 model which has tool calling limitations."""
    return _IS_KIMI_K25
