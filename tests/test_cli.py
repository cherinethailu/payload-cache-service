import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine

from payload_cache import cli
from payload_cache.main import create_app
from payload_cache.schemas import PayloadCreate
from tests.conftest import CountingTransformer

BODY = '{"list_1": ["a", "b"], "list_2": ["c", "d"]}'


# --- argument parsing -------------------------------------------------------------------


def test_short_flags() -> None:
    settings = cli.parse_args(["-h", "http://svc:9000", "-r", "3", "-j", BODY, "-o", "out.jsonl"])

    assert str(settings.host) == "http://svc:9000/"
    assert settings.repeat == 3
    assert settings.json_body == BODY
    assert settings.output == "out.jsonl"


def test_long_flags_and_defaults() -> None:
    settings = cli.parse_args(["--input", "-"])

    assert str(settings.host) == "http://localhost:8000/"
    assert settings.repeat == 1
    assert settings.input == "-"
    assert settings.output == "-"


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["-i", "in.json", "-j", BODY],
        ["-j", BODY, "-r", "0"],
        ["-j", BODY, "-h", "not a url"],
    ],
    ids=["no-input", "two-inputs", "non-positive-repeat", "invalid-host"],
)
def test_invalid_arguments_are_rejected(argv: list[str]) -> None:
    with pytest.raises(ValidationError):
        cli.parse_args(argv)


def test_environment_does_not_configure_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST", "http://elsewhere:1")

    assert str(cli.parse_args(["-j", BODY]).host) == "http://localhost:8000/"


# --- input loading ----------------------------------------------------------------------


def test_load_request_from_json_argument() -> None:
    request = cli.load_request(cli.parse_args(["-j", BODY]), io.StringIO())

    assert request == PayloadCreate(list_1=["a", "b"], list_2=["c", "d"])


def test_load_request_from_stdin() -> None:
    request = cli.load_request(cli.parse_args(["-i", "-"]), io.StringIO(BODY))

    assert request.list_2 == ["c", "d"]


def test_load_request_from_file(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text(BODY)

    request = cli.load_request(cli.parse_args(["-i", str(path)]), io.StringIO())

    assert request.list_1 == ["a", "b"]


def test_load_request_validates_before_sending() -> None:
    settings = cli.parse_args(["-j", '{"list_1": ["a"], "list_2": []}'])

    with pytest.raises(ValidationError):
        cli.load_request(settings, io.StringIO())


# --- against the real app ---------------------------------------------------------------


@pytest.fixture
def client(engine: Engine, transformer: CountingTransformer):
    with TestClient(create_app(engine=engine, transformer=transformer)) as client:
        yield client


def test_repeated_runs_reuse_payload_and_cache(
    client: TestClient, transformer: CountingTransformer
) -> None:
    settings = cli.parse_args(["-j", BODY, "-r", "3"])
    out = io.StringIO()

    cli.run(settings, cli.load_request(settings, io.StringIO()), client, out)

    results = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["iteration"] for r in results] == [1, 2, 3]
    assert [r["created"] for r in results] == [True, False, False]
    assert len({r["id"] for r in results}) == 1
    assert {r["output"] for r in results} == {"A, C, B, D"}
    assert sorted(transformer.calls) == ["a", "b", "c", "d"]


def test_main_writes_output_file(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.httpx, "Client", lambda **_: client)
    output = tmp_path / "result.jsonl"

    assert cli.main(["-j", BODY, "-o", str(output)]) == 0
    assert json.loads(output.read_text())["output"] == "A, C, B, D"


def test_main_reports_invalid_input(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["-j", "not json"]) == 2
    assert "invalid input" in capsys.readouterr().err
