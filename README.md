# Uptime Platform

Self-hosted uptime monitoring with a REST API and web interface, built with FastAPI and Vue 3.

## Features

- HTTP, TCP, DNS, TLS certificate, and ICMP monitoring with uptime statistics and check history.
- Automatic incidents, maintenance windows, and notifications via webhook, Telegram, or email.
- Public status pages, responsive dashboard, organizations, role-based access, and API keys.
- Docker deployment with PostgreSQL and optional HTTPS via Caddy.

## Installation

**Requirements:** Linux, Docker with Docker Compose v2, Bash, Python 3, `curl`, `openssl`, and `getent`. Docker must be installed and running.

Download and run the installer:

```bash
curl -fL https://raw.githubusercontent.com/nightingale-develop/uptime-platform/main/install.sh -o install.sh
sudo bash install.sh
```

The installer asks for an address, administrator credentials, and an organization name. It downloads the backend and frontend Docker images, creates the configuration, runs database migrations, and displays the application URL.

- **`localhost`:** `http://localhost:8080` (this computer only).
- **Domain:** HTTPS via Caddy; point DNS to the server and open ports 80/443.
- **IPv4 or blank input:** IP-based HTTPS via Caddy's private CA. Browsers will not trust the certificate until the CA is installed; automatic public-IP detection does not guarantee incoming connectivity.

Installation files and data are stored under `/opt/uptime-platform`. Re-running the installer preserves the database and secrets but pulls current `latest` images; **back up the database and `.env` before updating**.

## Management

```bash
cd /opt/uptime-platform
sudo docker compose ps -a
sudo docker compose logs --tail=100 api frontend
```

For domain/IP installations, include `--profile public` in Compose commands to include Caddy. To stop services without deleting data:

```bash
sudo docker compose --profile public down
```

API documentation: `<application URL>/backend/docs`.

## Docker images

- Backend: [`sashastudent/uptime-platform:latest`](https://hub.docker.com/r/sashastudent/uptime-platform)
- Frontend: [`sashastudent/uptime-platform-frontend:latest`](https://hub.docker.com/r/sashastudent/uptime-platform-frontend)

Both images are downloaded automatically by the installer. The complete application runs through Docker Compose.

## Security notes

The installer creates an organization owner, not a system-wide administrator. Public registration remains available unless separately disabled. Before exposing an installation to the internet, review monitor-target/SSRF protections, firewall rules, TLS trust, and backups.

## License

[MIT](LICENSE).
