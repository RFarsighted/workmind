import logging
from datetime import datetime

from app.core.database import SessionFactory
from app.models.monitoring import ModelCall

logger = logging.getLogger(__name__)


async def record_model_call(
    *,
    feature: str,
    latency_ms: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    model: str | None = None,
    success: bool = True,
    created_at: datetime | None = None,
) -> None:
    """Persist metadata for a completed provider request, never its prompt or response."""
    try:
        async with SessionFactory() as session:
            session.add(
                ModelCall(
                    feature=feature,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=max(0, int(latency_ms)),
                    success=success,
                    created_at=created_at,
                )
            )
            await session.commit()
    except Exception:
        # Monitoring must not turn a successful model response into a failed user action.
        logger.exception("Unable to persist model usage for feature %s", feature)


def langchain_usage(output) -> tuple[int | None, int | None]:
    """Read token usage from LangChain's OpenAI-compatible response metadata."""
    metadata = getattr(output, "usage_metadata", None)
    if isinstance(metadata, dict):
        input_tokens = metadata.get("input_tokens")
        output_tokens = metadata.get("output_tokens")
        if input_tokens is not None and output_tokens is not None:
            return int(input_tokens), int(output_tokens)

    response_metadata = getattr(output, "response_metadata", None)
    token_usage = response_metadata.get("token_usage") if isinstance(response_metadata, dict) else None
    if isinstance(token_usage, dict):
        input_tokens = token_usage.get("prompt_tokens")
        output_tokens = token_usage.get("completion_tokens")
        if input_tokens is not None and output_tokens is not None:
            return int(input_tokens), int(output_tokens)
    return None, None
