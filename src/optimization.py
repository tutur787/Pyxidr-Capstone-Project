"""
FABN Portfolio Optimization Pipeline
=====================================
Entry point for the containerized optimization pipeline.

Environment variables
---------------------
DATA_INPUT_DIR       : path to input data directory (local mode)
DATA_OUTPUT_DIR      : path to output data directory (local mode)
GCP_PROJECT_ID       : GCP project for BigQuery
BIGQUERY_DATASET     : BigQuery dataset name (default: Securities)
FABN_OPTIMIZATION_DATE : optimization as-of date (YYYY-MM-DD)
GCS_INPUT_BUCKET     : GCS bucket for input data (GCP mode)
GCS_OUTPUT_BUCKET    : GCS bucket for output data (GCP mode)
GRB_WLSACCESSID      : Gurobi WLS access ID
GRB_WLSSECRET        : Gurobi WLS secret
GRB_LICENSEID        : Gurobi WLS license ID
LOG_LEVEL            : logging level (default INFO)
"""

from __future__ import annotations

import logging
import os
import sys

from fabn_job import run_fabn_job
from fabn_pipeline import FabnPipelineParams


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )
    params = FabnPipelineParams.from_env()
    run_fabn_job(params)
    return 0


if __name__ == "__main__":
    sys.exit(main())
