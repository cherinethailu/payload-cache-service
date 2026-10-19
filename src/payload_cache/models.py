"""Database tables."""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TransformCacheEntry(SQLModel, table=True):
    """Cached result of one transformer call, keyed by the exact input string.

    Caching per string (not per request) lets different requests share work: a request
    only pays for strings that no earlier request has seen.
    """

    __tablename__ = "transform_cache"

    input: str = Field(primary_key=True, max_length=1024)
    output: str
    created_at: datetime = Field(default_factory=_utcnow)


class Payload(SQLModel, table=True):
    """A generated payload.

    ``input_hash`` identifies the request content, so posting the same lists again
    returns the existing identifier instead of creating a duplicate payload.
    """

    __tablename__ = "payload"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    input_hash: str = Field(unique=True, index=True, max_length=64)
    output: str
    created_at: datetime = Field(default_factory=_utcnow)
