import pytest
from sqlmodel import Session, select

from payload_cache.models import TransformCacheEntry
from payload_cache.service import PayloadService, input_hash, interleave
from tests.conftest import CountingTransformer

LIST_1 = ["first string", "second string", "third string"]
LIST_2 = ["other string", "another string", "last string"]


def test_interleave_alternates_items() -> None:
    assert interleave(["a", "b"], ["1", "2"]) == ["a", "1", "b", "2"]


def test_interleave_rejects_lists_of_different_length() -> None:
    with pytest.raises(ValueError):
        interleave(["a"], ["1", "2"])


def test_input_hash_is_order_sensitive() -> None:
    assert input_hash(["a"], ["b"]) == input_hash(["a"], ["b"])
    assert input_hash(["a"], ["b"]) != input_hash(["b"], ["a"])


def test_input_hash_does_not_depend_on_list_boundaries() -> None:
    # Naive concatenation would make these collide.
    assert input_hash(["a", "b"], ["c"]) != input_hash(["a"], ["b", "c"])


def test_create_payload_builds_interleaved_output(
    session: Session, transformer: CountingTransformer
) -> None:
    payload, created = PayloadService(session, transformer).create_payload(LIST_1, LIST_2)

    assert created
    assert payload.output == (
        "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
    )


def test_same_input_reuses_identifier_without_transforming(
    session: Session, transformer: CountingTransformer
) -> None:
    service = PayloadService(session, transformer)
    first, _ = service.create_payload(LIST_1, LIST_2)
    transformer.calls.clear()

    second, created = service.create_payload(LIST_1, LIST_2)

    assert not created
    assert second.id == first.id
    assert transformer.calls == []


def test_duplicate_strings_are_transformed_once(
    session: Session, transformer: CountingTransformer
) -> None:
    PayloadService(session, transformer).create_payload(["x", "x", "y"], ["y", "x", "z"])

    assert sorted(transformer.calls) == ["x", "y", "z"]


def test_only_unseen_strings_are_transformed(
    session: Session, transformer: CountingTransformer
) -> None:
    service = PayloadService(session, transformer)
    service.create_payload(["a", "b"], ["c", "d"])
    transformer.calls.clear()

    payload, created = service.create_payload(["a", "new"], ["d", "c"])

    assert created
    assert transformer.calls == ["new"]
    assert payload.output == "A, D, NEW, C"


def test_transformer_results_are_persisted(
    session: Session, transformer: CountingTransformer
) -> None:
    PayloadService(session, transformer).create_payload(["a"], ["b"])

    cached = {e.input: e.output for e in session.exec(select(TransformCacheEntry))}
    assert cached == {"a": "A", "b": "B"}


def test_get_payload_returns_stored_payload(
    session: Session, transformer: CountingTransformer
) -> None:
    service = PayloadService(session, transformer)
    payload, _ = service.create_payload(["a"], ["b"])

    assert service.get_payload(payload.id).output == "A, B"
