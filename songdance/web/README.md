# SongDance Web

Next.js frontend for SongDance. Use pnpm; other package managers are not supported by this repository.

## Run locally

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Open http://localhost:3000. The current Phase 1 page is implemented in `src/app/page.tsx`; upload and transcription arrive in later phases from the root development plan.

## Verify

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

The production image uses Next.js standalone output and is built by `Dockerfile`.
