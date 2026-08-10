from redis import Redis
from rq import Queue, Worker

from app.settings import Settings, get_settings


def create_worker(settings: Settings) -> Worker:
    connection = Redis.from_url(str(settings.redis_url))
    queue = Queue(settings.queue_name, connection=connection)
    return Worker([queue], connection=connection, log_job_description=False)


def main() -> None:
    worker = create_worker(get_settings())
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
