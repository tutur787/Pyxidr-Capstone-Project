FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV DATA_INPUT_DIR=/app/data/input
ENV DATA_OUTPUT_DIR=/app/data/output

RUN mkdir -p /app/data/input /app/data/output

CMD ["python", "src/optimization.py"]
