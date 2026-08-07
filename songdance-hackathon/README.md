# SongDance

Public Web MVP that turns a short piano recording into editable MIDI, MusicXML and sheet music.

## Current phase

Phases 1-7 provide the public product shell, real upload and transcription pipeline,
score workspace, anonymous quotas, signed downloads, 24-hour cleanup, privacy-safe
events, public privacy/terms pages, feature-gated YouTube clip import, and a verified
public-domain example result. Phase 8 provides production-ready Vercel and Railway
configuration plus deployment, rollback and operations documentation.

## Web

```bash
cd web
pnpm install
pnpm dev
```

Open http://localhost:3000.

## API

Python 3.11 is required.

```bash
cd api
uv sync
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000/health.

## Containers

When Docker is available:

```bash
docker compose up --build
```

The compose stack includes Web, API, Worker, periodic cleanup, PostgreSQL, Redis and
private MinIO storage. Copy `.env.example` values into your local environment and
replace the signing and storage secrets before using production mode.

YouTube import is disabled by default. Set `SONGDANCE_YOUTUBE_ENABLED=true` only where
the deployment includes yt-dlp and FFmpeg and the operating region permits the feature.
The importer ignores local yt-dlp configuration, forces direct connections without
cookies or browser credentials, and does not bypass private, login, regional, paid,
live, or platform restrictions.
The API image uses `tini` as PID 1 so timed-out yt-dlp/FFmpeg process groups are reaped.

## Production deployment

Deploy `web/` to Vercel. Deploy the API, RQ worker and cleanup cron from the same
repository to Railway or another Docker platform; the model pipeline is intentionally
not packaged as a Vercel Function. Start with [docs/deployment.md](docs/deployment.md)
and use [infra/env.production.example](infra/env.production.example) as the variable
contract. Operational recovery procedures are in [docs/runbook.md](docs/runbook.md).
