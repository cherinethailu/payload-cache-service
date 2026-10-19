"""cache-cli: drive the payload service from the command line.

Each iteration posts the same input and reads the resulting payload back, so running with
``--repeat`` shows the cache at work (same id, much lower latency after the first call).
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Self, TextIO

import httpx
from pydantic import AliasChoices, Field, HttpUrl, PositiveInt, ValidationError, model_validator
from pydantic_settings import (
    BaseSettings,
    CliApp,
    CliSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from payload_cache.schemas import PayloadCreate

STDIO = "-"


class CliSettings(BaseSettings):
    model_config = SettingsConfigDict(cli_kebab_case=True, cli_hide_none_type=True)

    host: HttpUrl = Field(
        default=HttpUrl("http://localhost:8000"),
        validation_alias=AliasChoices("host", "h"),
        description="Base URL of the payload service.",
    )
    repeat: PositiveInt = Field(
        default=1,
        validation_alias=AliasChoices("repeat", "r"),
        description="Number of create/read iterations.",
    )
    input: str | None = Field(
        default=None,
        validation_alias=AliasChoices("input", "i"),
        description="JSON file with list_1 and list_2 ('-' for stdin).",
    )
    json_body: str | None = Field(
        default=None,
        validation_alias=AliasChoices("json", "j"),
        description="Request body as a JSON string.",
    )
    output: str = Field(
        default=STDIO,
        validation_alias=AliasChoices("output", "o"),
        description="Where to write results as JSON lines ('-' for stdout).",
    )

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Command line only: generic environment variables such as HOST or INPUT must not
        # silently configure the tool.
        return (init_settings,)

    @model_validator(mode="after")
    def _exactly_one_input(self) -> Self:
        if (self.input is None) == (self.json_body is None):
            raise ValueError("provide exactly one of --input or --json")
        return self


def parse_args(argv: list[str]) -> CliSettings:
    # The task reserves -h for --host, so argparse's built-in -h/--help is replaced by a
    # --help-only flag.
    parser = argparse.ArgumentParser(
        prog="cache-cli", description=__doc__.splitlines()[0], add_help=False
    )
    parser.add_argument("--help", action="help", help="Show this message and exit.")
    source = CliSettingsSource(CliSettings, root_parser=parser)
    return CliApp.run(CliSettings, cli_args=argv, cli_settings_source=source)


def load_request(settings: CliSettings, stdin: TextIO) -> PayloadCreate:
    """Read and validate the request body before anything is sent to the server."""
    if settings.json_body is not None:
        raw = settings.json_body
    elif settings.input == STDIO:
        raw = stdin.read()
    else:
        raw = Path(settings.input).read_text()
    return PayloadCreate.model_validate_json(raw)


def run(settings: CliSettings, request: PayloadCreate, client: httpx.Client, out: TextIO) -> None:
    body = request.model_dump()
    for iteration in range(1, settings.repeat + 1):
        started = time.perf_counter()
        created = client.post("/payload", json=body)
        created.raise_for_status()
        payload_id = created.json()["id"]
        read = client.get(f"/payload/{payload_id}")
        read.raise_for_status()
        result: dict[str, Any] = {
            "iteration": iteration,
            "id": payload_id,
            "created": created.status_code == httpx.codes.CREATED,
            "output": read.json()["output"],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        out.write(json.dumps(result) + "\n")
        out.flush()


def main(argv: list[str] | None = None) -> int:
    try:
        settings = parse_args(sys.argv[1:] if argv is None else argv)
        request = load_request(settings, sys.stdin)
    except (ValidationError, OSError) as exc:
        print(f"cache-cli: invalid input: {exc}", file=sys.stderr)
        return 2

    out = sys.stdout if settings.output == STDIO else open(settings.output, "w")  # noqa: SIM115
    try:
        with httpx.Client(base_url=str(settings.host), timeout=30) as client:
            run(settings, request, client, out)
    except httpx.HTTPStatusError as exc:
        print(
            f"cache-cli: server returned {exc.response.status_code}: {exc.response.text}",
            file=sys.stderr,
        )
        return 1
    except httpx.HTTPError as exc:
        print(f"cache-cli: request failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if out is not sys.stdout:
            out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
