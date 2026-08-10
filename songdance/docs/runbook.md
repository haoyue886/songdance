# Production runbook

Use structured logs and hashed job identifiers. Never paste original filenames, audio,
full object keys, signed URLs, Redis contents or credentials into tickets.

## First response

1. Check API `/health`, Railway deploy status and recent API/Worker/Cleanup logs.
2. Check PostgreSQL, Redis and object storage provider status.
3. Lower `SONGDANCE_DAILY_JOB_LIMIT` to stop new work if failures can lose data or create
   unbounded cost. A positive value is required; use `1`, not `0`.
4. Preserve logs and the affected hashed job IDs before restarting services.

## API unavailable

- Migration failure: inspect the Alembic error and database connectivity. Do not enable
  `SONGDANCE_AUTO_CREATE_SCHEMA` in production.
- HTTP 403 `UNTRUSTED_PROXY`: verify requests enter only through Railway public ingress,
  then set `SONGDANCE_TRUSTED_PROXY_CIDRS` to the exact edge peer CIDR and keep
  `SONGDANCE_TRUSTED_PROXY_HOPS` at the actual proxy count. Never “fix” this with `/0`.
- Browser CORS failure: set `SONGDANCE_CORS_ORIGINS` to the exact HTTPS Vercel origin and
  redeploy API. Do not use `*`.
- HTTP 413: keep the 25 MB product limit; investigate clients rather than raising it.

## Queue backlog or stuck jobs

- Confirm the Worker is running one replica and listening on `SONGDANCE_QUEUE_NAME`.
- Check Redis connectivity and RQ failed registries. A job retries at most twice.
- If model memory exhaustion repeats, stop new submissions, restart the Worker, retain one
  replica and increase container memory before restoring capacity.
- Do not manually enqueue the same job ID while its active quota reservation exists.

## Model or artifact failures

- `NO_NOTES_DETECTED`: valid terminal result; ask for a clearer solo-piano clip.
- Model timeout/error: confirm FFmpeg and model runtime versions from the image, then retry
  only within the existing three-attempt ceiling.
- MusicXML or timeline failure: MIDI may remain downloadable; inspect the specific artifact
  status rather than marking the entire job successful.
- Any model or post-processing change requires rerunning the fixed 10-clip human quality
  gate. Automated synthesized-note scores do not replace that gate.

## Storage or deletion failures

- Confirm bucket credentials allow list multipart uploads, abort multipart uploads,
  read/write and delete for only the production bucket.
- Run `python -m app.jobs.cleanup` once in the Cleanup service and require
  `cleanup_cycle.failed=0` before restoring its Cron.
- A `DELETE_FAILED` job must remain visible as failed so cleanup can retry. Do not remove
  the database row while objects still exist.
- Keep the provider's one-day lifecycle as a backup, not as a replacement for application
  cleanup.

## Quota and cost protection

Initial ceilings are 3 jobs/IP/hour, 1 active job/client, 2 active jobs globally and 25
jobs/day. Review Railway CPU/memory, Redis usage, database size and bucket bytes daily for
the first week. Raise one limit at a time; a higher Worker replica count multiplies model
memory and compute cost.

If cost rises unexpectedly, set the daily limit to `1`, keep YouTube disabled, let current
jobs finish and inspect event counts before changing infrastructure.

## YouTube incidents

Keep `SONGDANCE_YOUTUBE_ENABLED=false` unless the operating region has been reviewed.
Platform rejection, private/login/region/paid/live restrictions and timeout must fall
back to local upload. Never add cookies, browser profiles, proxy bypasses or login tokens.

## Recovery verification

After any incident or rollback, require: `/health` 200, one anonymous upload, refresh
recovery, score and piano-roll rendering, three valid downloads, immediate delete, one
successful Cleanup cycle, and a clean browser console at desktop and 375 px widths.
