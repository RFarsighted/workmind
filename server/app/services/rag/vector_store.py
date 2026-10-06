from urllib.parse import urlsplit

import chromadb

from app.core.config import settings

COLLECTION_NAME = "workmind-knowledge"


async def get_collection():
    parsed = urlsplit(settings.chroma_url)
    if not parsed.hostname:
        raise RuntimeError("CHROMA_URL must include a host")
    client = await chromadb.AsyncHttpClient(
        host=parsed.hostname,
        port=parsed.port or (443 if parsed.scheme == "https" else 8000),
        ssl=parsed.scheme == "https",
        tenant="default_tenant",
        database="default_database",
    )
    return await client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
