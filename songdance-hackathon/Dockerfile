FROM node:22-slim AS web-dependencies

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH

RUN corepack enable

WORKDIR /build/web
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM web-dependencies AS web-builder

ENV NEXT_PUBLIC_API_URL=/api

COPY web/ ./
RUN pnpm build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV NODE_ENV=production

WORKDIR /app

RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get install -y --no-install-recommends \
        curl \
        ffmpeg \
        libsndfile1 \
        nginx \
        redis-server \
        supervisor \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.lock /app/api/requirements.lock
RUN pip install --no-cache-dir --requirement /app/api/requirements.lock \
    && pip install --no-cache-dir --no-deps basic-pitch==0.4.0

RUN groupadd --system songdance \
    && useradd --system --gid songdance --home-dir /nonexistent \
        --shell /usr/sbin/nologin songdance

ENV NUMBA_CACHE_DIR=/tmp/songdance-numba-cache

COPY --from=web-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=web-builder /build/web/public /app/web/public
COPY --from=web-builder /build/web/.next/standalone /app/web
COPY --from=web-builder /build/web/.next/static /app/web/.next/static

COPY api/alembic.ini /app/api/alembic.ini
COPY api/app /app/api/app
COPY deploy /app/deploy

RUN chmod +x /app/deploy/start-modelscope.sh \
    && mkdir -p /run/nginx /var/log/supervisor /tmp/nginx-client /tmp/nginx-proxy \
        /tmp/songdance-numba-cache \
    && chown -R songdance:songdance /app /run/nginx /var/log/supervisor \
        /tmp/nginx-client /tmp/nginx-proxy /tmp/songdance-numba-cache

EXPOSE 7860

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/deploy/start-modelscope.sh"]
