# FABN optimization (`src/`)

hi, testing

This folder holds the **production-style** Python entrypoint for the Funding Agreement-Backed Notes (FABN) portfolio workflow: pull market and liability inputs, build arrays for the solver, run a **Gurobi** linear program, and write results to disk.

The notebooks under `Optimization/` are the original exploratory versions; behavior should stay aligned by changing code **here** first, then refreshing notebooks to import these modules if needed. 

## Flow

```
optimization.py          Entrypoint (Docker CMD)
    │
    ├─► fabn_pipeline.build_pipeline()
    │       BigQuery (universe, spreads, cashflows)
    │       FRED Treasury curve → durations
    │       C1 rating factors, FABN liability schedule
    │       → returns pipeline dict
    │
    ├─► fabn_optimizer.solve_fabn_nev(pipeline)
    │       Builds & solves LP (budget, RBC, duration band, CF shortfall, …)
    │       → returns (model, FabnSolveResult)
    │
    └─► fabn_optimizer.export_fabn_results(...)
            Writes CSVs under DATA_OUTPUT_DIR when status is optimal
```

## Modules

| File | Role |
|------|------|
| **`optimization.py`** | Configures logging, wires BigQuery client → pipeline → solve → export. Run as `python src/optimization.py` from the project root (or via Docker). |
| **`fabn_pipeline.py`** | **`FabnPipelineParams`** (defaults + **`from_env()`** for `GCP_PROJECT_ID`, `BIGQUERY_DATASET`, `FABN_OPTIMIZATION_DATE`). **`build_pipeline(client, params)`** returns the **`pipeline`** dict consumed by the optimizer. |
| **`fabn_optimizer.py`** | **`solve_fabn_nev`** builds the Gurobi model; **`FabnSolveResult`** holds scalar summaries and **`h_opt`**. **`export_fabn_results`** writes **`optimizer_results.csv`** (per bond) and **`nev_summary.csv`** (aggregate metrics). |

## The `pipeline` dict

`build_pipeline` returns one dictionary aligned with the notebook “pipeline output”: dimensions (`N`, `T`, `Q`), **`CUSIPS`**, per-bond arrays (`spread`, `durs`, `theta`, `score`, `h_curr`, …), cashflow matrices (`bond_cf`, `qtr_bond_cf`, `qtr_fabn_cf`, `t_vec`, `qtr_idx`), and scalar parameters (`H`, `D_FABN`, `gamma_w`, `eps_D`, …). The optimizer reads keys by name; keep keys stable if you extend the model.

## Inputs vs outputs

- **Inputs today:** **BigQuery** (configured project/dataset) and **FRED** (via `pandas_datareader`) for the Treasury curve. **Application Default Credentials** are expected (e.g. `gcloud auth application-default login`, or mounted credentials in Docker).
- **`DATA_INPUT_DIR`:** Reserved for a future “load from local files” path; the current pipeline **does not** read bond CSVs from disk.
- **Outputs:** **`DATA_OUTPUT_DIR`** (default `/app/data/output` in the image). With Compose, this is typically mounted to `./data/output` on the host. Files appear only when Gurobi returns an **optimal** solution.

## Environment variables (common)

See also the docstring at the top of **`optimization.py`**.

| Variable | Purpose |
|----------|---------|
| `GCP_PROJECT_ID`, `BIGQUERY_DATASET` | BigQuery location |
| `FABN_OPTIMIZATION_DATE` | As-of date (`YYYY-MM-DD`) |
| `DATA_OUTPUT_DIR` | Where CSV exports are written |
| `LOG_LEVEL` | Python logging level (e.g. `INFO`, `DEBUG`) |
| `GRB_WLSACCESSID`, `GRB_WLSSECRET`, `GRB_LICENSEID` | Gurobi WLS license (containerized runs) |

`GCS_*` bucket variables are placeholders for future upload/download logic and are not used by the current `fabn_*` modules.
