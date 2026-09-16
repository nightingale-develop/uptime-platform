# Uptime Platform

[![Backend Docker Pulls](https://img.shields.io/docker/pulls/sashastudent/uptime-platform)](https://hub.docker.com/r/sashastudent/uptime-platform)
[Frontend image](https://hub.docker.com/r/sashastudent/uptime-platform-frontend)

Self-hosted uptime monitoring, incident management, notifications, public status pages, and web management UI built with FastAPI and Vue.js.

> **Release:** 1.0.0. The backend and responsive Vue.js management UI are included. The interactive installer supports localhost, a domain, or an IPv4 address. Review the deployment and security notes below before exposing an instance to the internet.
## Features

### Monitoring

* HTTP, TCP, DNS, TLS certificate, and ICMP monitoring with automatic scheduling and check history
* Typed monitor configurations for all supported monitor types
* Advanced HTTP monitoring with configurable methods, expected status codes, response body checks, redirect handling, and TLS verification
* DNS monitoring for A, AAAA, CNAME, MX, and TXT records
* TLS certificate validation and expiration monitoring
* ICMP availability and response time monitoring
* Automatic checker selection based on monitor type
* Serialized monitor state updates to prevent concurrent check races
* Automatic incident detection and recovery
* Maintenance windows
* Uptime statistics with 24h, 7d, 30d, and custom time ranges

### Notifications

* Webhook, Telegram, and email notification destinations
* Reliable notification delivery with retries and worker leases
* HMAC-SHA256 signed webhook requests
* SMTP email delivery with TLS and STARTTLS support

### Authentication and Organizations

* User registration and JWT authentication
* Rotating refresh-token sessions with HttpOnly cookies
* Organizations and organization-scoped resources
* Organization member and role management
* Role-based access control with owner, admin, member, and viewer roles
* API keys for CI, scripts, and service integrations
* HMAC-SHA256 protected API key storage
* Organization isolation across monitors, incidents, maintenance windows, status pages, statistics, notification destinations, and API keys
* Configurable CORS support for browser clients

### Status Pages

* Public status pages
* Organization-scoped status page management

### Web UI

The management interface is a responsive Vue 3 single-page application located in `frontend/`.

Implemented features:

* Dashboard with monitor status overview, open incidents, and recent incidents
* User registration, login, logout, and session restoration
* Automatic access-token refresh
* Protected routes and role-aware interface
* Organization creation and switching
* Organization member and role management
* Monitor creation, editing, deletion, and configuration
* HTTP, TCP, DNS, TLS, and ICMP monitoring interfaces
* Check history and monitor statistics
* Incident list, filtering, and details
* Maintenance window management
* Webhook, Telegram, and email notification management
* Public status pages and their administration
* API key creation, listing, and revocation
* Responsive layouts and mobile navigation
* Reusable form controls and consistent styling
* Lazy-loaded routes and page-specific styles

The frontend uses Vue 3, TypeScript, Vite, Vue Router, Pinia, Axios, and SCSS.

The production frontend runs in an Nginx container built from `frontend/Dockerfile`. Nginx serves the Vue application and proxies `/backend/` to the FastAPI service.


### Platform

* PostgreSQL persistence with Alembic migrations
* Docker Compose deployment of the backend, frontend, PostgreSQL, and optional Caddy HTTPS reverse proxy
* Interactive `install.sh` for initial configuration, database migrations, and creation of the first organization owner
* Unit, API, and PostgreSQL integration tests

## Repository Structure

```text
uptime-platform/
├── src/
│   └── uptime_platform/        # FastAPI backend and bootstrap CLI
├── migrations/
├── tests/
├── frontend/                   # Vue 3 SPA
│   ├── src/
│   ├── public/
│   ├── Dockerfile              # Frontend image
│   ├── nginx.conf              # SPA and API reverse proxy
│   ├── package.json
│   ├── package-lock.json
│   └── vite.config.ts
├── install.sh                  # Interactive installer
├── Dockerfile                  # Backend image
├── compose.yml
├── pyproject.toml
├── uv.lock
├── Makefile
└── .env.example
```

The backend and frontend are maintained in the same repository but use separate dependency and build systems.

## Quick Start

The interactive installer runs **from a checkout on a Linux host**. Prerequisites: Bash, Git, a running Docker daemon, Docker Compose v2, `curl`, `openssl`, Python 3, and `getent`. The installer does **not** install Docker or download application images: it builds the backend and frontend locally.

After the v1.0.0 tag is published, install the release:

```bash
git clone --branch v1.0.0 --depth 1 https://github.com/SashaSolovey1/uptime-platform.git
cd uptime-platform
sudo bash install.sh
```

The installer asks for an address, administrator email/password, and organization name; generates secrets in `.env`; initializes PostgreSQL; runs Alembic migrations; creates the first organization owner; starts services; and checks the frontend and API.

| Address entered | Access URL | Notes |
| --- | --- | --- |
| `localhost` or `127.0.0.1` | `http://localhost:8080` | Local-only mode; Caddy is not started. |
| Domain, e.g. `uptime.example.com` | `https://uptime.example.com` | Configure DNS and make ports 80/443 reachable for Caddy certificate issuance. |
| IPv4 address (or empty input to detect public IPv4) | `https://<your-ip>` | Uses Caddy's **private CA**. Remote browsers do not automatically trust its certificate; importing that CA is necessary before entering credentials. Public-IP detection does not guarantee inbound reachability through NAT, CGNAT, or a firewall. |

The installer preserves its generated `.env`, secrets, and Docker volumes on reruns. It does not replace an existing, manually managed `.env`. **Do not use `make docker-reset` on installations with data you want to keep.**

For an installed instance, use its selected address plus `/backend/health` to check the API. Direct API documentation is available locally at `http://127.0.0.1:8000/docs` when the API host port remains mapped as in `compose.yml`.

### Deployment notes

The web UI is served by Nginx. Browser API requests to `/backend/api/v1/...` are forwarded to FastAPI. The backend and frontend use **separate images**, with PostgreSQL and optional Caddy managed by the same Compose file.

The initial organization owner is **not** a global superuser. The regular registration endpoint remains available unless you disable it separately. The provided installer is an interactive source-based installer, not a Docker-less one-command VPS provisioner. Before public deployment, validate monitoring target restrictions, registration policy, TLS trust, backups, and your firewall configuration. The IP/private-CA option does not provide a publicly trusted certificate by default.

### Frontend Development

The Vue frontend is located in:

```text
frontend/
```

Install frontend dependencies:

```bash
cd frontend
npm ci
```

Create the frontend environment file:

```bash
cp .env.example .env
```

The development API URL should point to the FastAPI backend:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Start the Vite development server:

```bash
npm run dev
```

The frontend is then available at:

```text
http://localhost:5173
```

During development, run the FastAPI backend and Vite frontend separately.

## Authentication

### User Authentication

Register a user:

```http
POST /api/v1/auth/register
```

Log in:

```http
POST /api/v1/auth/login
```

A successful login returns a short-lived JWT access token and sets a rotating refresh token in an HttpOnly cookie.

The access token is used for normal authenticated API requests:

```http
Authorization: Bearer <access-token>
```

The Vue frontend keeps the access token in application memory rather than persistent browser storage.

Organization-scoped requests also use:

```http
X-Organization-ID: <organization-uuid>
```

The organizations available to the authenticated user can be retrieved through:

```http
GET /api/v1/organizations
```

### Refresh Tokens

JWT access tokens are intentionally short-lived.

When an access token expires, the client can obtain a new access token through:

```http
POST /api/v1/auth/refresh
```

The refresh token is stored in an HttpOnly cookie and is rotated on every successful refresh.

Each successful refresh:

1. Revokes the previous refresh session.
2. Creates a new refresh session.
3. Returns a new JWT access token.
4. Sets a new refresh-token cookie.

The refresh token itself is never stored in plaintext in PostgreSQL. Only an HMAC-SHA256 digest is stored.

The Vue frontend uses the refresh session to restore authentication after a page reload and automatically retry authenticated API requests when an access token expires.

Logout revokes the current refresh session:

```http
POST /api/v1/auth/logout
```

### Roles

Organization memberships use four roles:

| Role     | Access                                                |
| -------- | ----------------------------------------------------- |
| `viewer` | Read organization resources                           |
| `member` | Read resources and perform operational changes        |
| `admin`  | Member access plus administrative resource management |
| `owner`  | Full organization access                              |

Resource access is scoped to the selected organization.

Admins can manage members with lower roles, while owners can manage all organization roles.

The last owner of an organization cannot be removed or demoted.

### Organization Members

Organization administrators can list, add, update, and remove organization members.

Members are added by registered user email.

Organization membership controls which resources a user can access and which actions they can perform.

### API Keys

Admins and owners can create API keys for CI systems, scripts, automation, and service integrations.

The complete API key is returned only once when it is created.

Only an HMAC-SHA256 digest and a short visible prefix are stored by the platform.

API key requests use the same authorization header:

```http
Authorization: Bearer upt_<api-key>
```

API keys are bound to a single organization and currently receive member-level operational access.

API keys can be listed and revoked through the API.

## API

The platform exposes a REST API for managing:

* authentication
* organizations
* organization members
* monitors
* checks
* incidents
* maintenance windows
* monitor statistics
* notification destinations
* status pages
* API keys

HTTP, TCP, DNS, TLS, and ICMP monitors use different configuration structures depending on the selected monitor type.

The current request and response schemas, available endpoints, validation rules, and example payloads are available in the interactive Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

## Monitor Statistics

Monitor statistics are available for:

* 24 hours
* 7 days
* 30 days
* custom time ranges

Statistics include:

* uptime percentage
* successful check count
* failed check count
* total check count
* average response time

## Notification Destinations

Notifications are sent when incidents are opened or resolved.

Supported notification destinations:

* Webhook
* Telegram
* Email

Webhook requests support HMAC-SHA256 signatures.

Email notifications are delivered through SMTP with the following security modes:

* `none`
* `starttls`
* `tls`

Sensitive destination credentials such as webhook secrets, Telegram bot tokens, and SMTP passwords are not returned by the API.

## CORS

CORS is configurable through the environment:

```dotenv
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Credentials are enabled so browser clients can use the HttpOnly refresh-token cookie.

For production deployments, configure the actual frontend origins instead of development localhost addresses.

## Configuration

Important authentication-related environment variables:

```dotenv
JWT_SECRET=<secure-random-secret>
JWT_ACCESS_TOKEN_TTL_MINUTES=60

API_KEY_HASH_SECRET=<secure-random-secret>

REFRESH_TOKEN_HASH_SECRET=<secure-random-secret>
REFRESH_TOKEN_TTL_DAYS=30

REFRESH_COOKIE_NAME=refresh_token
REFRESH_COOKIE_SECURE=false
REFRESH_COOKIE_SAMESITE=lax

CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

For HTTPS production deployments:

```dotenv
REFRESH_COOKIE_SECURE=true
```

Changing `API_KEY_HASH_SECRET` invalidates existing API keys.

Changing `REFRESH_TOKEN_HASH_SECRET` invalidates existing refresh sessions.

## Development

### Backend

Install backend dependencies:

```bash
uv sync
```

Start the development database:

```bash
make dev-up
```

Apply migrations:

```bash
make migrate
```

Start the API:

```bash
uv run fastapi dev src/uptime_platform/main.py
```

Run the scheduler and notification worker in separate terminals:

```bash
make scheduler
make notification-worker
```

Run all backend checks:

```bash
make format
make lint
make test-fresh
```

### Frontend

Install dependencies:

```bash
cd frontend
npm ci
```

Start the development server:

```bash
npm run dev
```

The frontend uses:

* Vue 3
* TypeScript
* Vite
* Vue Router
* Pinia
* Axios
* ESLint
* Prettier

In development, Vite runs separately and communicates with the FastAPI API over HTTP. In the Docker deployment, Nginx serves the compiled SPA and proxies the API.

### Docker

For a new self-hosted installation, use `sudo bash install.sh` from the project checkout. The installer builds both images locally and starts the selected deployment mode.

Show service status and follow logs:

```bash
docker compose --profile public ps -a
docker compose --profile public logs --tail=100 api frontend caddy
```

For localhost mode, Caddy is not started; `docker compose ps -a` and `docker compose logs api frontend` are sufficient. Some systems require `sudo docker compose`.

Stop the application while preserving volumes:

```bash
docker compose --profile public down --remove-orphans
```

> **Destructive:** `make docker-reset` removes Docker volumes, including local PostgreSQL data. Do not use it as an update or recovery command.

The backend and frontend Docker Hub images are published separately. Image-only deployments require configuring the image names in Compose and providing a valid `.env`; see [Docker images](#docker-images). The interactive installer currently builds from source regardless of whether images have been published.

## Tech Stack

### Backend

Python 3.13 · FastAPI · SQLAlchemy · PostgreSQL · asyncpg · Alembic · Pydantic · PyJWT · pwdlib/Argon2 · asyncio · httpx2 · dnspython · icmplib · aiosmtplib · Docker Compose · pytest · Ruff · uv

### Frontend

Vue 3 · TypeScript · Vite · Vue Router · Pinia · Axios · ESLint · Prettier

## Roadmap

### Web UI

- Cross-device responsive testing and accessibility improvements
- End-to-end frontend testing

### Platform

* Encrypted notification credentials
* Slack notification destination
* Scheduler claiming and multi-instance safety
* Check history retention and cleanup
* Prometheus metrics and Grafana dashboards
* CI/CD with automated tests and Docker image publishing
* Automated Docker provisioning and installation from prebuilt release images
* Production hardening, SSRF/monitor-target controls, and deployment documentation

## Docker images

Uptime Platform publishes two application images. The backend image is used by the API, scheduler, notification worker, and migration service; the frontend image serves Vue with Nginx. Both are needed for the full application (alongside PostgreSQL and optional Caddy).

| Component | Versioned image |
| --- | --- |
| Backend | `sashastudent/uptime-platform:1.0.0` |
| Frontend | `sashastudent/uptime-platform-frontend:1.0.0` |

```bash
docker pull sashastudent/uptime-platform:1.0.0
docker pull sashastudent/uptime-platform-frontend:1.0.0
```

The `latest` tag can also be published for each image. Prefer matching, explicit version tags when deploying or reproducing a release. Publishing an image does not install the complete application by itself: use the Compose configuration and a properly initialized database.

The included `install.sh` currently **builds images from source**; it does not automatically pull the published application images. To deploy the published images directly, ensure that `compose.yml` defines `frontend.image`, set `APP_IMAGE` and `FRONTEND_IMAGE` to matching versioned tags in `.env`, and run Compose without rebuilding. This is an alternative deployment workflow and is not yet automated by the installer.

## License

Licensed under the [MIT License](LICENSE).
