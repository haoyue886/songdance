from app.services.queue import queue_job_id
from app.settings import Settings
from app.worker import create_worker


def test_rq_job_id_is_deterministic_and_does_not_expose_task_token() -> None:
    settings = Settings(
        environment="test", download_signing_secret="test-secret-at-least-32-characters"
    )
    task_token = "private-anonymous-task-token-1234567890"

    first = queue_job_id(task_token, 1, settings)
    repeated = queue_job_id(task_token, 1, settings)
    retry = queue_job_id(task_token, 2, settings)

    assert first == repeated
    assert first != retry
    assert task_token not in first
    assert first.startswith("transcription-")
    assert len(first) == len("transcription-") + 64


def test_worker_disables_rq_argument_descriptions() -> None:
    worker = create_worker(Settings(environment="test"))

    assert worker.log_job_description is False
