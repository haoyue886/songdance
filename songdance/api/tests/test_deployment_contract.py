import json
import re
import shlex
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INFRA_ROOT = PROJECT_ROOT / "infra"


def _has_fail_closed_apt_upgrade(stage: str) -> bool:
    runs = re.findall(r"(?m)^RUN\s+((?:[^\n]*\\\n)*[^\n]*)", stage)
    expected = shlex.split(
        "apt-get -o APT::Update::Error-Mode=any update"
        " && apt-get upgrade -y --no-install-recommends"
        " && apt-get install -y --no-install-recommends"
    )
    for run in runs:
        command = re.sub(r"\\\n\s*", " ", run)
        # Keep quotes so echoed separators cannot become shell operators.
        lexer = shlex.shlex(command, posix=False, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        tokens = list(lexer)
        if any(token in {"||", ";", "|", "&", "(", ")"} for token in tokens):
            continue
        for index in range(len(tokens) - len(expected) + 1):
            if (index == 0 or tokens[index - 1] == "&&") and (
                tokens[index : index + len(expected)] == expected
            ):
                return True
    return False


def test_image_refreshes_security_packages_in_both_runtime_stages() -> None:
    dockerfile = (PROJECT_ROOT / "api/Dockerfile").read_text(encoding="utf-8")
    stages = dockerfile.split("\nFROM ")[1:]
    assert len(stages) == 2
    assert all(_has_fail_closed_apt_upgrade(stage) for stage in stages)


def test_apt_security_contract_rejects_ignored_or_split_update_commands() -> None:
    strict_update = "apt-get -o APT::Update::Error-Mode=any update"
    upgrade = "apt-get upgrade -y --no-install-recommends"
    install = "apt-get install -y --no-install-recommends tini"

    assert not _has_fail_closed_apt_upgrade(
        f"RUN {strict_update} || true && {upgrade} && {install}"
    )
    assert not _has_fail_closed_apt_upgrade(f"RUN echo '{strict_update} && {upgrade} && {install}'")
    assert not _has_fail_closed_apt_upgrade(
        f"RUN echo 'noop && {strict_update} && {upgrade} && {install}'"
    )
    assert not _has_fail_closed_apt_upgrade(
        f"RUN echo noop '&&' {strict_update} '&&' {upgrade} '&&' {install}"
    )
    assert not _has_fail_closed_apt_upgrade(f"RUN {strict_update} && {upgrade} && {install}; true")
    assert not _has_fail_closed_apt_upgrade(f"# RUN {strict_update} && {upgrade} && {install}")
    assert not _has_fail_closed_apt_upgrade(f"RUN {strict_update} && {upgrade}\nRUN {install}")


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
