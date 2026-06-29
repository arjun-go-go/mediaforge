import asyncio
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from mediaforge.config import get_settings

_engines: dict[int, AsyncEngine] = {}
_session_makers: dict[int, async_sessionmaker] = {}


def _current_loop_key() -> int | None:
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return None


def _build_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        pool_timeout=30,
    )


def get_engine(database_url: str | None = None) -> AsyncEngine:
    if database_url is None:
        database_url = get_settings().database_url
    key = _current_loop_key()
    if key is None:
        key = 0
    engine = _engines.get(key)
    if engine is not None and str(engine.url) == database_url:
        return engine
    engine = _build_engine(database_url)
    _engines[key] = engine
    _session_makers.pop(key, None)
    return engine


def _get_session_maker(database_url: str | None = None) -> async_sessionmaker:
    key = _current_loop_key() or 0
    maker = _session_makers.get(key)
    engine = get_engine(database_url)
    if maker is None or maker.kw.get("bind") is not engine:
        maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        _session_makers[key] = maker
    return maker


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
    """Dispose the engine bound to the current event loop."""
    key = _current_loop_key()
    if key is None:
        return
    engine = _engines.pop(key, None)
    _session_makers.pop(key, None)
    if engine is not None:
        await engine.dispose()
