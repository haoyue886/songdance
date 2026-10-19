"""Test-only listener for the signed Creem callback, without account or job routes."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect

from app.database import create_db_engine, create_session_factory
from app.models import BillingWebhookEvent
from app.observability import RequestObservabilityMiddleware, configure_logging
from app.routes.billing import webhook
from app.settings import Settings


def create_billing_hook_app(settings: Settings) -> FastAPI:
    if (
        settings.environment != "test"
        or settings.billing_environment != "test"
        or settings.auto_create_schema
    ):
        raise ValueError("Billing listener requires test mode and explicit migrations")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_db_engine(settings)
        try:
            schema = inspect(engine)
            table = BillingWebhookEvent.__table__
            if not schema.has_table(table.name) or not set(table.columns.keys()).issubset(
                column["name"] for column in schema.get_columns(table.name)
            ):
                raise ValueError("Billing inbox migration is required")
            app.state.engine = engine
            app.state.session_factory = create_session_factory(engine)
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="Notavue billing test callback",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    app.state.settings = settings
    configure_logging()
    app.add_middleware(RequestObservabilityMiddleware)
    app.add_api_route("/webhooks/creem", webhook, methods=["POST"])
    return app
