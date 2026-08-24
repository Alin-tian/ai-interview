from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=settings.app_debug)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    import app.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # This project uses create_all rather than a migration framework.  Add
        # the new nullable column explicitly so existing SQLite/MySQL installs
        # receive it too; newly written sessions always populate the value.
        columns = await conn.run_sync(lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("interview_sessions")})
        if "updated_at" not in columns:
            await conn.execute(text("ALTER TABLE interview_sessions ADD COLUMN updated_at DATETIME NULL"))
            await conn.execute(text("UPDATE interview_sessions SET updated_at = created_at WHERE updated_at IS NULL"))


async def get_db():
    async with SessionLocal() as session:
        yield session
