# FABN optimization (`src/`)

Self-contained production Python for the FABN SAP portfolio workflow: BigQuery inputs, Gurobi solve, CSV export. The `Optimization/` folder remains for notebooks and exploratory work; the Docker image only needs `src/`.

## Flow

```
optimization.py          Entrypoint (Docker CMD)
    │
    ├─► fabn_pipeline.build_pipeline()
    │       BigQuery + FRED → pipeline dict
    │
    ├─► fabn_sap_solve.solve_sap()
    │       Gurobi SAP LP → result dict (allocations, trades, cashflows, …)
    │
    └─► fabn_optimizer_sap.export_fabn_results(...)
            Writes CSVs under DATA_OUTPUT_DIR when optimal

agent_cli.py             Optional NL / JSON orchestration (see agent/)
    └─► fabn_job.run_fabn_job() → same pipeline + solve + export
            SELECT queries on last job (summary, holdings delta, recommended trades)
```

## Modules

| File | Role |
|------|------|
| `optimization.py` | Logging + `run_fabn_job()` entrypoint |
| `fabn_pipeline.py` | `FabnPipelineParams`, `build_pipeline()` |
| `fabn_finance.py` | Book yield, duration, C-1 factors |
| `fabn_sap_solve.py` | `solve_sap()` — Gurobi model; builds `trades` buy/sell list |
| `fabn_optimizer_sap.py` | `FabnSolveResult`, `load_pipeline`, `export_fabn_results` |
| `fabn_job.py` | `run_fabn_job()` — used by the agent |
| `agent/` | Orchestration agent — [`agent/README.md`](agent/README.md) |
| `agent_cli.py` | CLI: `run`, `select`, `chat` |

## Solver output

When optimal, `solve_sap()` returns a dict including:

| Key | Description |
|-----|-------------|
| `allocations` | Per-bond optimal holdings (`h_opt`, `h_curr`, weight, spread, duration, …) |
| **`trades`** | Recommended buys/sells for the optimization date: bonds with \|Δ\| > $100k, top 15 buys + top 15 sells. Each row has `action` (`BUY`/`SELL`), `cusip`, `sector`, `rating`, `delta_usd`, `delta_weight_pct`, `spread_bps`, `duration`. |
| `cashflows` | Quarterly asset vs FABN liability cashflows |
| `sap_val`, `nii_val`, … | Objective components and portfolio metrics |

`FabnSolveResult.from_raw()` keeps the full dict on `solve.raw` (including `trades`) for the agent and API consumers.

## File outputs

`DATA_OUTPUT_DIR` (default `./data/output` locally; `/app/data/output` in Docker): `optimizer_results.csv`, `sap_summary.csv` when optimal. Trade recommendations are available in the solve result and via the agent `recommended_trades` query — not written to a separate CSV today.

## Agent

Natural-language and structured queries over the same pipeline live under [`agent/`](agent/README.md). After a confirmed run, use `select` with `query_id: "recommended_trades"` (or ask in chat) to list suggested buy/sell bonds for that date.

## Tests

Unit tests for the agent (schemas, SELECT catalog, Qwen JSON helpers) live in [`../tests/`](../tests/README.md). They run without Gurobi, BigQuery, or live HF API calls:

```bash
PYTHONPATH=src pytest tests/ -q
```
