"""FastAPI application composition."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from email_support.api.google_connection import router as google_connection_router
from email_support.api.health import router as health_router
from email_support.api.logging import install_auth_query_redaction
from email_support.api.owner_auth import owner_auth_runtime
from email_support.api.owner_auth import router as owner_auth_router


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    install_auth_query_redaction()
    async with owner_auth_runtime() as runtime:
        application.state.owner_auth_runtime = runtime
        yield


app = FastAPI(title="Email Support API", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(owner_auth_router)
app.include_router(google_connection_router)
