import json
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INFRA_ROOT = PROJECT_ROOT / "infra"


def _env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0])
    return keys


def test_vercel_contract_targets_next_build() -> None:
    config = json.loads((PROJECT_ROOT / "web/vercel.json").read_text(encoding="utf-8"))

    assert config["framework"] == "nextjs"
    assert config["installCommand"].endswith("pnpm install --frozen-lockfile")
    assert config["buildCommand"] == "pnpm build"
    header_keys = {item["key"] for item in config["headers"][0]["headers"]}
    assert {"X-Content-Type-Options", "X-Frame-Options", "Strict-Transport-Security"} <= header_keys


def test_railway_services_use_the_production_docker_image() -> None:
    expected_commands = {
        "railway.toml": "./docker-entrypoint.sh",
        "railway-worker.toml": "python -m app.worker",
        "railway-cleanup.toml": "python -m app.jobs.cleanup",
    }
    for filename, command in expected_commands.items():
        config = tomllib.loads((INFRA_ROOT / filename).read_text(encoding="utf-8"))
        assert config["build"]["dockerfilePath"] == "api/Dockerfile"
        assert config["deploy"]["startCommand"] == command

    cleanup = tomllib.loads((INFRA_ROOT / "railway-cleanup.toml").read_text(encoding="utf-8"))
    worker = tomllib.loads((INFRA_ROOT / "railway-worker.toml").read_text(encoding="utf-8"))
    assert cleanup["deploy"]["cronSchedule"] == "*/15 * * * *"
    assert worker["deploy"]["restartPolicyType"] == "ON_FAILURE"
    assert worker["deploy"]["restartPolicyMaxRetries"] == 5


def test_production_env_contract_covers_runtime_services() -> None:
    keys = _env_keys(INFRA_ROOT / "env.production.example")

    assert {
        "SONGDANCE_ENVIRONMENT",
        "SONGDANCE_CORS_ORIGINS",
        "SONGDANCE_DATABASE_URL",
        "SONGDANCE_REDIS_URL",
        "SONGDANCE_STORAGE_BACKEND",
        "SONGDANCE_S3_ENDPOINT_URL",
        "SONGDANCE_S3_BUCKET",
        "SONGDANCE_S3_ACCESS_KEY",
        "SONGDANCE_S3_SECRET_KEY",
        "SONGDANCE_TRUSTED_PROXY_HOPS",
        "SONGDANCE_TRUSTED_PROXY_CIDRS",
        "SONGDANCE_DOWNLOAD_SIGNING_SECRET",
        "SONGDANCE_DAILY_JOB_LIMIT",
        "SONGDANCE_YOUTUBE_ENABLED",
    } <= keys


def test_modelscope_container_drops_application_privileges() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    supervisor = (PROJECT_ROOT / "deploy/supervisord.conf").read_text(encoding="utf-8")
    nginx = (PROJECT_ROOT / "deploy/nginx.conf").read_text(encoding="utf-8")
    start_script = (PROJECT_ROOT / "deploy/start-modelscope.sh").read_text(
        encoding="utf-8"
    )

    assert "useradd --system --gid songdance" in dockerfile
    assert supervisor.count("user=songdance") == 5
    assert "user songdance;" in nginx
    assert "runuser -u songdance --preserve-environment" in start_script


def test_modelscope_container_provides_writable_numba_cache() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ENV NUMBA_CACHE_DIR=/tmp/songdance-numba-cache" in dockerfile
    assert "/tmp/songdance-numba-cache" in dockerfile
    assert "chown -R songdance:songdance" in dockerfile


def test_modelscope_proxy_does_not_trust_inbound_forwarded_for() -> None:
    nginx = (PROJECT_ROOT / "deploy/nginx.conf").read_text(encoding="utf-8")

    assert "$http_x_forwarded_for" not in nginx
    assert nginx.count("proxy_set_header X-Forwarded-For $remote_addr;") == 2


def test_modelscope_healthcheck_uses_dependency_readiness() -> None:
    nginx = (PROJECT_ROOT / "deploy/nginx.conf").read_text(encoding="utf-8")

    assert "proxy_pass http://127.0.0.1:8000/ready;" in nginx
