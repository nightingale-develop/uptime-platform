# Local development

Use the source checkout and Makefile for development. `install.sh` and `update.sh`
are exclusively for the installation in `/opt/uptime-platform`.

## Build and run Docker locally

Requires Git, Docker Compose, Make and uv for Python checks.

```bash
git clone https://github.com/nightingale-develop/uptime-platform.git
cd uptime-platform
cp .env.example .env
```

In this development `.env`, set image names to `uptime-platform:dev` and
`uptime-platform-frontend:dev` using `APP_IMAGE` and `FRONTEND_IMAGE`. Use development
secrets and add `http://localhost:8080` to `CORS_ALLOWED_ORIGINS`.

Use a separate Compose project to keep development data separate from `/opt`:

```bash
export COMPOSE_PROJECT_NAME=uptime-platform-dev
make docker-build
docker build -t uptime-platform-frontend:dev frontend
make docker-up
make docker-ps
```

The existing `docker-build` Make target builds the backend; the frontend command
uses `frontend/` as its build context. Compose runs database migrations at startup.
Open <http://localhost:8080>. This port must be free; do not run the installed
frontend and the development frontend on the same port.

To create the initial owner, read the password without recording it in shell history:

```bash
read -r -s -p 'Owner password: ' owner_password; printf '\n'
printf '%s\n' "$owner_password" | docker compose run --rm -T --no-deps api python -m uptime_platform.cli bootstrap-admin --email owner@example.com --organization Development
unset owner_password
```

```bash
make logs-api
make logs-scheduler
make logs-notification-worker
make docker-down
```

`docker-down` preserves data volumes. `make docker-reset` is destructive; do not use
it for the `/opt` installation. Keep `COMPOSE_PROJECT_NAME=uptime-platform-dev` set
for all development Compose/Make commands.

## Python checks

```bash
uv sync
make lint
make test-unit
make test
```

The test suite uses `.env.test` and a disposable PostgreSQL service on port 5433.
The Make test targets load `.env.test` for both migrations and pytest;
`make test` starts that database and applies migrations. For a direct pytest run,
use `uv run --env-file .env.test pytest`. Do not point tests at a production
database. Use `make format` to apply Ruff formatting and fixes.
