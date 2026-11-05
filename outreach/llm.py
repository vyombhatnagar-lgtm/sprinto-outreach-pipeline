"""Thin wrapper over the Anthropic SDK for schema-constrained calls.

Every call returns (validated pydantic object, meta). The meta (model that
actually served it, token usage, stop reason, whether a fallback ran) goes
into the step's trace record.
"""
from typing import Any, Dict, Optional, Tuple, Type, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from .config import Settings

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, settings: Settings, client: Optional[anthropic.Anthropic] = None,
                 model: Optional[str] = None):
        self.model = model or settings.model
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    def structured(self, *, system: str, user: str, output_model: Type[T],
                   effort: str = "medium", max_tokens: int = 16000) -> Tuple[T, Dict[str, Any]]:
        schema = output_model.model_json_schema()
        kwargs: Dict[str, Any] = {}
        if self.model.startswith("claude-opus"):
            # server-side fallback on a policy decline; offered for Opus, not for Haiku
            kwargs = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                **kwargs,
            )
        except anthropic.AuthenticationError as e:
            raise LLMError("Anthropic authentication failed - check ANTHROPIC_API_KEY") from e
        except anthropic.BadRequestError as e:
            raise LLMError(f"Anthropic rejected the request: {e.message}") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Anthropic rate limit hit - retry later") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the Anthropic API") from e

        meta = {
            "model": resp.model,
            "stop_reason": resp.stop_reason,
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "fallback_ran": any(getattr(i, "type", "") == "fallback_message"
                                for i in (getattr(resp.usage, "iterations", None) or [])),
        }
        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            raise LLMError(f"Model declined the request ({getattr(details, 'category', None)})")
        if resp.stop_reason == "max_tokens":
            raise LLMError("Model output hit max_tokens before finishing")

        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            raise LLMError("No text block in model response")
        try:
            return output_model.model_validate_json(text), meta
        except ValidationError as e:
            raise LLMError(f"Model output failed schema validation: {e}") from e
