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
    │       Gurobi SAP LP → result dict
    │
    └─► fabn_optimizer_sap.export_fabn_results(...)
            Writes CSVs under DATA_OUTPUT_DIR when optimal
```

## Modules

| File | Role |
|------|------|
| `optimization.py` | Logging + `run_fabn_job()` entrypoint |
| `fabn_pipeline.py` | `FabnPipelineParams`, `build_pipeline()` |
| `fabn_finance.py` | Book yield, duration, C-1 factors |
| `fabn_sap_solve.py` | `solve_sap()` — Gurobi model |
| `fabn_optimizer_sap.py` | `FabnSolveResult`, `load_pipeline`, `export_fabn_results` |
| `fabn_job.py` | `run_fabn_job()` — used by the agent |

## Outputs

`DATA_OUTPUT_DIR` (default `./data/output` locally; `/app/data/output` in Docker): `optimizer_results.csv`, `sap_summary.csv` when optimal.
