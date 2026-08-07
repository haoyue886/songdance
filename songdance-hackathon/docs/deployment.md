# Vercel deployment guide

SongDance uses Vercel for the public Next.js website and Railway for the stateful,
long-running Python services. Do not deploy the transcription pipeline as a Vercel
Function: it needs FFmpeg, Basic Pitch, a persistent RQ worker and a scheduled cleanup
process.

## Architecture

```text
Browser
  -> Vercel Web (web/)
  -> Railway API (api/Dockerfile, public HTTPS)
       -> Railway PostgreSQL
       -> Railway Redis -> Railway RQ Worker
       -> private S3-compatible bucket
       -> Railway Cleanup Cron
```

The API is the only component allowed to read or write the bucket. The browser receives
short-lived signed download paths, never permanent object URLs.

## Accounts and repository

You need Vercel, Railway, an S3-compatible provider such as Cloudflare R2, and a private
Git repository accessible to Vercel and Railway. Push the contents of the `songdance/`
directory as the repository root. Do not commit `.env`, credentials, database files,
audio uploads, or `api/uv.lock`.

## 1. Create private object storage

1. Create a private bucket, for example `songdance-production`.
2. Create an S3 API credential restricted to that bucket for object read/write/delete
   and multipart upload cleanup.
3. Keep public bucket access disabled. Browser CORS is unnecessary because all object
   access goes through the API.
4. If the provider supports lifecycle rules, add a one-day expiration rule as a backup.
   The application cleanup Cron remains authoritative because it also deletes database
   metadata and releases quota state.

Record the endpoint, region, bucket, access key and secret key in a password manager.

## 2. Create Railway data services

1. Create one Railway project and add PostgreSQL and Redis services.
2. Keep both on Railway private networking. Do not create public database or Redis
   domains.
3. Copy the provider variables into the application services using Railway variable
   references. `SONGDANCE_DATABASE_URL` accepts Railway's `postgresql://` URL and
   normalizes it to the installed psycopg driver.

## 3. Create the Railway API

Create a service from the private repository and set its config file path to
`/infra/railway.toml`. Give only this service a public Railway domain.

Copy every `SONGDANCE_*` variable from `infra/env.production.example` into the service,
replacing placeholders. Important values:

- `SONGDANCE_CORS_ORIGINS`: the final Vercel production origin, with no trailing path.
- `SONGDANCE_DATABASE_URL`: private Railway PostgreSQL URL.
- `SONGDANCE_REDIS_URL`: private Railway Redis URL.
- `SONGDANCE_DOWNLOAD_SIGNING_SECRET`: generate with `openssl rand -hex 32`.
- `SONGDANCE_STORAGE_BACKEND=s3`: production must use durable shared storage.
- `SONGDANCE_YOUTUBE_ENABLED=false`: leave off for the first release.
- `SONGDANCE_GLOBAL_ACTIVE_JOB_LIMIT=2` and `SONGDANCE_DAILY_JOB_LIMIT=25`: initial cost
  ceiling; raise only after measuring memory and processing cost.

The container entrypoint runs `alembic upgrade head` before Uvicorn. A successful deploy
must return HTTP 200 from `https://API_DOMAIN/health`.

`infra/env.production.example` deliberately uses the reserved `192.0.2.0/24` documentation
range. Before deployment, replace it with the exact Railway edge peer CIDR. The API rejects
`0.0.0.0/0` and `::/0` in production; never use a default route to make a proxy check pass.
If Railway cannot provide a stable edge CIDR, keep the API behind a private gateway that
does, or change the proxy boundary before exposing the service.

## 4. Create the Worker and Cleanup services

Create two more services from the same commit:

| Service | Config path | Public domain | Replicas |
|---|---|---:|---:|
| Worker | `/infra/railway-worker.toml` | No | 1 |
| Cleanup | `/infra/railway-cleanup.toml` | No | Cron |

Give both the same database, Redis, storage, signing and limit variables as the API.
The Worker must show an RQ startup line and listen to the `songdance` queue. The Cleanup
service runs once every 15 minutes and must log `cleanup_cycle` with `failed=0`.

Do not scale the Worker above one replica until model memory and queue behavior have been
measured. Each worker process loads the transcription model.

## 5. Deploy the Web to Vercel

1. Import the same private repository into Vercel.
2. Set **Root Directory** to `web`.
3. Keep Framework Preset as Next.js. `web/vercel.json` supplies the install command,
   build command and response security headers.
4. Add `NEXT_PUBLIC_API_URL=https://API_DOMAIN` to Production and Preview environments.
5. Deploy and note the final `https://*.vercel.app` URL.
6. Return to the Railway API and set `SONGDANCE_CORS_ORIGINS` to that exact origin, then
   redeploy the API. If a custom Web domain is added, include both HTTPS origins separated
   by commas during the migration, then remove the obsolete origin.

Because `NEXT_PUBLIC_API_URL` is compiled into browser JavaScript, changing it requires a
new Vercel deployment.

## 6. Production acceptance checklist

Run these checks after deployment; they are not proven until run against the real URLs.

1. `curl --fail https://API_DOMAIN/health` returns `status=ok`.
2. Open the Vercel URL in a private window; `/`, `/transcribe`, `/examples`, `/privacy`
   and `/terms` load without authentication.
3. Upload legal 1-second, 30-second and 90-second WAV samples. Repeat representative
   uploads for MP3 and M4A; reject an invalid file and a file over 25 MB.
4. Refresh the job URL while queued and confirm progress recovers.
5. Confirm score and piano-roll views, original/MIDI playback, loop, speed and transpose.
6. Download MIDI, MusicXML and PDF; parse MIDI/MusicXML and visually inspect the PDF.
7. Delete the job and confirm its URL returns expired/not found and downloads stop.
8. Submit four jobs from one client within an hour; the fourth must return HTTP 429.
9. Set one test job's expiry in the past, run Cleanup once, and confirm database rows and
   bucket objects are gone. Restore the normal Cron afterward.
10. Run the fixed 10-clip human regression suite on the deployed model; retain the signed
    review record proving at least 7/10 usable clips.
11. Repeat the core upload flow at 375 px width and check there is no horizontal overflow.
12. Keep YouTube disabled and confirm local upload remains complete.

## Rollback

1. In Vercel, promote the previous successful deployment.
2. In Railway, roll API and Worker back to the same previous Git commit. Never roll only
   one of them when queue payload or model code changed.
3. Database migrations are forward-only during an incident. If the previous application
   cannot read the new schema, deploy a compatibility fix instead of destructively
   downgrading production data.
4. Pause new jobs by setting `SONGDANCE_DAILY_JOB_LIMIT=1` and waiting for active work to
   drain; do not delete Redis while jobs are running.
5. Validate `/health`, one upload, all three downloads and deletion before reopening the
   daily limit.

Official references: [Vercel project configuration](https://vercel.com/docs/projects/project-configuration),
[Railway config as code](https://docs.railway.com/reference/config-as-code), and
[Railway public networking](https://docs.railway.com/networking/public-networking).
