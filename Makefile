.PHONY: build up down logs api worker restart

build:
	docker compose build --no-cache

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

api:
	docker compose restart api

worker:
	docker compose restart worker

restart:
	docker compose restart
