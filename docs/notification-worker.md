# Notification worker coordination

The worker uses PostgreSQL delivery leases to coordinate multiple processes. No broker or lease-renewal service is required.

## Incident messages

Telegram and Slack messages use readable text; email includes an HTML body and a plain-text alternative.
All show the monitor name, type and sanitized target before the technical UUIDs.
An opening message includes the check's known failure reason. A recovery message
includes the incident start, restoration time and elapsed duration, in UTC.
Thresholds still determine when an incident opens and resolves; this duration is
the recorded incident duration, not the time since the first failed probe.

Set `PUBLIC_APP_URL=https://uptime.example.com` in the deployment `.env` to add a
link to `/monitors/{monitor_id}`. Use the browser-facing HTTP(S) address, without
credentials, query parameters or fragments. Localhost, private IPs and internal
hostnames are rejected. An empty value omits the link. New installations fill it
for public addresses; existing installations receive an empty default on update
and need an explicit value. Apply configuration through the normal deployment
update procedure. Links require sign-in and access to the monitor's organization;
deleted monitors remain described in the notification but no longer open in the UI.

The event stores its monitor/check snapshot in the same transaction as the incident.
Renaming or deleting the monitor before delivery cannot remove that snapshot.
When an address changes during a probe, the message identifies the address that was
actually checked. Older queued events remain deliverable, with unavailable fields
shown explicitly rather than reconstructed from current monitor data.

Targets omit URL credentials, **all** query parameters and fragments. Recognized
credential paths (including Telegram bot tokens and Slack/webhook paths) are masked.
Monitor names are escaped for HTML; raw exception text, response bodies and full
monitor/destination configuration are not copied into messages. Known exception
types provide safe reasons such as timeout, DNS, TLS or connection failure;
unclassified failures are reported as reason unavailable. Avoid placing arbitrary
credentials in monitor names or custom URL paths: an opaque secret has no reliable
generic identifier. The original monitoring URL is unchanged.

Webhooks retain `id`, `type`, `created_at` and `payload`, plus the existing signing
and event-ID headers. New payloads include `monitor_id`, `incident_id`, `monitor_name`,
`monitor_type`, `target`, `reason`, `status_code`, `started_at`, `resolved_at`,
`duration_seconds` and `monitor_url`. Timestamps use ISO 8601; missing values are
JSON `null`, and duration is a number of seconds. Legacy UUID-only payloads remain
supported. These additional JSON fields need no database migration.

## Slack

In your Slack app, enable **Incoming Webhooks**, select **Add New Webhook to Workspace**
and authorize the destination channel ([Slack setup guide](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/)).
In Uptime Platform, open **Notifications**, select **Slack** and paste the incoming
webhook URL. HTTPS URLs on `hooks.slack.com` and `hooks.slack-gov.com` are supported.
The Slack webhook determines the channel; no separate bot token or channel ID is needed.

Treat the entire webhook URL as a password. It is hidden in API responses and the
destination list. When editing, leave the field empty to retain it, or paste a new
URL to rotate it. It is stored with the destination credentials in PostgreSQL.

Slack receives the same incident snapshot as the other channels, with plain-text
blocks and a **View monitor** button when `PUBLIC_APP_URL` is configured. User text
cannot introduce Slack mentions or formatting; link previews are disabled. Failed
requests, including rate limits, use the existing worker retry policy. Retries can
produce duplicate messages if Slack accepted a request before a timeout or worker crash.

Apply migration `b8d4e2f60173` with the normal update procedure before using Slack.
Remove Slack destinations before downgrading this migration; downgrade refuses to
discard their configuration automatically.

## Ownership and transactions

Each delivery has an existing `locked_until` timestamp and a new `lease_token` UUID. A claim selects eligible rows with `FOR UPDATE SKIP LOCKED`, assigns a fresh token and expiry using PostgreSQL's clock, and commits before any network request. Another worker skips locked rows and cannot claim an unexpired lease.

A cycle still processes at most `batch_size` deliveries (100 by default), but claims only one executable wave at a time, up to `concurrency` (10 by default). It finishes and cleans that wave before claiming the next. An asyncio lock also serializes overlapping `run_once()` calls on the same worker instance. Already-attempted IDs are excluded for the remainder of that cycle, preventing immediate loops after unexpected failures.

