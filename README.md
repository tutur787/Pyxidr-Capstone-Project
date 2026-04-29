# Pyxidr-Capstone-Project

## In data folder please see the Markdown file that goes over it

## In the Regulation folder, you can look at the excel to get further insights

---

## Running with Docker

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- A `.env` file in the project root with your credentials (copy `.env.example` to get started):
  ```bash
  cp .env.example .env
  # then fill in GRB_WLSACCESSID, GRB_WLSSECRET, GRB_LICENSEID, and GCP_PROJECT_ID
  ```
- GCP credentials set up locally (`gcloud auth application-default login`)

### Commands

| Command | Description |
|---|---|
| `make build` | Build the Docker image |
| `make run` | Run the optimization pipeline |
| `make notebook` | Start JupyterLab at http://localhost:8888 |
| `make shell` | Open a bash shell inside the container |
| `make down` | Stop running containers |
| `make clean` | Stop containers and remove volumes |
| `make help` | Print available commands |

### Typical workflow

```bash
# First time setup
cp .env.example .env   # fill in credentials in .env. NEVER COMMIT .ENV
make build

# Run the optimization pipeline
make run

# Or explore data interactively
make notebook          # open http://localhost:8888 in your browser
```

### How data flows

- Input data is read from `./arthur_data/` (mounted read-only into the container)
- Output results are written to `./data/` (mounted read-write, so results appear on your machine)
- GCP credentials are passed in from your local `~/.config/gcloud` — no service account key file needed
