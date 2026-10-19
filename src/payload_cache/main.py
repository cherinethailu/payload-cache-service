"""Application factory; ``uvicorn payload_cache.main:app`` serves the default instance."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine

from payload_cache.api import router
from payload_cache.config import Settings, get_settings
from payload_cache.db import build_engine, init_db
from payload_cache.transformer import Transformer, make_transformer


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    transformer: Transformer | None = None,
) -> FastAPI:
    """Build the app; dependencies can be injected so tests need no patching."""
    settings = settings or get_settings()
    engine = engine or build_engine(settings.database_url)
    transformer = transformer or make_transformer(settings.transformer_delay_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(engine)
        yield
        engine.dispose()

    app = FastAPI(title="Payload cache", lifespan=lifespan)
    app.state.engine = engine
    app.state.transformer = transformer
    app.include_router(router)
    return app


app = create_app()
