# Tests (`tests/`)

Lightweight unit tests for the FABN orchestration agent. They run **without** Gurobi, BigQuery, or live Hugging Face API calls so CI and local dev stay fast.

Configuration: [`pytest.ini`](../pytest.ini) sets `pythonpath = src` so imports match production (`agent.*`, `fabn_*`).

## Files

| File | What it covers |
|------|----------------|
| **`conftest.py`** | Prepends `src/` to `sys.path` (redundant with `pytest.ini`, safe fallback). |
| **`test_agent_schemas.py`** | `RunRequest` / `AgentTurn` JSON round-trip; `SelectRequest` including `recommended_trades`; `validate_run_request()` (e.g. rejects future dates). |
| **`test_agent_catalog.py`** | `execute_select()` for `summary_metrics`, `top_holdings_delta`, and `recommended_trades` using a synthetic job (`SimpleNamespace`, no `fabn_job` import). |
| **`test_qwen_translator.py`** | `_extract_json()` (plain JSON and markdown fences); `_hf_token()` error when env vars are unset. |

## What is not tested here

| Area | Reason |
|------|--------|
| Full `run_fabn_job()` | Requires GCP credentials, BigQuery, FRED, and Gurobi WLS |
| Live HF Inference API | Needs `HF_TOKEN` and network; would be flaky in CI |
| `mapper.run_request_to_params()` | Pulls `fabn_pipeline` (heavy deps); covered indirectly via integration runs |

Add integration tests separately (Docker + credentials) if you need end-to-end coverage.

## Run tests

From the project root:

```bash
pip install pytest pydantic numpy
pytest tests/
```

Or with explicit path:

```bash
PYTHONPATH=src pytest tests/ -q
```

Expected: **11 tests** passing (schemas, catalog including `recommended_trades`, qwen JSON helpers).

Inside Docker (after `make build`):

```bash
docker compose run --rm optimization pytest tests/ -q
```

(`pytest` is listed in [`requirements.txt`](../requirements.txt).)

## Adding tests

- Prefer **no** imports of `fabn_job`, `gurobipy`, or `google.cloud` in new unit tests.
- Use `SimpleNamespace` or small fixtures for job-like objects (see `test_agent_catalog.py`).
- Mock external APIs with `pytest.MonkeyPatch` (see `test_qwen_translator.py`).
- For Pydantic models, use `model_validate_json()` on minimal JSON blobs.

## Related docs

- Agent package: [`../src/agent/README.md`](../src/agent/README.md)
- Production pipeline: [`../src/README.md`](../src/README.md)
