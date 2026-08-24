from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.models.database import init_db
from app.api.interviews import router as interviews_router
from app.rag.material_retriever import retriever
from app.services.cache import check_redis

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = settings.required_infrastructure()
    if missing:
        raise RuntimeError("缺少基础设施配置: " + ", ".join(missing))
    await init_db()
    await check_redis()
    await retriever.check_ready()
    yield

app = FastAPI(title="AI Interview Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(interviews_router, prefix="/api/v1")

@app.get("/api/v1/health")
async def health(): return {"status": "ok", "service": "ai-interview-agent"}
