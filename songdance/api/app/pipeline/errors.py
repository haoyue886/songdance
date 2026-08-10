class PipelineError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AudioPreprocessError(PipelineError):
    def __init__(self, message: str = "音频预处理失败") -> None:
        super().__init__("AUDIO_PREPROCESS_FAILED", message)


class AudioPreprocessTimeoutError(PipelineError):
    def __init__(self) -> None:
        super().__init__("AUDIO_PREPROCESS_TIMEOUT", "音频预处理超时")


class ModelInferenceError(PipelineError):
    def __init__(self, message: str = "钢琴转录模型执行失败") -> None:
        super().__init__("MODEL_INFERENCE_FAILED", message)


class NoNotesDetectedError(PipelineError):
    def __init__(self) -> None:
        super().__init__("NO_NOTES_DETECTED", "没有检测到可用的钢琴音符")


class NoteCleanupError(PipelineError):
    def __init__(self, message: str = "音符清洗失败") -> None:
        super().__init__("NOTE_CLEANUP_FAILED", message)


class StructureAnalysisError(PipelineError):
    def __init__(
        self,
        message: str = "音频结构分析失败",
        *,
        code: str = "STRUCTURE_ANALYSIS_FAILED",
    ) -> None:
        super().__init__(code, message)


class ScoreGenerationError(PipelineError):
    def __init__(self, message: str = "乐谱后处理失败") -> None:
        super().__init__("SCORE_GENERATION_FAILED", message)
