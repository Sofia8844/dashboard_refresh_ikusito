from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router

"""Punto de entrada de FastAPI para publicar los endpoints del microservicio."""

app = FastAPI(
    title="Dashboard Refresh Microservice",
    version="0.1.0",
    description="Asynchronous dashboard snapshot refresh service.",
)
app.include_router(router)
