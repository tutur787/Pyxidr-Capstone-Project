# Build context is the repo root (see docker-compose.yml) because the backend
# reaches outside backend/ at runtime: it imports src/agent/ (agent_service.py)
# and runs Optimization/fabn_data_pipeline.py via runpy (optimizer_service.py).
FROM python:3.12.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY src/ ./src/
COPY Optimization/fabn_data_pipeline.py Optimization/fabn_finance.py ./Optimization/
COPY FABN.xlsx ./FABN.xlsx

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
