# Deployment updates

For an installer-managed deployment, prefer [update.sh](../update.sh) and the
[README instructions](../README.md#updating-an-installsh-deployment). It does not
need source files, Git, Python packages or npm on the server.

Download the updater for the release you want to install from its versioned Git
URL. The updater fetches only the deployment manifest, updater and monitoring
configuration. It never downloads a source archive or overwrites `.env` secrets.
It changes only the two application image selections in `.env`.

Managed Compose and monitoring configuration are replaced by the release defaults;
local customizations are backed up, but not merged. Files without the installer's
Compose ownership marker are not automatically adopted. Simultaneous updater
runs are rejected with a local lock. Old scheduler and worker processes must be
stopped on every host using the database before a schema-changing upgrade.

## Manual update for customized deployments

1. Obtain the selected release's Compose and monitoring files and merge relevant
   changes into your custom configuration. Preserve your project name, database
   volume and secrets. Inspect that release's migration notes.
2. Back up `.env`, Compose, monitoring configuration and Caddy configuration. Protect
   database backups and copy them off the server. Back up certificate volumes
   separately when needed.
3. Select matching published backend/frontend tags in `.env`, then pull all
   application images. A failed pull must not stop the running application.
4. Stop frontend, API and all scheduler/worker replicas. Take a final PostgreSQL
   dump while writers are stopped.
5. Run migrations using the new image. Continue only if they succeed.
6. Recreate application services, check API health and worker logs, then check all
   three Prometheus targets if monitoring is enabled.

Commands below assume you are in your deployment directory and have already
selected the release images and protected your configuration backup:

```bash
sudo docker compose pull api frontend scheduler notification-worker migrate
sudo docker compose stop frontend api scheduler notification-worker
umask 077
backup_file="$(mktemp "$HOME/uptime-before-upgrade.XXXXXXXX.sql")"
sudo docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$backup_file"
sudo docker compose run --rm --no-deps migrate
sudo docker compose up -d --no-deps --wait api scheduler notification-worker
sudo docker compose up -d --no-deps --wait frontend
sudo docker compose ps -a
```

Use a fresh private backup file instead of overwriting an earlier backup. Run each
command only after the previous one succeeds. If monitoring files changed,
recreate Prometheus/Grafana to reload their bind mounts. Preserve existing Caddy
and data volumes. Never use `down -v` as an upgrade command.

If migration fails, leave writers stopped and inspect logs. Neither the updater
nor this procedure automatically reverses database migrations. Restore a compatible
backup before returning to an older image when the schemas are incompatible.

The updater refreshes files at the same bind-mount paths, so it recreates monitoring
containers after replacing their configuration. It does not automatically prune
backups, upgrade PostgreSQL to a new major version, or update other hosts.
