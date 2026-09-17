# Concurrent schedulers

Multiple scheduler processes can share PostgreSQL. Coordination uses two nullable
columns on `monitors`: `check_lease_token` and `check_lease_until`. A database check
constraint requires both columns to be set or cleared together. Lease fields are
internal and are not exposed in monitor API responses.

## Claim, execute, record

1. In a short transaction, select due, non-paused monitors without a live lease
   using `FOR UPDATE SKIP LOCKED`. Order by `next_check_at`, then monitor ID.
2. Assign a fresh UUID token per claim. Set expiration from the PostgreSQL clock
   to `timeout_seconds + lease_grace_seconds` and commit before network I/O.
3. Run the probe outside any database transaction with an overall asyncio timeout
   of `timeout_seconds`. Total timeout becomes a failed check, like a probe failure.
4. Lock the monitor row and check its token and expiration **after** obtaining the
   lock, using PostgreSQL's current clock. Discard results from expired or replaced
   owners before writing checks, state, incidents, or outbox events.
5. Record the result, update `next_check_at`, and clear the lease in one transaction.
   Maintenance still stores the check and advances the schedule without updating
   state or creating an incident; that branch also clears the lease atomically.

Normal monitor updates do not write lease columns. Release operations match both
monitor ID and token, so an old process cannot clear a replacement's lease.

## Limits and shutdown

The existing defaults remain: poll interval 1 second, batch size 100, concurrency
20. A batch is now processed in waves of at most `concurrency` claims, so leases
are not consumed by a semaphore backlog. A monitor is attempted at most once per
`run_once`, including when its checker raises. Overlapping `run_once` calls on one
scheduler instance are serialized. The returned count is attempts, not successes.

`lease_grace_seconds` defaults to 30 and `cleanup_timeout_seconds` to 5. These are
constructor options, not environment variables. Claim and recording transactions
are bounded by the grace timeout. No heartbeat is required for these bounded checks.

Unexpected checker/recording errors are logged; a failed recording transaction
rolls back all of its writes. Ordinary database polling errors are logged and the
next polling iteration retries. Task cancellation propagates, cancels and drains
the active checker tasks, then attempts bounded token-matched cleanup. SIGTERM
cancels the scheduler through this same path; the asyncio runner handles SIGINT.

If cleanup fails, or the process dies before cleanup (including SIGKILL), another
scheduler can claim the monitor once the lease expires. Uncommitted claims roll
back. No reaper process or lease renewal service is needed.

## Guarantee boundaries

Only the current unexpired claimant can begin a scheduled result transaction.
The row lock protects that transaction from another claimant until commit/rollback.
An expired process cannot persist a late result or release a newer claim.

This is not exactly-once network I/O: a stopped/unresponsive process or an already
sent request can overlap a replacement after expiry. Timeouts require cooperative
async cancellation. The database token fences persisted effects, not the remote
target. Manual API checks intentionally retain their existing semantics and may
overlap a scheduled probe; their state writes still use the monitor row lock.

## Upgrade and rollback

Migration `6a82b4d91f03` follows `18e7e0bc5755` and adds the nullable columns and
constraint without changing existing monitor state or scheduling timestamps.

Stop **all old scheduler instances**, apply the migration, and start schedulers
running the new code. Old schedulers do not honor leases, so running old and new
versions together does not provide the guarantee. Do not deploy the new code
against the old schema. For downgrade, stop the new schedulers before removing
the lease columns and return to a single old scheduler.

## Tests

`tests/integration/scheduler/test_scheduler_leases.py` uses independent PostgreSQL
sessions, controlled checker events, and a disposable organization per test. It
checks skip-locked claims, two concurrent schedulers, abandoned/expired claims,
late owners, rollback, cancellation, checker/persistence failures, maintenance,
and unchanged manual-check behavior. Expiration is advanced in the test database
instead of sleeping for a production lease duration.

Run using the project's disposable test database and migrations (`make
test-integration`), never against production. Unit coverage includes total probe
timeouts, bounded claim waves, retrying polling errors, and SIGTERM cancellation.
