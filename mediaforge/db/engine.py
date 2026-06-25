from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mediaforge.config import get_settings

_engine = None
_session_maker = None


def get_engine(database_url: str | None = None):
    global _engine
    if database_url is None:
        database_url = get_settings().database_url
    if _engine is None or str(_engine.url) != database_url:
        _engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=40,
            pool_recycle=3600,
            pool_timeout=30,
        )
    return _engine


def _get_session_maker(database_url: str | None = None):
    global _session_maker
    target_url = database_url or get_settings().database_url
    if _session_maker is None or str(_session_maker.bind.url) != target_url:
        _session_maker = async_sessionmaker(
            get_engine(database_url),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_maker


@asynccontextmanager
async def get_session(database_url: str | None = None):
    async with _get_session_maker(database_url)() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_engine() -> None:
    """Dispose the current engine and clear the session maker."""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_maker = None
