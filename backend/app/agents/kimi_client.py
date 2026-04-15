"""Custom OpenAI client for Kimi K2.5 with disable_thinking support."""

from typing import Any, Optional
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import CreateResult


class KimiK25ChatCompletionClient(OpenAIChatCompletionClient):
    """Custom client for Kimi K2.5 that disables thinking mode to fix tool calling."""

    async def create(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        json_output: Optional[bool] = None,
        extra_create_args: Optional[dict[str, Any]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> CreateResult:
        """Override create to inject disable_thinking parameter."""
        # Merge disable_thinking into extra_create_args
        extra_args = extra_create_args or {}
        extra_args["disable_thinking"] = True

        return await super().create(
            messages=messages,
            tools=tools,
            json_output=json_output,
            extra_create_args=extra_args,
            cancellation_token=cancellation_token,
        )

    def create_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        json_output: Optional[bool] = None,
        extra_create_args: Optional[dict[str, Any]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> Any:
        """Override create_stream to inject disable_thinking parameter."""
        extra_args = extra_create_args or {}
        extra_args["disable_thinking"] = True

        return super().create_stream(
            messages=messages,
            tools=tools,
            json_output=json_output,
            extra_create_args=extra_args,
            cancellation_token=cancellation_token,
        )
