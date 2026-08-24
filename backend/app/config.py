from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./interview_agent.db"
    app_debug: bool = False
    upload_dir: str = "uploads"
    cors_origins: str = "http://localhost:3000"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_request_timeout_seconds: float = 45.0
    tavily_api_key: str = ""
    es_host: str = ""
    es_request_timeout_seconds: float = 5.0
    redis_url: str = ""
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""

    def required_infrastructure(self) -> list[str]:
        missing = []
        for name, value in (("DATABASE_URL", self.database_url), ("LLM_API_KEY", self.llm_api_key), ("LLM_BASE_URL", self.llm_base_url), ("LLM_MODEL", self.llm_model), ("ES_HOST", self.es_host), ("REDIS_URL", self.redis_url), ("EMBEDDING_API_KEY", self.embedding_api_key), ("EMBEDDING_BASE_URL", self.embedding_base_url), ("EMBEDDING_MODEL", self.embedding_model)):
            if not value:
                missing.append(name)
        return missing

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
