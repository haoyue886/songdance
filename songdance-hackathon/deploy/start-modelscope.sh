#!/bin/sh
set -eu

DATA_ROOT=/mnt/workspace/songdance
SECRET_FILE=$DATA_ROOT/download-signing-secret

mkdir -p "$DATA_ROOT/redis" "$DATA_ROOT/storage" "$DATA_ROOT/tmp"
chown -R songdance:songdance "$DATA_ROOT"

if [ -z "${SONGDANCE_DOWNLOAD_SIGNING_SECRET:-}" ]; then
    if [ ! -s "$SECRET_FILE" ]; then
        python -c 'import secrets; print(secrets.token_hex(32))' > "$SECRET_FILE"
        chown songdance:songdance "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
    fi
    SONGDANCE_DOWNLOAD_SIGNING_SECRET="$(sed -n '1p' "$SECRET_FILE")"
    export SONGDANCE_DOWNLOAD_SIGNING_SECRET
fi

export SONGDANCE_ENVIRONMENT="${SONGDANCE_ENVIRONMENT:-production}"
export SONGDANCE_CORS_ORIGINS="${SONGDANCE_CORS_ORIGINS:-https://modelscope.cn}"
export SONGDANCE_DATABASE_URL="${SONGDANCE_DATABASE_URL:-sqlite:////mnt/workspace/songdance/songdance.db}"
export SONGDANCE_REDIS_URL="${SONGDANCE_REDIS_URL:-redis://127.0.0.1:6379/0}"
export SONGDANCE_STORAGE_BACKEND="${SONGDANCE_STORAGE_BACKEND:-local}"
export SONGDANCE_LOCAL_STORAGE_PATH="${SONGDANCE_LOCAL_STORAGE_PATH:-$DATA_ROOT/storage}"
export SONGDANCE_TEMP_PATH="${SONGDANCE_TEMP_PATH:-$DATA_ROOT/tmp}"
export SONGDANCE_QUOTA_BACKEND="${SONGDANCE_QUOTA_BACKEND:-redis}"
export SONGDANCE_QUOTA_NAMESPACE="${SONGDANCE_QUOTA_NAMESPACE:-modelscope}"
export SONGDANCE_TRUSTED_PROXY_HOPS="${SONGDANCE_TRUSTED_PROXY_HOPS:-1}"
export SONGDANCE_TRUSTED_PROXY_CIDRS="${SONGDANCE_TRUSTED_PROXY_CIDRS:-127.0.0.1/32,::1/128}"
export SONGDANCE_GLOBAL_ACTIVE_JOB_LIMIT="${SONGDANCE_GLOBAL_ACTIVE_JOB_LIMIT:-1}"
export SONGDANCE_HOURLY_JOB_LIMIT="${SONGDANCE_HOURLY_JOB_LIMIT:-25}"
export SONGDANCE_DAILY_JOB_LIMIT="${SONGDANCE_DAILY_JOB_LIMIT:-25}"
export SONGDANCE_YOUTUBE_ENABLED="${SONGDANCE_YOUTUBE_ENABLED:-false}"

cd /app/api
runuser -u songdance --preserve-environment -- /usr/local/bin/alembic upgrade head

exec /usr/bin/supervisord -c /app/deploy/supervisord.conf
