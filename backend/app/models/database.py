'''
创建全局异步引擎和会话工厂
定义所有 ORM 模型的基类，并在启动时创建表及补齐 updated_at 列
'''
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()
# 创建异步数据库引擎engine——并告诉引擎连接什么数据库（echo，是否把数据库执行的什么操作show出来）
engine = create_async_engine(settings.database_url, echo=settings.app_debug)
#创建异步会话工厂SessionLocal——并告诉会话工厂使用哪个引擎
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

#ORM 模型的基类
class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    import app.models  # noqa: F401

    # 链接数据库   engine.connect()，只获取连接，不自动开启事务。需要手动提交
    #engine.begin()会自动处理事务：代码正常结束：自动提交；代码抛出异常：自动回滚；代码结束后：自动释放连接
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 本项目使用 create_all，而不是数据库迁移框架。 因此需要显式添加这个新的可为空字段，
        # 以便现有的 SQLite/MySQL 数据库也能获得该字段；
        # 新创建的会话始终会为这个字段填充值。
        columns = await conn.run_sync(
            lambda sync_conn: {
                column["name"]
                for column in inspect(sync_conn).get_columns("interview_sessions")
            }
        )
        if "updated_at" not in columns:
            await conn.execute(
                # text() 允许我们执行原生 SQL 语句
                text(
                    "ALTER TABLE interview_sessions ADD COLUMN updated_at DATETIME NULL"
                )
            )
            await conn.execute(
                text(
                    "UPDATE interview_sessions SET updated_at = created_at WHERE updated_at IS NULL"
                )
            )


async def get_db():
    async with SessionLocal() as session:
        #把会话交给调用者，把当前数据库会话暂时交出去。
        yield session
        # 为什么用 yield，而不是 return。函数返回后，async with 会立即结束，
        # 数据库会话也会被关闭，接口拿到的可能是一个已经关闭的 Session。
        # 而 yield 会暂停函数的执行，直到调用者使用完毕，函数才会继续执行，
        # async with 才会结束，数据库会话才会被关闭。
