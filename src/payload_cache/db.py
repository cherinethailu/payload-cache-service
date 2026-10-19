"""Engine and session handling."""

from collections.abc import Iterator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine


def build_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        # FastAPI runs sync endpoints in a thread pool, so the SQLite connection must be
        # usable from threads other than the one that created it.
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args)


def init_db(engine: Engine) -> None:
    # Shortcut: tables are created on startup. A production service would manage the
    # schema with migrations (Alembic) instead.
    SQLModel.metadata.create_all(engine)


def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
