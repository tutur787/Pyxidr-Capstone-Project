.PHONY: build run notebook shell down clean help

build:
	docker compose build

run:
	docker compose up optimization

notebook:
	docker compose --profile notebook up

shell:
	docker compose run --rm optimization bash

down:
	docker compose --profile notebook down

clean:
	docker compose --profile notebook down --volumes --remove-orphans

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  build     Build the Docker image"
	@echo "  run       Run the optimization pipeline"
	@echo "  notebook  Start JupyterLab (http://localhost:8888)"
	@echo "  shell     Open a bash shell inside the container"
	@echo "  down      Stop running containers"
	@echo "  clean     Stop containers and remove volumes"
