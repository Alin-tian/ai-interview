"""Interview material vector retrieval backed by Elasticsearch."""
import hashlib

from elastic_transport import ConnectionError, ConnectionTimeout
from elasticsearch import AsyncElasticsearch
from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()
INDEX = "interview_materials"
MAPPING = {"mappings": {"properties": {
    "session_id": {"type": "integer"}, "source_id": {"type": "integer"},
    "source_type": {"type": "keyword"}, "title": {"type": "text"},
    "content": {"type": "text"}, "chunk_no": {"type": "integer"},
    "embedding": {"type": "dense_vector", "dims": 1536, "index": True, "similarity": "cosine"},
}}}


class MaterialRetriever:
    def __init__(self):
        self.client: AsyncElasticsearch | None = None

    async def _es(self) -> AsyncElasticsearch:
        if self.client is None:
            self.client = AsyncElasticsearch(
                settings.es_host,
                request_timeout=settings.es_request_timeout_seconds,
                retry_on_timeout=True,
                max_retries=2,
            )
        return self.client

    @staticmethod
    def unavailable_error(exc: Exception) -> RuntimeError:
        return RuntimeError(
            "Elasticsearch is unavailable or timed out. Verify ES_HOST (usually "
            "http://localhost:9200) and run: docker compose up -d elasticsearch"
        )

    async def embed(self, text: str) -> list[float]:
        client = AsyncOpenAI(api_key=settings.embedding_api_key, base_url=settings.embedding_base_url)
        result = await client.embeddings.create(model=settings.embedding_model, input=text[:8000])
        return result.data[0].embedding

    async def ensure_index(self, dims: int) -> None:
        es = await self._es()
        if not await es.indices.exists(index=INDEX):
            mapping = MAPPING.copy()
            mapping["mappings"] = {"properties": dict(MAPPING["mappings"]["properties"])}
            mapping["mappings"]["properties"]["embedding"] = {"type": "dense_vector", "dims": dims, "index": True, "similarity": "cosine"}
            await es.indices.create(index=INDEX, body=mapping)

    async def index_source(self, session_id: int, source_id: int, source_type: str, title: str, content: str) -> None:
        try:
            es = await self._es()
            for number, chunk in enumerate(_chunks(content)):
                vector = await self.embed(chunk)
                await self.ensure_index(len(vector))
                key = hashlib.sha256(f"{session_id}:{source_id}:{number}".encode()).hexdigest()
                await es.index(index=INDEX, id=key, document={"session_id": session_id, "source_id": source_id, "source_type": source_type, "title": title, "content": chunk, "chunk_no": number, "embedding": vector})
            await es.indices.refresh(index=INDEX)
        except (ConnectionTimeout, ConnectionError) as exc:
            raise self.unavailable_error(exc) from exc

    async def search(self, session_id: int, query: str, limit: int = 5) -> list[dict]:
        try:
            vector = await self.embed(query)
            es = await self._es()
            base = {"bool": {"filter": [{"term": {"session_id": session_id}}], "must": [{"match": {"content": query}}]}}
            body = {"size": limit, "query": {"script_score": {"query": base, "script": {"source": "0.3 * _score + 0.7 * (cosineSimilarity(params.vector, 'embedding') + 1.0)", "params": {"vector": vector}}}}}
            response = await es.search(index=INDEX, body=body)
            return [{"source_id": x["_source"]["source_id"], "title": x["_source"]["title"], "content": x["_source"]["content"], "score": x["_score"]} for x in response["hits"]["hits"]]
        except (ConnectionTimeout, ConnectionError) as exc:
            raise self.unavailable_error(exc) from exc

    async def check_ready(self) -> None:
        try:
            es = await self._es()
            if not await es.ping():
                raise RuntimeError("Elasticsearch is unavailable")
            await self.embed("health check")
        except (ConnectionTimeout, ConnectionError) as exc:
            raise self.unavailable_error(exc) from exc


def _chunks(text: str, size: int = 1200) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


retriever = MaterialRetriever()
