"""Test-only mail listener exposing the two signed callbacks and no other API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect

from app.database import create_db_engine, create_session_factory
from app.models.mail import MailDelivery, MailEvent, MailSuppression
from app.observability import RequestObservabilityMiddleware, configure_logging
from app.routes.mail import router
from app.settings import Settings


def create_mail_hook_app(settings: Settings) -> FastAPI:
    if settings.environment != "test" or settings.auto_create_schema:
        raise ValueError("Mail listener requires test mode and explicit migrations")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_db_engine(settings)
        try:
            schema = inspect(engine)
            for model in (MailDelivery, MailEvent, MailSuppression):
                table = model.__table__
                if not schema.has_table(table.name) or not set(table.columns.keys()).issubset(
                    column["name"] for column in schema.get_columns(table.name)
                ):
                    raise ValueError("Mail migration 014 is required")
            app.state.engine = engine
            app.state.session_factory = create_session_factory(engine)
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="Notavue mail test callbacks",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    app.state.settings = settings
    configure_logging()
    app.add_middleware(RequestObservabilityMiddleware)
    app.include_router(router)
    return app
