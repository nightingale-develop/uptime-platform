.PHONY: \
	dev-up \
	dev-down \
	migrate \
	test-db-up \
	test-db-down \
	test-migrate \
	test \
	test-frontend \
	test-unit \
	test-api \
	test-integration \
	test-fresh \
	format \
	lint \
	scheduler \
	notification-worker \
	docker-build \
	docker-build-backend \
	docker-build-frontend \
	docker-up \
	docker-down \
	docker-reset \
	docker-ps \
	logs-api \
	logs-scheduler \
	logs-notification-worker \
	docker-rebuild

.PHONY: release
VERSION ?= patch
export VERSION

release:
	bash scripts/release.sh "$$VERSION"


dev-up:
	docker compose up -d --wait postgres


dev-down:
	docker compose stop postgres


migrate:
	set -a; . ./.env; set +a; uv run alembic upgrade head


test-db-up:
	docker compose --profile test up -d --wait postgres-test


test-db-down:
	docker compose --profile test rm -sf postgres-test


test-migrate: test-db-up
	set -a; . ./.env.test; set +a; uv run alembic upgrade head


test-unit:
	set -a; . ./.env.test; set +a; uv run pytest tests/unit -v


test-api:
	set -a; . ./.env.test; set +a; uv run pytest tests/api -v


test-integration: test-migrate
	set -a; . ./.env.test; set +a; uv run pytest tests/integration -v


test: test-migrate
	set -a; . ./.env.test; set +a; uv run pytest -v
	$(MAKE) test-frontend


test-frontend:
	npm --prefix frontend test


test-fresh:
	docker compose --profile test rm -sf postgres-test
	$(MAKE) test


format:
	uv run ruff format .
	uv run ruff check --fix .


lint:
	uv run ruff format --check .
	uv run ruff check .


scheduler:
	uv run python -m uptime_platform.scheduler.main


notification-worker:
	uv run python -m uptime_platform.notifications.main


docker-build: docker-build-backend docker-build-frontend


docker-build-backend:
	set -a; . ./.env; set +a; \
	docker build \
		--no-cache \
		-t "$${APP_IMAGE:-sashastudent/uptime-platform:latest}" \
		.


docker-build-frontend:
	set -a; . ./.env; set +a; \
	docker build \
		--no-cache \
		-t "$${FRONTEND_IMAGE:-sashastudent/uptime-platform-frontend:latest}" \
		frontend


docker-up:
	docker compose up -d


docker-down:
	docker compose down --remove-orphans


docker-reset:
	docker compose down -v --remove-orphans
	$(MAKE) docker-build
	docker compose up -d --wait postgres
	$(MAKE) migrate
	docker compose up -d


docker-ps:
	docker compose ps


logs-api:
	docker compose logs -f api


logs-scheduler:
	docker compose logs -f scheduler


logs-notification-worker:
	docker compose logs -f notification-worker

docker-rebuild:
	$(MAKE) docker-build
	docker compose up -d --force-recreate
