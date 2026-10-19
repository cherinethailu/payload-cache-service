# payload-cache

A FastAPI microservice that builds payloads from two lists of strings. Each string goes
through a "transformer function" that stands in for an expensive external service. The
service caches transformer results in a database so that it calls the transformer as
rarely as possible.

```
POST /payload        {"list_1": [...], "list_2": [...]}  ->  {"id": "...", "message": "..."}
GET  /payload/{id}                                        ->  {"output": "A, X, B, Y, ..."}
```

## Quick start

```bash
docker compose up --build            # API on http://localhost:8000 (API_PORT to change)
pip install -e .                     # installs cache-cli
cache-cli -i examples/sample.json -r 3
```

Sample output. The first iteration pays for 6 transformer calls; the next two are served
entirely from the database:

```
{"iteration": 1, "id": "46b9...", "created": true,  "output": "FIRST STRING, OTHER STRING, ...", "elapsed_ms": 630.29}
{"iteration": 2, "id": "46b9...", "created": false, "output": "FIRST STRING, OTHER STRING, ...", "elapsed_ms": 3.14}
{"iteration": 3, "id": "46b9...", "created": false, "output": "FIRST STRING, OTHER STRING, ...", "elapsed_ms": 2.98}
```

To run against PostgreSQL instead of SQLite:

```bash
docker compose --profile postgres up --build api-postgres   # http://localhost:8001
```

Without Docker:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
uvicorn payload_cache.main:app --reload
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PAYLOAD_CACHE_DATABASE_URL` | `sqlite:///./payload_cache.db` | Any SQLAlchemy URL (SQLite or PostgreSQL) |
| `PAYLOAD_CACHE_TRANSFORMER_DELAY_SECONDS` | `0.1` | Simulated latency of the external transformer |

## CLI

```
cache-cli [-h|--host URL] [-r|--repeat N] [-i|--input FILE|-] [-j|--json JSON] [-o|--output FILE|-] [--help]
```

Each iteration posts the input and reads the payload back. Results are written as JSON
lines: id, whether the payload was newly created, output, and round-trip time. Exactly one
of `--input` / `--json` is required.

```bash
cache-cli -j '{"list_1": ["a"], "list_2": ["b"]}'
cat examples/sample.json | cache-cli -i - -o results.jsonl
```

**Deviation from the spec:** the spec gives `-h` to both `--host` and `--help`. Here `-h`
means `--host`, and help is only available as `--help`.

## Design

```
api.py  ->  service.py  ->  models.py (SQLModel)  ->  SQLite / PostgreSQL
                 \
                  -> transformer.py (simulated external service)
```

- **Two levels of reuse.**
  1. *Payload level.* A request is fingerprinted with a SHA-256 hash of its two lists.
     If the same lists were posted before, the service returns the existing id right away
     (HTTP 200 instead of 201) without touching the transformer cache.
  2. *String level.* For a new payload, the service collects the unique strings from both
     lists and loads every cached result in **one** query. It then calls the transformer
     only for the misses, once per distinct string. So a new request that overlaps with
     earlier ones only pays for the strings nobody has seen yet.
- **Why cache per string rather than per request:** the transformer is the expensive
  resource, and different requests often share strings. A per-request cache would
  transform `"first string"` again in every new combination.
- **The fingerprint is order-sensitive.** `(["a"], ["b"])` and `(["b"], ["a"])` produce
  different outputs, so they are different payloads. The lists are encoded as a JSON array
  of arrays, so list boundaries count: `(["a","b"], ["c"])` cannot collide with
  `(["a"], ["b","c"])`.
- **Payloads store their output.** Reads are a primary-key lookup. They do not have to
  rebuild the output from the cache.
- **Concurrency.** Cache rows are written with `INSERT ... ON CONFLICT DO NOTHING`, so two
  requests that miss on the same string don't fail. Both results are equal, and either one
  is kept. Payloads have a unique `input_hash`. If two identical requests race, the loser
  catches the `IntegrityError` and returns the winner's id. Cache rows are committed before
  the payload, so transformer results are never lost if a later step fails.
- **Testability.** `create_app()` accepts the engine and the transformer, so tests inject
  an in-memory database and a call-counting transformer without monkeypatching.

## Tests

```bash
pytest
```

- `tests/test_service.py`: unit tests for the hashing and interleaving helpers. Also
  tests the caching rules (the transformer is called once per distinct string, never for
  cached strings, and never for repeated payloads).
- `tests/test_api.py`: integration tests through HTTP → service → real SQLite, including
  validation errors and 404s.
- `tests/test_cli.py`: argument parsing, input sources (`--json`, file, stdin), and the
  full CLI run against the real app.

## Shortcuts and known limitations

- **No migrations.** Tables are created on startup with `create_all`. A production
  service would use Alembic.
- **No cache invalidation.** Entries live forever, which is correct as long as the
  transformer is deterministic. If the transformer can change, the cache key should
  include a transformer version.
- **Sync stack.** Sync SQLModel sessions and a sync transformer run in FastAPI's
  threadpool. That keeps the code simple. An async transformer client with concurrent
  calls for the misses would cut latency for large requests.
- **Limits.** Requests are capped at 1000 items per list and 1024 characters per string.
  This bounds the work one request can trigger and keeps cache keys indexable.
- **Ambiguous output.** The output is joined with `", "` as the spec requires. That is
  ambiguous if the strings themselves contain `", "`.
