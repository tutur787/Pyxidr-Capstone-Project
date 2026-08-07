.PHONY: build run notebook shell down clean help agent-chat dashboard dashboard-down

build:
	docker compose build

run:
	docker compose up optimization

notebook:
	docker compose --profile notebook up

shell:
	docker compose run --rm optimization bash

dashboard:
	docker compose up --build backend frontend

dashboard-down:
	docker compose down backend frontend

down:
	docker compose --profile notebook down

clean:
	docker compose --profile notebook down --volumes --remove-orphans

agent-chat:
	docker compose run --rm optimization python src/agent_cli.py chat --repl

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  build     Build the Docker image"
	@echo "  run       Run the optimization pipeline"
	@echo "  notebook  Start JupyterLab (http://localhost:8888)"
	@echo "  shell     Open a bash shell inside the container"
	@echo "  dashboard      Build + run the FastAPI backend (:8000) and React dashboard (:4173)"
	@echo "  dashboard-down Stop the backend + frontend containers"
	@echo "  agent-chat  Interactive agent (HF Inference API; set HF_TOKEN in .env)"
	@echo "  down      Stop running containers"
	@echo "  clean     Stop containers and remove volumes"
