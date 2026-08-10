import multiprocessing
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import TypeVar

from app.pipeline.errors import PipelineError, StructureAnalysisError

ResultT = TypeVar("ResultT")


def run_with_timeout(
    worker: Callable[..., ResultT], args: tuple[object, ...], timeout_seconds: float
) -> ResultT:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_invoke, args=(sender, worker, args), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout_seconds):
            process.terminate()
            process.join()
            raise StructureAnalysisError(
                "音频结构分析超时", code="STRUCTURE_ANALYSIS_TIMEOUT"
            )
        try:
            status, payload = receiver.recv()
        except EOFError as error:
            raise StructureAnalysisError("音频结构分析进程异常退出") from error
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join()
    if status == "ok":
        return payload
    if status == "pipeline_error":
        code, message = payload
        raise StructureAnalysisError(message, code=code)
    raise StructureAnalysisError()


def _invoke(
    sender: Connection,
    worker: Callable[..., ResultT],
    args: tuple[object, ...],
) -> None:
    try:
        sender.send(("ok", worker(*args)))
    except PipelineError as error:
        sender.send(("pipeline_error", (error.code, error.message)))
    except Exception:
        sender.send(("unexpected_error", None))
    finally:
        sender.close()
