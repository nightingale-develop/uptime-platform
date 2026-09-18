# Uptime Platform

![Version](https://img.shields.io/badge/version-1.2.0-blue)
[![Docker Pulls](https://img.shields.io/docker/pulls/sashastudent/uptime-platform)](https://hub.docker.com/repository/docker/sashastudent/uptime-platform)


Self-hosted uptime monitoring with a web dashboard and REST API, built with FastAPI and Vue 3.

## Quick start

**Requirements:** Linux, Docker with Compose v2, Bash, Python 3, `curl`, `openssl`, and `getent`.

```bash
curl -fL https://raw.githubusercontent.com/nightingale-develop/uptime-platform/v1.2.0/install.sh -o install.sh
sudo bash install.sh
```

The installer asks for an address, owner credentials, and an organization name. It downloads the Docker images, configures the application, runs migrations, and prints the URL.

- **Local:** choose `localhost` → <http://localhost:8080> (accessible only on this computer).
- **Domain:** point DNS to the server and open ports 80/443; Caddy handles HTTPS.
- **IP / automatic detection:** Caddy uses a private CA. Browsers will not trust its certificate until you install that CA; a detected public IP does not guarantee external connectivity.

The installation lives in `/opt/uptime-platform`. **Back up PostgreSQL and `.env` before rerunning the installer:** existing installations are updated through `update.sh`, preserving secrets and backing up configuration and PostgreSQL.

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

**Docker images:** [backend](https://hub.docker.com/r/sashastudent/uptime-platform) and [frontend](https://hub.docker.com/r/sashastudent/uptime-platform-frontend). The installer pulls both. Use matching version tags for releases (`1.2.0`); `latest` follows the most recently published build.

## Updating an install.sh deployment

**No Git checkout or local build is needed.** Application code is in Docker
images; Compose, settings and the updater live in `/opt/uptime-platform`.

For an installation created before 1.2.0, download the updater once:

~~~bash
curl -fL https://raw.githubusercontent.com/nightingale-develop/uptime-platform/v1.2.0/update.sh -o update.sh
sudo bash update.sh --version 1.2.0
~~~

New installations already include it:

~~~bash
sudo bash /opt/uptime-platform/update.sh --version 1.2.0
~~~

Replace the version with a published release when updating again. Add
`--observability` to install and start Prometheus/Grafana too. Existing monitoring
and Caddy are detected and retained.

The updater downloads Compose, monitoring configuration and the next updater
from the selected Git tag, and pulls both matching application images **before
stopping services**. It then backs up configuration, stops API/frontend/scheduler/
worker, dumps PostgreSQL, applies the migration and starts the new version. It
preserves all secrets, the project name and data volumes, and pins both image
variables in `.env` to the selected release. Fresh installs also use pinned images.

Configuration and database backups are stored under
`/opt/uptime-platform/backups/pre-VERSION-TIMESTAMP.*`. Copy successful backups to
separate storage and manage their retention. Caddy configuration is copied;
certificate volumes are preserved but are not included in the SQL/config backup.
Stop scheduler/worker replicas on other hosts before updating the shared database.
The updater coordinates one installer-managed Compose installation only.

If download or image pull fails, the application is left running. If backup or
migration fails after stopping it, the updater reports the backup path and leaves
application processes stopped for diagnosis. It never deletes volumes or attempts
automatic database rollback. A rollback after schema changes requires restoring
a compatible database/configuration backup, not just selecting an older image.

Only installer-managed configurations are replaced. A custom Compose file without
the ownership marker is rejected. Preserve custom changes separately and use the
[manual upgrade procedure](docs/updating.md) for a customized deployment.

Check the result:

~~~bash
cd /opt/uptime-platform
sudo docker compose ps -a
sudo docker compose logs --tail=50 api scheduler notification-worker
curl -fsS http://localhost:8080/backend/health
~~~

## What's new in 1.2.0

- Notification workers claim executable waves, use unique lease tokens to guard
  writes/releases, bound total send time and clean up on SIGTERM. See
  [worker coordination and upgrade details](docs/notification-worker.md).
- Worker cycle freshness is visible in Grafana and has a Prometheus stall alert.
- Standalone updates download version-matched images and deployment files, preserve
  settings, create backups and run migrations without requiring Git or source files.
- Installer and updater use the same release Compose file and include optional
  monitoring configuration. Existing installations no longer repeat owner bootstrap.

## Upgrading to 1.1.0

Version 1.1.0 introduces safe concurrent schedulers and optional platform observability. Before upgrading from 1.0.0:

1. Back up PostgreSQL and `.env`; preserve your Compose project name and volumes.
2. Stop **all old schedulers** before applying the lease migration. Older instances do not respect leases.
3. Upgrade backend and frontend together, using matching images or building this checkout locally.

Follow the [scheduler upgrade instructions](docs/scheduler.md) for the exact sequence. The updater now downloads the matching Compose and monitoring configuration for installer deployments.

If migration startup fails with `InvalidPasswordError`, verify that `POSTGRES_PASSWORD` matches the password already stored in PostgreSQL. Changing `.env` does not reset an existing database user's password. **Do not run `docker compose down -v` to fix this:** it deletes data volumes.

## Prometheus and Grafana (optional)

The `observability` Compose profile monitors the platform itself: API, scheduler, notification worker, and notification backlog. It includes a provisioned [Grafana dashboard](observability/grafana/dashboards/uptime-platform.json) and [alert rules](observability/prometheus/alerts.yml).

For an installer deployment, enable monitoring while updating:

~~~bash
sudo bash /opt/uptime-platform/update.sh --version 1.2.0 --observability
~~~

Older installations first download update.sh as described above. For a source
checkout with configured `.env`, use the published release images:

~~~bash
export APP_IMAGE=sashastudent/uptime-platform:1.2.0
export FRONTEND_IMAGE=sashastudent/uptime-platform-frontend:1.2.0
docker compose --profile observability up -d
~~~

Existing databases must be upgraded with old workers stopped first; see the
[manual procedure](docs/updating.md). For local development, build backend from
`.` and frontend from `frontend`, then select those local images instead.

- **Prometheus:** <http://localhost:9090> → **Status → Targets** and **Alerts**.
- **Grafana:** <http://localhost:3000> → sign in with `admin` / `admin` and change the password. Its data source and dashboard are provisioned automatically.

Both interfaces bind to localhost; use an SSH tunnel for a remote server. To use an existing Grafana, [import the dashboard JSON](observability/grafana/dashboards/uptime-platform.json) and select your Prometheus data source.

The API exports `/metrics` on port `8000`, scheduler on `9001`, and notification worker on `9002`. Background exporter ports are internal to the Compose network, and the frontend blocks public access to `/backend/metrics`. Run one Python process per container and scale containers, not FastAPI workers.

Metrics cover checks, check duration, the last successful scheduler and worker cycles, delivery outcomes, and the PostgreSQL-backed notification queue. Counters reset on restart and may lose increments if a process crashes before its next scrape; queue size is read from PostgreSQL and is not subject to that loss. Prometheus evaluates the alerts, but **sending alert notifications requires a separately configured Alertmanager**. Adjust scheduler-stall and backlog thresholds for your workload.

Stop monitoring without removing its volumes:

```bash
docker compose --profile observability stop grafana prometheus
```

## Security and development notes

The installer creates an **organization owner**, not a system-wide administrator. Public registration remains available unless separately disabled. Before exposing the app to the internet, review monitor-target/SSRF protections, firewall rules, TLS trust, and backups.

Local knowledge-base, Obsidian, and agent-context files are excluded from Git and Docker build contexts. Keep them private. Scheduler coordination details and tests are documented in [docs/scheduler.md](docs/scheduler.md).

## License

[MIT](LICENSE).
