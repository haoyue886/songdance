from urllib.request import urlopen

from redis import Redis
from rq import Queue, Worker

from app.settings import Settings


def check_readiness(settings: Settings) -> dict[str, bool]:
    connection = Redis.from_url(
        str(settings.redis_url),
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        redis_ready = bool(connection.ping())
        queue = Queue(settings.queue_name, connection=connection)
        worker_ready = bool(Worker.all(connection=connection, queue=queue))
    except Exception:
        redis_ready = False
        worker_ready = False
    finally:
        connection.close()

    try:
        with urlopen("http://127.0.0.1:3000/", timeout=2) as response:
            web_ready = response.status == 200
    except Exception:
        web_ready = False

    return {"redis": redis_ready, "worker": worker_ready, "web": web_ready}
