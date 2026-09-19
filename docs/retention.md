# History cleanup

The scheduler automatically removes old history:

| History | Default retention |
| --- | --- |
| Check results | 30 days after the check |
| Resolved incidents | 90 days after resolution |
| Completed notifications | 30 days after processing |

Open incidents, pending notifications and deliveries still being processed are
kept. Monitors and their current status are unchanged. Deleted history disappears
from charts and statistics.

Statistics use the checks that remain, not the deleted history. When a requested
period exceeds the retention window or the available history, the dashboard
shows an incomplete-history notice and the dates of the checks used. Increasing
retention or disabling cleanup does not restore deleted records.

The statistics API returns `is_partial`, `history_available_from` (the oldest
remaining check), and `first_check_at` / `last_check_at` for the requested period.
No checks means null check dates and uptime, with `is_partial=true`. The flag is
conservative while cleanup catches up; it does not detect every monitoring gap
inside the available history. Custom ranges up to 90 days remain supported.

## Settings

To change the defaults, edit `/opt/uptime-platform/.env`:

```dotenv
RETENTION_ENABLED=true
RETENTION_CHECKS_DAYS=30
RETENTION_INCIDENTS_DAYS=90
RETENTION_NOTIFICATIONS_DAYS=30
RETENTION_INTERVAL_SECONDS=60
RETENTION_BATCH_SIZE=1000
```

Set `RETENTION_ENABLED=false` to disable cleanup. Days, interval and batch size
must be positive integers. Apply changes to both cleanup and statistics:

```bash
cd /opt/uptime-platform
sudo docker compose up -d --no-deps --force-recreate api scheduler
```

Cleanup runs at scheduler startup, then pauses between passes (60 seconds by
default). Each pass removes up to 1000 rows per table by default, so a large
backlog takes several passes.

## Verify on an installed application

Check that the scheduler is running and inspect its logs:

```bash
cd /opt/uptime-platform
sudo docker compose ps scheduler
sudo docker compose logs --since=10m scheduler
```

A successful deletion produces a line such as:

```text
retention deleted {'checks': 1000, 'incidents': 2, 'deliveries': 5, 'events': 5}
```

The numbers are rows deleted in that pass. `retention cleanup failed` indicates
an error; the scheduler retries at the next interval. No deletion message is
written when there is nothing to remove.

To check for remaining expired check results, run this read-only query. Replace
`30 days` if you changed `RETENTION_CHECKS_DAYS`:

```bash
sudo docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
SELECT count(*) AS expired_checks
FROM checks
WHERE checked_at < now() - interval '30 days';
SQL
```

Repeat after a few cleanup intervals. The backlog should decrease toward zero
if cleanup keeps up with newly expiring records. Zero means there are no expired
checks; by itself it does not prove cleanup ran. If the count stays high, check
the logs and retention settings. Database files may not shrink immediately:
PostgreSQL reuses the freed space.

## Verify without waiting for records to age

In a [local development checkout](development.md), run the existing retention
tests against the disposable test database on port 5433:

```bash
make test-migrate
uv run --env-file .env.test pytest tests/unit/retention tests/integration/retention tests/unit/scheduler/test_main.py -v
```

Use the test database configured in `.env.test`, never the installed database.
The tests create expired and recent records, verify deletion and preservation,
and check batch limits, concurrent cleanup and rollback after failures.
All tests should pass. This checks cleanup without changing production history
or shortening its retention period.
