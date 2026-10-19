from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


class CountingTransformer:
    """Transformer double that records every call, to assert on cache behaviour."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, value: str) -> str:
        self.calls.append(value)
        return value.upper()


@pytest.fixture
def engine() -> Iterator[Engine]:
    # A single shared in-memory connection: fast, isolated per test, and visible to the
    # worker threads FastAPI's TestClient uses for sync endpoints.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()
