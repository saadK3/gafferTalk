from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from gaffertalk_api.config import get_settings
from gaffertalk_api.domain.errors import (
    InvalidTeamIdError,
    InvalidUpstreamFplResponseError,
    UpstreamFplTimeoutError,
    UpstreamFplUnavailableError,
)
from gaffertalk_api.domain.models import Player, Position, SquadLookupResult
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.services.player_catalogue import PlayerCatalogueLoader
from gaffertalk_api.services.team_loader import TeamLoader


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


class PlayerSearchResponse(BaseModel):
    players: tuple[Player, ...]
    retrieved_at: datetime


settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    client = FplClient(
        base_url=settings.fpl_base_url,
        timeout_seconds=settings.fpl_timeout_seconds,
        max_attempts=settings.fpl_max_attempts,
    )
    application.state.team_loader = TeamLoader(client)
    application.state.player_catalogue = PlayerCatalogueLoader(client)
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
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


def get_team_loader(request: Request) -> TeamLoader:
    return request.app.state.team_loader


def get_player_catalogue(request: Request) -> PlayerCatalogueLoader:
    return request.app.state.player_catalogue


@app.get(
    "/v1/entries/{team_id}/squad",
    response_model=SquadLookupResult,
    tags=["FPL entries"],
)
async def get_entry_squad(
    team_id: Annotated[int, Path(gt=0, description="Public FPL Team ID")],
    loader: Annotated[TeamLoader, Depends(get_team_loader)],
) -> SquadLookupResult:
    """Load the latest publicly finalized squad for an FPL Team ID."""

    try:
        return await loader.load(team_id)
    except InvalidTeamIdError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "invalid_team_id", "message": str(error)},
        ) from error
    except UpstreamFplTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "upstream_timeout", "message": str(error)},
        ) from error
    except InvalidUpstreamFplResponseError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "invalid_upstream_response", "message": str(error)},
        ) from error
    except UpstreamFplUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "upstream_unavailable", "message": str(error)},
        ) from error


@app.get("/v1/players", response_model=PlayerSearchResponse, tags=["FPL players"])
async def search_players(
    position: Annotated[Position, Query(description="Required FPL position")],
    query: Annotated[str, Query(min_length=2, max_length=40)],
    loader: Annotated[PlayerCatalogueLoader, Depends(get_player_catalogue)],
) -> PlayerSearchResponse:
    """Search current public FPL players for a recorded squad change."""

    try:
        players = await loader.search(position=position, query=query)
        return PlayerSearchResponse(players=players, retrieved_at=datetime.now(UTC))
    except UpstreamFplTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "upstream_timeout", "message": str(error)},
        ) from error
    except InvalidUpstreamFplResponseError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "invalid_upstream_response", "message": str(error)},
        ) from error
    except UpstreamFplUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "upstream_unavailable", "message": str(error)},
        ) from error
