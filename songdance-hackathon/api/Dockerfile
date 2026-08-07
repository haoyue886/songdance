ARG DEBIAN_MIRROR=deb.debian.org

FROM node:22-slim AS runtime-tools

ARG DEBIAN_MIRROR

RUN sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL=https://pypi.org/simple

COPY requirements.lock ./
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" --requirement requirements.lock
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" --no-deps basic-pitch==0.4.0

COPY --from=runtime-tools /usr/local/bin/node /usr/local/bin/node
COPY --from=runtime-tools /usr/bin/tini /usr/bin/tini
RUN node --version | grep -Eq '^v(2[2-9]|[3-9][0-9])\.' \
    && python -c 'from importlib.metadata import version; assert (version("yt-dlp"), version("yt-dlp-ejs")) == ("2026.7.4", "0.8.0")' \
    && tini --version

COPY alembic.ini ./
COPY app ./app
COPY docker-entrypoint.sh ./
RUN chmod +x ./docker-entrypoint.sh \
    && mkdir -p .data/storage .data/tmp

EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["./docker-entrypoint.sh"]
