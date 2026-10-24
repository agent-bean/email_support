"""FastAPI application composition."""

from fastapi import FastAPI

from email_support.api.health import router as health_router

app = FastAPI(title="Email Support API", version="0.1.0")
app.include_router(health_router)
