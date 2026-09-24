# Uptime Platform Helm chart

This chart deploys the production core of Uptime Platform:

- PostgreSQL with a PVC
- Alembic migration Job on install/upgrade
- FastAPI API
- scheduler
- notification worker
- Vue/nginx frontend
- internal Services
- OpenShift Route when the Route API is available
- optional Kubernetes Ingress
- generated/preserved application and PostgreSQL secrets

It intentionally does not deploy the local/test extras from `compose.yml` such as
Mailpit, Caddy, Prometheus, Grafana, or `postgres-test`.

## Project placement

Keep the chart in the repository at:

```text
deploy/helm/uptime-platform/
```

No Python or Vue source-code changes are required for the chart itself.

## OpenShift

```bash
helm upgrade --install uptime-platform ./deploy/helm/uptime-platform \
  -f ./deploy/helm/uptime-platform/values-openshift.yaml \
  --namespace uptime-platform \
  --create-namespace
```

If `route.host` is empty, OpenShift may generate a host for the Route.

## Kubernetes with Ingress

Edit `values-kubernetes.yaml` and set the real hostname, then:

```bash
helm upgrade --install uptime-platform ./deploy/helm/uptime-platform \
  -f ./deploy/helm/uptime-platform/values-kubernetes.yaml \
  --namespace uptime-platform \
  --create-namespace
```

## Secrets

By default, the chart generates these on first install and preserves them during
upgrades using Helm's `lookup` function:

- `POSTGRES_PASSWORD`
- `JWT_SECRET`
- `REFRESH_TOKEN_HASH_SECRET`
- `API_KEY_HASH_SECRET`
- `DATABASE_URL`

To provide an existing Secret instead:

```yaml
secrets:
  create: false
  existingSecret: uptime-platform-secrets
```

The existing Secret must contain:

```text
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
DATABASE_URL
JWT_SECRET
REFRESH_TOKEN_HASH_SECRET
API_KEY_HASH_SECRET
```

## Images

Defaults match the uploaded project version:

```text
sashastudent/uptime-platform:latest
sashastudent/uptime-platform-frontend:latest
```

Change `backend.image.tag` and `frontend.image.tag` for another release.

## Migrations

A managed Kubernetes Job runs once per Helm release revision:

```text
alembic upgrade head
```

API/scheduler/worker pods use an init container that waits until the database's
`alembic_version` matches the migration head embedded in the backend image. The Job
and workloads can therefore be created together, including when Helm is used with
`--wait`, while application processes do not start against an unmigrated database.

## OpenShift security

The workload security context is compatible with the usual OpenShift restricted
SCC model: non-root, no privilege escalation, all Linux capabilities dropped,
RuntimeDefault seccomp.

The source project currently calls `icmplib.async_ping(..., privileged=True)`.
`NET_RAW` is therefore relevant to ICMP checks. The chart leaves `NET_RAW` disabled
by default because restricted OpenShift SCCs commonly reject it. If the cluster
administrator permits it, set:

```yaml
securityContext:
  addNetRaw: true
```

HTTP/TCP/DNS/TLS checks do not require that capability.

## One release per namespace

The current frontend `nginx.conf` contains:

```nginx
proxy_pass http://api:8000/;
```

For that reason the chart intentionally creates the backend Service with the fixed
name `api`. Do not install multiple releases in the same namespace unless the
frontend configuration is made release-name aware.
