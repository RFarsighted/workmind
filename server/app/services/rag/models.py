import httpx

from app.core.config import settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts with the configured SiliconFlow model."""
    if not settings.siliconflow_api_key:
        raise RuntimeError("SILICONFLOW_API_KEY is not configured")
    if not texts:
        return []

    endpoint = f"{settings.siliconflow_base_url.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {settings.siliconflow_api_key}"}
    vectors: list[list[float] | None] = [None] * len(texts)

    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        for offset in range(0, len(texts), 32):
            batch = texts[offset : offset + 32]
            response = await client.post(
                endpoint,
                headers=headers,
                json={"model": settings.siliconflow_embedding_model, "input": batch},
            )
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("data", []):
                index = int(item["index"])
                vectors[offset + index] = item["embedding"]

    if any(vector is None for vector in vectors):
        raise RuntimeError("SiliconFlow returned an incomplete embedding response")
    return [vector for vector in vectors if vector is not None]
