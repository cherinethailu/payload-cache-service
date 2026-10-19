"""Integration tests: HTTP layer, service and a real (in-memory) database together."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from payload_cache.main import create_app
from tests.conftest import CountingTransformer

EXPECTED_OUTPUT = (
    "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
)
SAMPLE = {
    "list_1": ["first string", "second string", "third string"],
    "list_2": ["other string", "another string", "last string"],
}


@pytest.fixture
def client(engine: Engine, transformer: CountingTransformer) -> Iterator[TestClient]:
    with TestClient(create_app(engine=engine, transformer=transformer)) as client:
        yield client


def test_create_then_read_payload(client: TestClient) -> None:
    created = client.post("/payload", json=SAMPLE)
    assert created.status_code == 201
    assert created.json()["message"] == "Payload created"

    read = client.get(f"/payload/{created.json()['id']}")
    assert read.status_code == 200
    assert read.json() == {"output": EXPECTED_OUTPUT}


def test_repeated_post_returns_same_id_without_transformer_calls(
    client: TestClient, transformer: CountingTransformer
) -> None:
    first = client.post("/payload", json=SAMPLE)
    calls_after_first = len(transformer.calls)

    second = client.post("/payload", json=SAMPLE)

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert len(transformer.calls) == calls_after_first


@pytest.mark.parametrize(
    "body",
    [
        {"list_1": ["a"], "list_2": ["b", "c"]},
        {"list_1": [], "list_2": []},
        {"list_1": ["a"]},
        {"list_1": ["a"], "list_2": [1]},
        {"list_1": ["a" * 1025], "list_2": ["b"]},
    ],
    ids=["length-mismatch", "empty", "missing-list", "non-string", "string-too-long"],
)
def test_invalid_input_is_rejected(client: TestClient, body: dict) -> None:
    assert client.post("/payload", json=body).status_code == 422


def test_unknown_payload_returns_404(client: TestClient) -> None:
    response = client.get("/payload/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_malformed_payload_id_is_rejected(client: TestClient) -> None:
    assert client.get("/payload/not-a-uuid").status_code == 422
