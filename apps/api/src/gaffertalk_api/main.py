from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from gaffertalk_api.config import get_settings


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["operations"])
async def health() -> HealthResponse:
    """Report whether the API process is ready to serve requests."""

    return HealthResponse(
        status="ok",
        service="gaffertalk-api",
        environment=settings.environment,
    )
