# Uptime Platform

![Version](https://img.shields.io/badge/version-1.3.10-blue)
[![Docker Pulls](https://img.shields.io/docker/pulls/sashastudent/uptime-platform)](https://hub.docker.com/repository/docker/sashastudent/uptime-platform)
[![Helm](https://img.shields.io/badge/Helm-chart-0F1689?logo=helm&logoColor=white)](https://nightingale-develop.github.io/uptime-platform)

Self-hosted uptime monitoring with a FastAPI backend and Vue 3 dashboard.

- HTTP, TCP, DNS, TLS certificate and ICMP checks.
- Incidents, maintenance windows, webhook, Telegram, email and Slack notifications.
- Public status pages, organizations, roles and API keys.
- PostgreSQL, concurrent schedulers and notification workers.
- Optional HTTPS, Prometheus and Grafana.

## Install with Docker Compose

Requires Linux, Docker Compose v2, Bash, Python 3, curl, openssl, getent and flock.

```bash
curl -fL https://raw.githubusercontent.com/nightingale-develop/uptime-platform/refs/tags/latest/install.sh -o install.sh
sudo bash install.sh
```

The installer creates `/opt/uptime-platform`, configures Docker and asks for the
application address. After installation, open the displayed `/register` link to
create your account and organization. Your account receives the owner role.

- **This computer:** select `localhost`, then open <http://localhost:8080>.
- **Domain:** configure DNS and open ports 80/443; Caddy provides HTTPS.
- **IP address:** Caddy uses a private CA that must be trusted on client devices.

## Install with Helm

Uptime Platform can also be deployed to Kubernetes and OpenShift using the
public Helm repository.

```bash
helm repo add uptime-platform https://nightingale-develop.github.io/uptime-platform
helm repo update
```

### OpenShift

```bash
helm upgrade --install uptime-platform \
  uptime-platform/uptime-platform
```

The chart deploys PostgreSQL, runs database migrations, and starts the API,
scheduler, notification worker and frontend. On OpenShift, the application is
exposed using a Route.

### Kubernetes

Enable an Ingress and provide the application hostname:

```bash
helm upgrade --install uptime-platform \
  uptime-platform/uptime-platform \
  --set route.enabled=false \
  --set ingress.enabled=true \
  --set ingress.host=uptime.example.com
```

Depending on the cluster, an Ingress controller and `ingress.className` may also
need to be configured.

Available chart versions can be listed with:

```bash
helm search repo uptime-platform
```

To upgrade the release:

```bash
helm repo update
helm upgrade uptime-platform uptime-platform/uptime-platform
```

To uninstall it:

```bash
helm uninstall uptime-platform
```

Helm repository:
<https://nightingale-develop.github.io/uptime-platform>

API documentation: `<application URL>/backend/docs`.

## Screenshots

<img src="docs/screenshots/dashboard.png" alt="Dashboard" width="800">
<img src="docs/screenshots/monitor-details.png" alt="Monitor details" width="800">
<img src="docs/screenshots/status-page.png" alt="Status page" width="800">

## Update or reinstall

Installation and updates always use `/opt/uptime-platform`:

```bash
curl -fL https://raw.githubusercontent.com/nightingale-develop/uptime-platform/refs/tags/latest/update.sh -o update.sh
sudo bash update.sh
```

The updater selects the latest stable version. To update to a specific
version, use `sudo bash update.sh --version 1.3.1`.

Updates preserve configuration and data volumes and create a database backup.
See [installation and updates](docs/updating.md) for details and clean reinstall.
History is automatically removed after its [retention period](docs/retention.md).

## Check the application

Use the installation directory:

```bash
cd /opt/uptime-platform
sudo docker compose ps -a
sudo docker compose logs --tail=50 api scheduler notification-worker
curl -fsS http://localhost:8080/backend/health
```

Expected health response: `{"status":"ok"}`. This checks API availability;
worker progress is monitored separately.

## Prometheus and Grafana

Add `--observability` to the update command above to enable monitoring.
Existing monitoring is retained.

- [Prometheus](http://localhost:9090): check **Status → Targets** and **Alerts**.
- [Grafana](http://localhost:3000): initial login `admin` / `admin`; change the password.
- The data source and [dashboard](observability/grafana/dashboards/uptime-platform.json)
  are provisioned automatically. The same JSON can be imported into another Grafana.

Both interfaces bind to localhost; use an SSH tunnel for remote access.
Metrics cover checks, scheduler/worker progress, deliveries and notification backlog.
Counters reset on process restart; backlog comes from PostgreSQL. Alert delivery
requires a separately configured Alertmanager.

```bash
sudo docker compose --profile observability stop grafana prometheus
```

## Documentation

- [Installation, updates and clean reinstall](docs/updating.md)
- [Local development and Make commands](docs/development.md)
- [Scheduler coordination](docs/scheduler.md)
- [Notification worker coordination](docs/notification-worker.md)
- [Data retention and cleanup](docs/retention.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Pull request template](.github/pull_request_template.md)
- [MIT license](LICENSE)
