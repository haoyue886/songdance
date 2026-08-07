from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import create_db_engine, create_session_factory
from app.middleware.origin import OriginEnforcementMiddleware
from app.middleware.request_size import RequestSizeLimitMiddleware
from app.middleware.trusted_proxy import TrustedProxyOnlyMiddleware
from app.models import Base
from app.observability import RequestObservabilityMiddleware, configure_logging
from app.routes.analytics import router as analytics_router
from app.routes.downloads import router as downloads_router
from app.routes.jobs import router as jobs_router
from app.routes.youtube import router as youtube_router
from app.services.queue import JobQueue, create_job_queue
from app.services.quota import JobQuota, create_job_quota
from app.services.readiness import check_readiness
from app.services.storage import ObjectStorage, create_storage
from app.settings import Settings, get_settings


def create_app(
    settings: Settings | None = None,
    storage: ObjectStorage | None = None,
    job_queue: JobQueue | None = None,
    job_quota: JobQuota | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    engine = create_db_engine(resolved_settings)
    session_factory = create_session_factory(engine)
    if resolved_settings.auto_create_schema:
        Base.metadata.create_all(engine)

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.3.0",
        docs_url="/docs" if resolved_settings.environment != "production" else None,
    )
    app.state.settings = resolved_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.storage = storage or create_storage(resolved_settings)
    app.state.job_queue = job_queue or create_job_queue(resolved_settings)
    app.state.job_quota = job_quota or create_job_quota(resolved_settings)

    configure_logging()
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=resolved_settings.max_request_bytes)
    app.add_middleware(RequestObservabilityMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(
        OriginEnforcementMiddleware,
        allowed_origins=resolved_settings.cors_origin_list,
    )
    app.add_middleware(
        TrustedProxyOnlyMiddleware,
        enabled=resolved_settings.environment == "production",
        networks=resolved_settings.trusted_proxy_networks,
    )
    app.include_router(jobs_router)
    app.include_router(downloads_router)
    app.include_router(analytics_router)
    app.include_router(youtube_router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "songdance-api", "version": app.version}

    @app.get("/ready", tags=["system"])
    def ready() -> JSONResponse:
        components = check_readiness(resolved_settings)
        available = all(components.values())
        return JSONResponse(
            status_code=200 if available else 503,
            content={
                "status": "ready" if available else "unavailable",
                "components": components,
            },
        )

    return app


app = create_app()
