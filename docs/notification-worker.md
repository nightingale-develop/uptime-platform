# Notification worker coordination

The worker uses PostgreSQL delivery leases to coordinate multiple processes. No broker or lease-renewal service is required.

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
