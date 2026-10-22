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

For migration-010 managed tasks, verify the private Dispatcher is logging `dispatch_cycle`.
`dispatch_retry` means the accepted task is waiting for queue recovery, not a reason to
upload again with a new key. After restoring Redis/storage, run
`python -m app.jobs.dispatch` once or let `--loop` recover it. `DISPATCH_TIMEOUT`,
`WORKER_LOST`, or `UPLOAD_INCOMPLETE` are fenced terminal outcomes; the original usage
period receives the release exactly once. An incomplete source requires a fresh upload.
Never remove `job_submissions` tombstones during media cleanup or force-enqueue an old
attempt; an explicit retry creates a new attempt and reservation. If restoring after
complete Redis loss, first pause new admissions and reconcile runtime quota counters.

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

These hourly/daily counters count admitted attempts, including rejected media and failed
queue/storage submissions. Cancellation releases the active slot but never refunds these
safety counters. Free/Pro/guest business reservations still release on failure through
their own ledgers. Honor `Retry-After`; do not clear Redis counters to retry invalid media.

Uploaded-file probing/clip extraction run off the API event loop, and Worker normalization
uses the same bounded media subprocess wrapper. On Linux each process has a 512 MiB
address-space limit and an 8 MiB stack
limit; CPU limits are 10 seconds for ffprobe and 60 seconds for ffmpeg, with wall limits
of 15/120 seconds. Output files are capped at 512 KiB/16 MiB, captured stdout at 64 KiB,
open files at 64, and core dumps are disabled. Input formats are restricted to WAV/MP3/MOV
for uploads; Worker normalization accepts WAV only. Protocols are restricted to local files,
decoder/encoder threads to one, and Worker normalization also uses one filter thread.
Child environments exclude application credentials.

On Linux, media children also require Landlock ABI 4 or newer. They can read the packaged
runtime tree and the exact input file, write only the exact clip output file, and cannot
create network sockets. A seccomp filter enforces the socket restriction for TCP and UDP.
It also denies io_uring, importing other processes' descriptors, ptrace, and file
permission/owner/timestamp/xattr changes; these are outside Landlock's file-content rules.
Ioctl is limited to the FIOCLEX/FIONCLEX descriptor flags; inode/device operations are denied.
The output file is created exclusively before sandboxing.
If Landlock setup fails, media processing fails closed; do not disable it to recover uploads.

Repeated `AUDIO_DECODE_FAILED`/`CLIP_EXTRACTION_FAILED`/`AUDIO_PREPROCESS_FAILED` can mean malformed input or a
resource limit. Check the exact image and normal-file regression before changing limits.
Worker wall-clock expiration remains `AUDIO_PREPROCESS_TIMEOUT`. Normalization writes to
a private temporary output and replaces the final path only on success; failed or empty
output cannot overwrite a previous result, and its private directory is removed.
Landlock and seccomp limit filesystem and socket access but do not isolate CPU/memory across
processes or remove FFmpeg parser vulnerabilities. The process still shares the API UID,
limits apply per process, and macOS does not enforce Linux resource/Landlock limits.
Same-UID signals and process control are still available; malicious descendants may also
create a new session outside the original process group. Aggregate container capacity
and parent-process containment still require separate validation. Keep credentials and
business data outside the read-only runtime library tree.
These controls apply to uploaded-file validation, clip extraction and Worker normalization
through run_media. yt-dlp still uses a separate subprocess path and is not covered by this
policy. Keep YouTube disabled; that path and total process capacity still need acceptance.

If cost rises unexpectedly, set the daily limit to `1`, keep YouTube disabled, let current
jobs finish and inspect event counts before changing infrastructure.

## YouTube incidents

Keep `SONGDANCE_YOUTUBE_ENABLED=false` unless the operating region has been reviewed.
Platform rejection, private/login/region/paid/live restrictions and timeout must fall
back to local upload. Never add cookies, browser profiles, proxy bypasses or login tokens.

## Recovery verification

Before restoring a database/object snapshot, close public write ingress and stop Workers,
Dispatcher, billing/deletion processors and email jobs. Restore into an isolated new
database and private bucket; verify backup hashes and compare table rows, tombstones,
usage/paid history, object bytes and metadata before starting writers. A database-only
restore is insufficient when media lives in object storage. Do not reset expiry dates or
recreate deleted accounts from an old snapshot; reconcile deletions and provider facts
that occurred after the backup before reopening access.

Use pg_dump custom format and pg_restore with --exit-on-error --single-transaction for
the rehearsed logical restore. Roles, grants, extensions, encrypted/remote backups and
provider PITR need their own production procedure. The local
[restore rehearsal](reviews/2026-10-22-backup-restore-rehearsal.md) verified a synthetic
snapshot and one durable job with fresh Redis; it does not approve production RTO/RPO.
Fresh Redis does not retain runtime admission counters: reconcile capacity/cost protection
before admitting new work. Publish recovered jobs only through the original Dispatcher;
check RQ FINISHED and one business settlement, rather than forcing a second attempt.

After any incident or rollback, require: `/health` 200, one anonymous upload, refresh
recovery, score and piano-roll rendering, three valid downloads, immediate delete, one
successful Cleanup cycle, and a clean browser console at desktop and 375 px widths.
