# Uptime Platform

![Version](https://img.shields.io/badge/version-1.1.0-blue)
[![Docker Pulls](https://img.shields.io/docker/pulls/sashastudent/uptime-platform)](https://hub.docker.com/repository/docker/sashastudent/uptime-platform)


Self-hosted uptime monitoring with a web dashboard and REST API, built with FastAPI and Vue 3.

## Quick start

**Requirements:** Linux, Docker with Compose v2, Bash, Python 3, `curl`, `openssl`, and `getent`.

```bash
curl -fL https://raw.githubusercontent.com/nightingale-develop/uptime-platform/main/install.sh -o install.sh
sudo bash install.sh
```

The installer asks for an address, owner credentials, and an organization name. It downloads the Docker images, configures the application, runs migrations, and prints the URL.

- **Local:** choose `localhost` → <http://localhost:8080> (accessible only on this computer).
- **Domain:** point DNS to the server and open ports 80/443; Caddy handles HTTPS.
- **IP / automatic detection:** Caddy uses a private CA. Browsers will not trust its certificate until you install that CA; a detected public IP does not guarantee external connectivity.

The installation lives in `/opt/uptime-platform`. **Back up PostgreSQL and `.env` before rerunning the installer:** it preserves data and secrets but pulls the current `latest` images.

## Features

- HTTP, TCP, DNS, TLS certificate, and ICMP checks, with history and uptime statistics.
- Automatic incidents, maintenance windows, and webhook, Telegram, or email notifications.
- Public status pages, organizations, role-based access, and API keys.
- Docker deployment with PostgreSQL; optional HTTPS and Prometheus/Grafana monitoring.
- Concurrent schedulers with expiring PostgreSQL leases and crash recovery.

## Screenshots

<img src="docs/screenshots/dashboard.png" alt="Dashboard" width="800">

<img src="docs/screenshots/monitor-details.png" alt="Monitor details" width="800">

<img src="docs/screenshots/status-page.png" alt="Status page" width="800">


## Manage your installation

```bash
cd /opt/uptime-platform
sudo docker compose ps -a
sudo docker compose logs --tail=100 api frontend
```

For domain/IP deployments, add `--profile public` to Compose commands to include Caddy. API documentation is available at `<application URL>/backend/docs`.

**Docker images:** [backend](https://hub.docker.com/r/sashastudent/uptime-platform) and [frontend](https://hub.docker.com/r/sashastudent/uptime-platform-frontend). The installer pulls both. Use matching version tags for releases (`1.1.0` when published); `latest` follows the most recently published build.

## Upgrading to 1.1.0

Version 1.1.0 introduces safe concurrent schedulers and optional platform observability. Before upgrading from 1.0.0:

1. Back up PostgreSQL and `.env`; preserve your Compose project name and volumes.
2. Stop **all old schedulers** before applying the lease migration. Older instances do not respect leases.
3. Upgrade backend and frontend together, using matching images or building this checkout locally.

Follow the [scheduler upgrade instructions](docs/scheduler.md) for the exact sequence. Existing installer deployments also need the updated `compose.yml` and `observability/` directory to enable monitoring.

If migration startup fails with `InvalidPasswordError`, verify that `POSTGRES_PASSWORD` matches the password already stored in PostgreSQL. Changing `.env` does not reset an existing database user's password. **Do not run `docker compose down -v` to fix this:** it deletes data volumes.

## Prometheus and Grafana (optional)

The `observability` Compose profile monitors the platform itself: API, scheduler, notification worker, and notification backlog. It includes a provisioned [Grafana dashboard](observability/grafana/dashboards/uptime-platform.json) and [four alert rules](observability/prometheus/alerts.yml).

**Until the updated images are published, build from this checkout** using your existing deployment `.env`:

```bash
docker build -t uptime-platform:observability .
docker build -t uptime-platform-frontend:observability frontend
export APP_IMAGE=uptime-platform:observability
export FRONTEND_IMAGE=uptime-platform-frontend:observability
docker compose --profile observability up -d
```

For an `install.sh` deployment, first back up its `.env` and Compose file, then copy this checkout's `compose.yml` and `observability/` into `/opt/uptime-platform`. Build images in the checkout, run Compose in the installation directory, preserve its project name and volumes, and add `--profile public` if Caddy is in use. The installer does not fetch the observability configuration automatically. Keep both image variables set for subsequent Compose commands.

- **Prometheus:** <http://localhost:9090> → **Status → Targets** and **Alerts**.
- **Grafana:** <http://localhost:3000> → sign in with `admin` / `admin` and change the password. Its data source and dashboard are provisioned automatically.

Both interfaces bind to localhost; use an SSH tunnel for a remote server. To use an existing Grafana, [import the dashboard JSON](observability/grafana/dashboards/uptime-platform.json) and select your Prometheus data source.

The API exports `/metrics` on port `8000`, scheduler on `9001`, and notification worker on `9002`. Background exporter ports are internal to the Compose network, and the frontend blocks public access to `/backend/metrics`. Run one Python process per container and scale containers, not FastAPI workers.

Metrics cover checks, check duration, the last successful scheduler cycle, delivery outcomes, and the PostgreSQL-backed notification queue. Counters reset on restart and may lose increments if a process crashes before its next scrape; queue size is read from PostgreSQL and is not subject to that loss. Prometheus evaluates the alerts, but **sending alert notifications requires a separately configured Alertmanager**. Adjust scheduler-stall and backlog thresholds for your workload.

Stop monitoring without removing its volumes:

```bash
docker compose --profile observability stop grafana prometheus
```

## Security and development notes

The installer creates an **organization owner**, not a system-wide administrator. Public registration remains available unless separately disabled. Before exposing the app to the internet, review monitor-target/SSRF protections, firewall rules, TLS trust, and backups.

Local knowledge-base, Obsidian, and agent-context files are excluded from Git and Docker build contexts. Keep them private. Scheduler coordination details and tests are documented in [docs/scheduler.md](docs/scheduler.md).

## License

[MIT](LICENSE).
