# BigQuery Test — VS Code / Jupyter

A small exercise to confirm that we can query the capstone tables hosted in BigQuery
(`Agg_Spread_Long`, `Agg_Fixed_Field`) from a Jupyter notebook running in VS Code,
and produce one table + one chart (average latest spread by BICS Level 1 sector).

## 1. Install the Google Cloud SDK (one time)

On macOS:

```bash
brew install --cask google-cloud-sdk
```

This gives you the `gcloud` command-line tool.

## 2. Authenticate — Application Default Credentials (ADC)

ADC is the recommended approach for local development: no key files to manage,
no env vars to set. You log in once with your Google account, and any Python
library that talks to Google Cloud (including `google-cloud-bigquery`) will
automatically pick up your credentials.

```bash
gcloud auth application-default login
```

A browser window opens — pick the Google account that has access to the
BigQuery project where you uploaded the tables. After approval, the credentials
are stored in `~/.config/gcloud/application_default_credentials.json`.

Then set your default project (replace with your actual GCP project ID):

```bash
gcloud config set project YOUR_PROJECT_ID
```

That's it. You won't need to repeat this unless the credentials expire (rare on
a personal laptop) or you switch Google accounts.

> **Service account JSON keys** are an alternative (used on servers / CI), but
> for local dev on your laptop ADC is simpler and safer.

## 3. Install Python dependencies

From the repo root, in your Python environment:

```bash
pip install -r bigquery_test/requirements.txt
```

## 4. Run the notebook

1. Open `bq_sector_spread.ipynb` in VS Code.
2. In the first cell, set `PROJECT_ID` and `DATASET` to your values.
3. Select your Python kernel (top-right of the notebook).
4. **Run All**.

### Expected output

- **Cell 2** prints the list of tables in the dataset (you should see
  `Agg_Spread_Long` and `Agg_Fixed_Field`).
- **Cell 4** displays a DataFrame with one row per BICS Level 1 sector.
- **Cell 5** renders a horizontal bar chart of average latest spread by sector.

If cell 2 fails with an auth error, redo step 2.
If it fails with "dataset not found", double-check `PROJECT_ID` / `DATASET`.
