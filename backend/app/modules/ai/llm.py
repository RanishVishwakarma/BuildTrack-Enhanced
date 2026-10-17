"""Thin wrapper around the Anthropic SDK.

All Claude calls go through `create_message`, so the model, effort, refusal
fallback and error handling are configured in one place. Without an
ANTHROPIC_API_KEY the AI features raise AINotConfigured instead of guessing.
"""

import logging
from typing import Any

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

# Models that accept the server-side refusal fallback ("default" routing).
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client: Any = None
_test_client: Any = None


class AINotConfigured(Exception):
    """No API key configured."""


class AIUnavailable(Exception):
    """The AI service could not produce an answer (error, timeout or refusal)."""


def ai_configured() -> bool:
    return _test_client is not None or bool(settings.ai_enabled and settings.anthropic_api_key)


def test_client_installed() -> bool:
    return _test_client is not None


def set_test_client(client: Any) -> None:
    """Install a fake client (tests only). Pass None to remove it."""
    global _test_client
    _test_client = client


def get_client():
    global _client
    if _test_client is not None:
        return _test_client
    if not settings.ai_enabled:
        raise AINotConfigured("AI features are switched off (AI_ENABLED=false).")
    if not settings.anthropic_api_key:
        raise AINotConfigured("AI is not configured. Set ANTHROPIC_API_KEY in the backend environment.")
    if _client is None:
        headers = {"anthropic-workspace-id": settings.anthropic_workspace_id} if settings.anthropic_workspace_id else None
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=settings.ai_timeout_seconds, max_retries=2, default_headers=headers)
    return _client


async def create_message(
    *,
    system: list[dict] | str,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 16000,
    effort: str | None = None,
    json_schema: dict | None = None,
):
    """One Messages API call. Raises AINotConfigured or AIUnavailable."""
    client = get_client()
    output_config: dict = {"effort": effort or settings.ai_effort}
    if json_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": json_schema}
    kwargs: dict = {
        "model": settings.ai_model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        "output_config": output_config,
    }
    if tools:
        kwargs["tools"] = tools
    if settings.ai_model in _FALLBACK_MODELS:
        # If a request is declined, the API retries it on a fallback model
        # instead of failing the user's request.
        kwargs["betas"] = [_FALLBACK_BETA]
        kwargs["fallbacks"] = "default"

    try:
        response = await client.beta.messages.create(**kwargs)
    except anthropic.AuthenticationError as error:
        logger.error("Anthropic authentication failed: %s", error)
        raise AIUnavailable("The AI service rejected the configured API key.") from error
    except anthropic.RateLimitError as error:
        raise AIUnavailable("The AI service is busy. Please try again in a minute.") from error
    except anthropic.APITimeoutError as error:
        raise AIUnavailable("The AI service took too long to respond.") from error
    except anthropic.APIConnectionError as error:
        raise AIUnavailable("Could not reach the AI service.") from error
    except anthropic.BadRequestError as error:
        logger.error("Anthropic rejected the request: %s", error)
        if "workspace" in str(error).lower():
            raise AIUnavailable("The configured API key needs a workspace: set ANTHROPIC_WORKSPACE_ID or use a workspace-scoped key.") from error
        raise AIUnavailable("The AI service could not process this request.") from error
    except anthropic.APIStatusError as error:
        logger.error("Anthropic error %s: %s", error.status_code, error)
        raise AIUnavailable("The AI service returned an error.") from error

    if response.stop_reason == "refusal":
        raise AIUnavailable("The AI service declined to answer this request.")
    return response


def block_to_dict(block) -> dict:
    """Serialize a response content block so it can be replayed unchanged."""
    if isinstance(block, dict):
        return block
    return block.model_dump(mode="json", exclude_none=True)


def response_text(response) -> str:
    return "".join(getattr(block, "text", "") for block in response.content if getattr(block, "type", None) == "text").strip()


def usage_of(response) -> dict:
    usage = getattr(response, "usage", None)
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
    }