Before sending, the worker checks the token and remaining lease time in PostgreSQL. It subtracts elapsed local monotonic time and reserves a database-write budget. An expired or replaced claim does not start a send.

Recording locks the delivery row and then checks its token, expiry using the current database clock, and unprocessed state. The expiry check happens after obtaining the lock, so time spent waiting for a concurrent transaction cannot make an expired claim valid. Retry/success fields and clearing both lease fields commit together. A stale write returns no result and changes nothing. Cleanup matches the token and cannot clear a newer worker's lease.

The migration adds the nullable token without discarding existing locks or pending work. Its constraint permits legacy timestamp-only leases, which expire naturally; every new claim has a token. Do not run old workers concurrently with the upgraded code: they can still write without checking tokens.

## Timeouts, errors and shutdown

- `notification_timeout_seconds` bounds the entire send operation with `asyncio.timeout`, in addition to the channel's individual network timeouts. A send timeout schedules a normal retry, increments attempts, and uses the existing exponential backoff and maximum-attempt policy.
- Database operations have a separate `database_timeout_seconds` budget (5 seconds by default). Cleanup has a total `cleanup_timeout_seconds` budget (5 seconds by default).
- The configured lease (60 seconds by default) is a minimum. The actual lease is at least the send timeout plus three database budgets and one second of margin. Pre-send checking further reduces the send budget when necessary. No application-host wall clock is used to determine lease ownership.
- `TaskGroup` waits for all sending tasks to finish or cancel before the `finally` block releases their claims. SIGTERM cancels the running worker once; repeated SIGTERM does not interrupt cleanup. Ctrl+C also unwinds cleanup.
- SIGKILL cannot run cleanup. If the database is unavailable during cleanup, leases also remain until expiry, allowing another worker to recover the work.
- Cancellation is cooperative: a blocked event loop or code that suppresses cancellation cannot be stopped by an asyncio timeout. Token checks still fence database writes; leases alone cannot fence an external recipient.

`uptime_notification_worker_last_success_timestamp_seconds` advances after a complete successful cycle, including idle cycles and correctly persisted retries. It stays unchanged on internal processing/persistence/cleanup errors or cancellation. A zero value means no successful cycle since startup. The dashboard and `UptimeNotificationWorkerStalled` alert show this separately from exporter availability.

## Duplicate delivery and idempotency

A crash after an external recipient accepts a notification but before PostgreSQL records success can cause a later retry. A timeout can also leave the external outcome unknown. These changes prevent stale database writes, not all duplicate external effects.

Webhooks already carry a stable `X-Uptime-Event-ID` header and the same ID in the payload. It remains the same across retries and worker replacements. A receiving application should authenticate the webhook, atomically deduplicate by event ID within the appropriate destination/consumer scope, and return success for an already handled event. No exactly-once guarantee is made for webhook, Telegram or email delivery.

## Upgrade

Back up PostgreSQL and deployment configuration. Stop all old notification workers sharing the database before applying migration `92c7e8a31d40`, including replicas outside the local Compose project. For a complete backend upgrade, stop API and scheduler processes as well, apply `alembic upgrade head` using the new image, and recreate services with that image. See the [deployment update procedure](updating.md).

Use matching backend/frontend `1.2.0` images for this change; `1.1.0` images do not include it. Rolling back across schema changes requires a planned application/database rollback; changing only the image tag is not a general rollback strategy.

## Verification

PostgreSQL integration tests cover simultaneous claims, two workers with bounded capacity, expiry recovery, stale writes/releases, expiry while waiting for a row lock, an old send finishing after replacement, pre-send expiry checks, timeouts with persisted backoff, cancellation and rollback after persistence failure. Unit tests cover cycle bookkeeping, cleanup ordering, SIGTERM and validation. Webhook tests verify stable event IDs across retry attempts.

The Python control-flow patterns follow [asyncio task and cancellation documentation](https://docs.python.org/3/library/asyncio-task.html); atomic selection uses [PostgreSQL row locking](https://www.postgresql.org/docs/current/sql-select.html).
