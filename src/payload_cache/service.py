"""Payload generation and transformer-result caching."""

import hashlib
import json
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import Insert
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from payload_cache.models import Payload, TransformCacheEntry
from payload_cache.transformer import Transformer

OUTPUT_SEPARATOR = ", "


def input_hash(list_1: Sequence[str], list_2: Sequence[str]) -> str:
    """Stable fingerprint of a request, used to detect payloads generated before.

    Order matters (it changes the output), so the lists are hashed as-is, not sorted.
    """
    canonical = json.dumps([list(list_1), list(list_2)], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def interleave(first: Sequence[str], second: Sequence[str]) -> list[str]:
    return [item for pair in zip(first, second, strict=True) for item in pair]


class PayloadService:
    def __init__(self, session: Session, transformer: Transformer) -> None:
        self._session = session
        self._transformer = transformer

    def get_payload(self, payload_id: uuid.UUID) -> Payload | None:
        return self._session.get(Payload, payload_id)

    def create_payload(self, list_1: Sequence[str], list_2: Sequence[str]) -> tuple[Payload, bool]:
        """Return the payload for these lists and whether it was newly created."""
        fingerprint = input_hash(list_1, list_2)
        existing = self._find_by_hash(fingerprint)
        if existing is not None:
            return existing, False

        transformed = self._transform_all(set(list_1) | set(list_2))
        output = OUTPUT_SEPARATOR.join(
            interleave([transformed[s] for s in list_1], [transformed[s] for s in list_2])
        )

        payload = Payload(input_hash=fingerprint, output=output)
        self._session.add(payload)
        try:
            self._session.commit()
        except IntegrityError:
            # A concurrent request stored the same payload between our lookup and insert;
            # theirs wins so that both callers get the same identifier.
            self._session.rollback()
            existing = self._find_by_hash(fingerprint)
            if existing is None:
                raise
            return existing, False
        self._session.refresh(payload)
        return payload, True

    def _find_by_hash(self, fingerprint: str) -> Payload | None:
        return self._session.exec(select(Payload).where(Payload.input_hash == fingerprint)).first()

    def _transform_all(self, values: set[str]) -> dict[str, str]:
        """Transform every value, calling the transformer at most once per uncached value."""
        cached = {
            entry.input: entry.output
            for entry in self._session.exec(
                select(TransformCacheEntry).where(TransformCacheEntry.input.in_(values))
            )
        }
        fresh = {value: self._transformer(value) for value in values - cached.keys()}
        if fresh:
            self._store(fresh.items())
        return cached | fresh

    def _store(self, results: Iterable[tuple[str, str]]) -> None:
        # Committed on its own so the (expensive) results survive even if storing the
        # payload fails afterwards. "Insert or ignore" because a concurrent request may
        # have cached the same string meanwhile; both results are equal, either is fine.
        now = datetime.now(UTC)
        rows = [{"input": i, "output": o, "created_at": now} for i, o in results]
        self._session.execute(_insert_ignore_conflicts(self._session, rows))
        self._session.commit()


def _insert_ignore_conflicts(session: Session, rows: list[dict]) -> Insert:
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        stmt = postgresql.insert(TransformCacheEntry)
    elif dialect == "sqlite":
        stmt = sqlite.insert(TransformCacheEntry)
    else:
        raise NotImplementedError(f"Unsupported database dialect: {dialect}")
    return stmt.values(rows).on_conflict_do_nothing(index_elements=["input"])
