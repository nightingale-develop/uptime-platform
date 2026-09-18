# Installation and updates

The scripts manage the installation in `/opt/uptime-platform`.
For running from source, see [local development](development.md).

## Install

```bash
curl -fL https://raw.githubusercontent.com/nightingale-develop/uptime-platform/main/install.sh -o install.sh
sudo bash install.sh
```

Enter the application address, owner email, organization and password.
Configuration is saved in `/opt/uptime-platform/.env`.

## Update

```bash
curl -fL https://raw.githubusercontent.com/nightingale-develop/uptime-platform/main/update.sh -o update.sh
sudo bash update.sh --version 1.2.1
```

Replace `1.2.1` with the desired published release. Add `--observability` to enable
Prometheus and Grafana; existing monitoring stays enabled.

The updater backs up configuration and the database to
`/opt/uptime-platform/backups/`, applies migrations and restarts the application.
Configuration and data volumes are preserved. PostgreSQL must be running.
If schedulers or workers run on other hosts, stop them before updating.

History is subject to [automatic cleanup](retention.md). Check the retention
periods before updating if you need to keep older records.

If an update fails after stopping the application, fix the reported error before
restarting it. There is no automatic database rollback.

## Clean reinstall

```bash
sudo bash install.sh --clean
```

**This deletes the database, monitoring history, certificates and everything in
`/opt/uptime-platform`, including backups.** Save anything needed elsewhere first.
Deployments using the Docker project name `uptime-platform` are also removed.
Enter the new installation details and type `CONFIRM` when prompted.
