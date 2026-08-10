FROM node:22-slim AS dependencies

ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org
ARG COREPACK_NPM_REGISTRY=https://registry.npmjs.org
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ENV NPM_CONFIG_REGISTRY=$NPM_CONFIG_REGISTRY
ENV COREPACK_NPM_REGISTRY=$COREPACK_NPM_REGISTRY
RUN corepack enable

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM dependencies AS builder
COPY . .
RUN pnpm build

FROM node:22-slim AS runner

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

WORKDIR /app
RUN groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
