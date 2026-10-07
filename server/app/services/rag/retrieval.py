from app.core.config import settings
from app.services.rag.models import embed_texts
from app.services.rag.vector_store import get_collection


async def retrieve_documents(
    question: str,
    *,
    category: str | None = None,
    limit: int = 4,
) -> list[dict[str, str | float]]:
    """Return relevant knowledge chunks using the same threshold as RAG chat."""
    query_embedding = (await embed_texts([question]))[0]
    collection = await get_collection()
    count = await collection.count()
    if count == 0:
        return []

    result = await collection.query(
        query_embeddings=[query_embedding],
        n_results=min(limit, count),
        where={"category": category} if category else None,
        include=["documents", "metadatas", "distances"],
    )
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    matches: list[dict[str, str | float]] = []
    for content, metadata, distance in zip(documents, metadatas, distances):
        similarity = max(0.0, min(1.0, 1.0 - float(distance)))
        if similarity >= settings.rag_min_similarity:
            matches.append(
                {
                    "title": metadata.get("title", "未命名文档"),
                    "content": content,
                    "score": similarity,
                }
            )
    return matches
