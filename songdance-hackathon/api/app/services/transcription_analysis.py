import logging
from pathlib import Path

from app.pipeline.analysis import (
    AnalysisConfig,
    StructureAnalysis,
    analyze_audio,
    fallback_analysis,
)
from app.pipeline.errors import PipelineError

logger = logging.getLogger(__name__)


def analyze_with_fallback(
    source: Path, config: AnalysisConfig, job_id: str
) -> StructureAnalysis:
    try:
        return analyze_audio(source, config)
    except PipelineError as error:
        return fallback_analysis(config, error.code)
    except Exception:
        logger.exception("Unexpected structure analysis failure for job %s", job_id)
        return fallback_analysis(config, "STRUCTURE_ANALYSIS_UNEXPECTED_ERROR")
