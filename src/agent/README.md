# FABN orchestration agent (`src/agent/`)

Natural-language and structured interface over the **deterministic** FABN pipeline. The agent translates user input into validated `AgentTurn` JSON, then dispatches to `fabn_job.run_fabn_job()` or read-only result queries. It does not modify the Gurobi model or generate BigQuery SQL.

Entry point for users: [`../agent_cli.py`](../agent_cli.py) (run from project root with `PYTHONPATH=src` or inside Docker).

## Flow

```
User message (chat) or JSON (turn/run/select)
    │
    ├─► qwen_translator.py     HF Inference API → AgentTurn JSON (chat only)
    │       or parse_turn_json / Pydantic (structured CLI)
    │
    ├─► validators.py          Business rules (dates, positive budgets, …)
    ├─► mapper.py                RunRequest → FabnPipelineParams
    │
    └─► orchestrator.py          handle_turn()
            ├─ intent=run  → preview (confirm=false) or run_fabn_job (confirm=true)
            └─ intent=select → catalog.py (fixed queries on last job)
```

## Modules

| File | Role |
|------|------|
| **`schemas.py`** | Pydantic models: `RunRequest`, `SelectRequest`, `AgentTurn`. Contract between LLM, CLI, and orchestrator. |
| **`validators.py`** | Fail-closed checks (e.g. no future `optimization_date`, positive `budget_usd`). Raises `ValidationError`. |
| **`mapper.py`** | Maps `RunRequest` fields onto `FabnPipelineParams` (`H`, `eps_D`, `RBC_bar`, `cost_of_capital`→`gamma_w`, `savings_rate_scalar`→`lambda_w`, `w_max`, `n_min`). |
| **`catalog.py`** | Fixed **SELECT** queries: `summary_metrics`, `top_holdings_delta`, `recommended_trades`. No LLM-generated SQL/pandas. |
| **`orchestrator.py`** | `AgentSession`, `handle_turn()`, `translate_user_message()`, JSON response formatting. |
| **`qwen_translator.py`** | Hugging Face Inference API client for `Qwen/Qwen2.5-7B-Instruct` (env: `HF_TOKEN`, optional `HF_AGENT_MODEL`). |
| **`prompts.py`** | System prompt for NL → `AgentTurn` JSON. |
| **`__init__.py`** | Exports `AgentTurn`, `RunRequest`, `SelectRequest` only (avoids pulling Gurobi/BQ on lightweight imports). |

## Intents (v1)

| Intent | Meaning | Side effects |
|--------|---------|----------------|
| **`run`** | Configure optimization | `confirm=false` → parameter preview only; `confirm=true` → full pipeline + solve + CSV export |
| **`select`** | Query last job | Read-only; requires a completed job in `AgentSession.last_job` |
| **`unsupported`** | Out of scope | No solver run |

## SELECT queries

Fixed read-only queries against `AgentSession.last_job` (run an optimization with `confirm=true` first).

| `query_id` | Purpose | Key fields |
|------------|---------|------------|
| **`summary_metrics`** | High-level SAP objective and risk metrics | `sap_objective_usd`, `statutory_nii_usd`, `duration_avg_years`, `output_dir`, … |
| **`top_holdings_delta`** | Largest position changes vs current book | `bond`, `h_opt_usd`, `h_curr_usd`, `delta_usd`, `spread_bps` |
| **`recommended_trades`** | Buy/sell list for the optimization date | `action` (`BUY`/`SELL`), `cusip`, `sector`, `rating`, `delta_usd`, `delta_weight_pct`, `spread_bps`, `duration` |

`recommended_trades` reads the `trades` list produced by `solve_sap()` in [`../fabn_sap_solve.py`](../fabn_sap_solve.py): bonds with \|Δ\| > $100k, top 15 buys plus top 15 sells (rebalance from current to optimal holdings on that date). Use `limit` (default 10, max 100) to cap rows returned.

After a confirmed run, the orchestrator returns **`summary_metrics`** only; request **`recommended_trades`** (or other queries) in a follow-up `select` turn or chat message.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN` | Hugging Face API token (required for `chat`) |
| `HF_AGENT_MODEL` | Model id (default: `Qwen/Qwen2.5-7B-Instruct`) |
| `GCP_PROJECT_ID`, `BIGQUERY_DATASET`, `FABN_OPTIMIZATION_DATE` | Passed through `FabnPipelineParams.from_env()` as session defaults |
| `DATA_OUTPUT_DIR` | Where optimizer CSVs are written after a confirmed run |

See [`.env.example`](../../.env.example) at the project root.

## CLI examples

Structured JSON (no LLM):

```bash
python src/agent_cli.py run --json '{"optimization_date":"2025-01-15","budget_usd":500000000,"confirm":false}'
python src/agent_cli.py run --json '{"optimization_date":"2025-01-15","budget_usd":500000000,"confirm":true}'
python src/agent_cli.py select --json '{"query_id":"summary_metrics"}'
python src/agent_cli.py select --json '{"query_id":"top_holdings_delta","limit":10}'
python src/agent_cli.py select --json '{"query_id":"recommended_trades","limit":20}'
```

Natural language (HF Inference API):

```bash
python src/agent_cli.py chat --message "Run optimization as of 2025-01-15 with 500 million budget"
python src/agent_cli.py chat --message "What bonds should I buy or sell from the last run?"
python src/agent_cli.py chat --repl
```

Docker:

```bash
make build
make agent-chat   # interactive REPL
```

## Design notes

- **Deterministic core:** All optimization math lives in `src/fabn_pipeline.py`, `src/fabn_sap_solve.py`, and `src/fabn_finance.py`; the agent only orchestrates.
- **Confirm gate:** Runs with side effects require `confirm: true` on `RunRequest` (typically after a preview turn).
- **Session state:** `AgentSession` holds `last_job` (for SELECT) and `chat_history` (for multi-turn Qwen calls). State is in-process only (not persisted across CLI invocations unless using `--repl` in one process).

## Related code

| Path | Relationship |
|------|----------------|
| [`../fabn_job.py`](../fabn_job.py) | `run_fabn_job()` — build → solve → export |
| [`../fabn_pipeline.py`](../fabn_pipeline.py) | `FabnPipelineParams`, `build_pipeline()` |
| [`../fabn_sap_solve.py`](../fabn_sap_solve.py) | `solve_sap()` |
| [`../agent_cli.py`](../agent_cli.py) | CLI: `turn`, `run`, `select`, `chat` |

Tests for this package live in [`../../tests/`](../../tests/README.md).
