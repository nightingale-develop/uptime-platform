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
make docker-up
make docker-ps
```

`make docker-build` builds both backend and frontend images from local sources,
using `APP_IMAGE` and `FRONTEND_IMAGE` from `.env`. `make docker-rebuild` builds
both images and recreates the containers. To rebuild only the frontend of an
already running development stack:

```bash
make docker-build-frontend
docker compose up -d --no-deps --force-recreate frontend
```

The updater downloads published images for `/opt/uptime-platform`; it does not
build your local changes. Compose runs database migrations at startup.
Open <http://localhost:8080>. This port must be free; do not run the installed
frontend and the development frontend on the same port.

Open <http://localhost:8080/register> to create your account and organization.
The account receives the owner role.

```bash
make logs-api
make logs-scheduler
make logs-notification-worker
make docker-down
```

`docker-down` preserves data volumes. `make docker-reset` is destructive; do not use
it for the `/opt` installation. Keep `COMPOSE_PROJECT_NAME=uptime-platform-dev` set
for all development Compose/Make commands.

If migrations fail with `password authentication failed`, the password in `.env`
does not match the existing database. Changing `POSTGRES_PASSWORD` does not change
the password stored in a database volume. Restore the matching credentials or
use a separate development Compose project with its own database.

## Checks

```bash
uv sync
npm ci --prefix frontend
make lint
make test-unit
make test
```

The test suite uses `.env.test` and a disposable PostgreSQL service on port 5433.
The Make test targets load `.env.test` for both migrations and pytest;
`make test` starts that database, applies migrations, runs all backend tests,
then runs the frontend regression tests. Frontend tests require Node.js and the
dependencies installed by `npm ci --prefix frontend`; run them separately with
`make test-frontend`. For a direct pytest run,
use `uv run --env-file .env.test pytest`. Do not point tests at a production
database. Use `make format` to apply Ruff formatting and fixes.
