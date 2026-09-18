# Installation and updates

Both scripts manage only `/opt/uptime-platform`. They do not use a checkout's
`.env` or accept a different installation directory.

## Install

```bash
curl -fL https://raw.githubusercontent.com/nightingale-develop/uptime-platform/main/install.sh -o install.sh
sudo bash install.sh
```

Enter the application address, owner email, organization and password. Configuration
and generated secrets are saved under `/opt/uptime-platform`. Running the installer
again updates an existing managed installation without creating another owner.

## Clean reinstall

```bash
sudo bash install.sh --clean
```

After entering the new installation details, type `CONFIRM` at the `(CONFIRM)` prompt.
The installer downloads and checks release files and images before deleting:

- Containers, volumes and networks labelled as Docker project `uptime-platform`.
- `/opt/uptime-platform`, including its configuration and backups.

**This erases the database, monitoring history and certificates.** Copy anything
needed to another directory or machine first. Other Docker projects and the source
checkout are preserved. A previous checkout deployment using the same project name
is removed too. New secrets and an empty database are created.

## Update without deleting data

```bash
curl -fL https://raw.githubusercontent.com/nightingale-develop/uptime-platform/main/update.sh -o update.sh
sudo bash update.sh --version 1.2.0
```

Replace the version with the desired published release. Add `--observability` to
start Prometheus and Grafana.

The updater checks database access before stopping application processes, saves
configuration and a PostgreSQL dump under `/opt/uptime-platform/backups/`, applies
migrations and restarts services. It preserves secrets and data volumes. PostgreSQL
must be running; stop schedulers and workers on other hosts separately.

If a migration fails, inspect the error before restarting writers. There is no
automatic database rollback. Changing `.env` does not reset PostgreSQL's stored
password. Use `--clean` only when you intend to discard the old installation.

For building from source, see [local development](development.md).
