from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from gaffertalk_api.config import get_settings
from gaffertalk_api.domain.errors import (
    InvalidTeamIdError,
    InvalidUpstreamFplResponseError,
    UpstreamFplNotFoundError,
    UpstreamFplTimeoutError,
    UpstreamFplUnavailableError,
)
from gaffertalk_api.domain.models import Player, Position, SquadLookupResult
from gaffertalk_api.domain.pro_research import (
    NamedTransferResearchResponse,
    SquadActionResearchResponse,
)
from gaffertalk_api.domain.recommendation_requests import (
    ConversationalRecommendationRequest,
    ConversationalRecommendationResponse,
    ConversationOutcome,
    CurrentSquadInput,
    DemoSquadResponse,
    FreeQuestionQuota,
    NamedTransferResearchRequest,
    OutgoingSelectionMode,
    SquadActionResearchRequest,
    TransferRecommendationRequest,
)
from gaffertalk_api.domain.recommendations import RecommendationResult
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.llm.groq import GroqConversationClient
from gaffertalk_api.services.conversation_preflight import ConversationPreflightService
from gaffertalk_api.services.free_question_usage import (
    FreeQuestionLimitExceededError,
    FreeQuestionUsageStore,
    select_quota_gameweek,
)
from gaffertalk_api.services.player_catalogue import PlayerCatalogueLoader
from gaffertalk_api.services.pro_research_loader import ProResearchLoader
from gaffertalk_api.services.recommendation_loader import RecommendationLoader
from gaffertalk_api.services.synthetic_squad import (
    DEFAULT_SYNTHETIC_SQUAD_PATH,
    load_synthetic_squad,
)
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
    application.state.recommendation_loader = RecommendationLoader(client)
    application.state.pro_research_loader = ProResearchLoader(client)
    application.state.free_usage = FreeQuestionUsageStore(
        settings.free_usage_database_path,
        settings.free_question_limit,
    )
    application.state.groq_client = (
        GroqConversationClient(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            base_url=settings.groq_base_url,
            timeout_seconds=settings.groq_timeout_seconds,
        )
        if settings.groq_api_key
        else None
    )
    try:
        yield
    finally:
        if application.state.groq_client is not None:
            await application.state.groq_client.aclose()
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
    allow_methods=["GET", "POST"],
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


def get_recommendation_loader(request: Request) -> RecommendationLoader:
    return request.app.state.recommendation_loader


def get_pro_research_loader(request: Request) -> ProResearchLoader:
    return request.app.state.pro_research_loader


def get_free_usage(request: Request) -> FreeQuestionUsageStore:
    return request.app.state.free_usage


def free_client_id(
    value: Annotated[str, Header(alias="X-GafferTalk-Client-ID", min_length=36, max_length=36)],
) -> str:
    try:
        return str(UUID(value))
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_client_id", "message": "The browser ID is invalid."},
        ) from error


def upstream_http_exception(error: Exception) -> HTTPException:
    if isinstance(error, UpstreamFplTimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "upstream_timeout", "message": str(error)},
        )
    if isinstance(error, InvalidUpstreamFplResponseError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "invalid_upstream_response", "message": str(error)},
        )
    if isinstance(error, UpstreamFplNotFoundError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "upstream_evidence_missing",
                "message": "FPL did not provide required player evidence.",
            },
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "upstream_unavailable", "message": str(error)},
    )


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


@app.post(
    "/v1/recommendations/transfers",
    response_model=RecommendationResult,
    tags=["recommendations"],
)
async def recommend_transfer(
    request: TransferRecommendationRequest,
    loader: Annotated[RecommendationLoader, Depends(get_recommendation_loader)],
) -> RecommendationResult:
    """Rank legal one-player replacements using live public FPL data."""

    try:
        return await loader.recommend(request)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_recommendation_state", "message": str(error)},
        ) from error


@app.post(
    "/v1/pro/research/named-transfer",
    response_model=NamedTransferResearchResponse,
    tags=["Pro research"],
)
async def research_named_transfer(
    request: NamedTransferResearchRequest,
    http_request: Request,
    loader: Annotated[ProResearchLoader, Depends(get_pro_research_loader)],
) -> NamedTransferResearchResponse:
    """Compare a requested one-player move with holding, waiting and alternatives."""

    groq: GroqConversationClient | None = http_request.app.state.groq_client
    if groq is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "pro_research_unconfigured",
                "message": "Pro research needs a configured Groq API key.",
            },
        )
    try:
        report = await loader.named_transfer(request)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_pro_research_state", "message": str(error)},
        ) from error
    except (
        InvalidUpstreamFplResponseError,
        UpstreamFplNotFoundError,
        UpstreamFplTimeoutError,
        UpstreamFplUnavailableError,
    ) as error:
        raise upstream_http_exception(error) from error
    try:
        assistant_message = await groq.synthesize_pro_report(request.question, report)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "pro_grounding_rejected",
                "message": "The research summary failed its grounding check.",
            },
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "pro_research_unavailable", "message": "Groq is unavailable."},
        ) from error
    return NamedTransferResearchResponse(
        report=report,
        assistant_message=assistant_message,
        provider="groq",
        model=groq.model,
    )


@app.post(
    "/v1/pro/research/squad-action",
    response_model=SquadActionResearchResponse,
    tags=["Pro research"],
)
async def research_squad_action(
    request: SquadActionResearchRequest,
    http_request: Request,
    loader: Annotated[ProResearchLoader, Depends(get_pro_research_loader)],
) -> SquadActionResearchResponse:
    """Rank the best legal squad action against rolling under a selected risk policy."""

    groq: GroqConversationClient | None = http_request.app.state.groq_client
    if groq is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "pro_research_unconfigured",
                "message": "Pro research needs a configured Groq API key.",
            },
        )
    try:
        report = await loader.squad_action(request)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_pro_research_state", "message": str(error)},
        ) from error
    except (
        InvalidUpstreamFplResponseError,
        UpstreamFplNotFoundError,
        UpstreamFplTimeoutError,
        UpstreamFplUnavailableError,
    ) as error:
        raise upstream_http_exception(error) from error
    try:
        assistant_message = await groq.synthesize_squad_action_report(request.question, report)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "pro_grounding_rejected",
                "message": "The research summary failed its grounding check.",
            },
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "pro_research_unavailable", "message": "Groq is unavailable."},
        ) from error
    return SquadActionResearchResponse(
        report=report,
        assistant_message=assistant_message,
        provider="groq",
        model=groq.model,
    )


@app.post(
    "/v1/recommendations/conversation",
    response_model=ConversationalRecommendationResponse,
    tags=["recommendations"],
)
async def conversational_recommendation(
    request: ConversationalRecommendationRequest,
    http_request: Request,
    loader: Annotated[RecommendationLoader, Depends(get_recommendation_loader)],
    catalogue_loader: Annotated[PlayerCatalogueLoader, Depends(get_player_catalogue)],
    usage: Annotated[FreeQuestionUsageStore, Depends(get_free_usage)],
    client_id: Annotated[str, Depends(free_client_id)],
) -> ConversationalRecommendationResponse:
    """Interpret and explain a deterministic recommendation through Groq."""

    groq: GroqConversationClient | None = http_request.app.state.groq_client
    if groq is None and request.selection_mode is OutgoingSelectionMode.SELECTED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "conversation_unconfigured",
                "message": "Conversational recommendations need a configured Groq API key.",
            },
        )
    try:
        catalogue = await catalogue_loader.load()
    except (
        InvalidUpstreamFplResponseError,
        UpstreamFplTimeoutError,
        UpstreamFplUnavailableError,
    ) as error:
        raise upstream_http_exception(error) from error
    gameweek = select_quota_gameweek(catalogue.gameweeks)
    try:
        if request.selection_mode is OutgoingSelectionMode.AUTO:
            snapshot = RecommendationLoader.build_snapshot(request.squad, catalogue)
            discovery = ConversationPreflightService().discover_route(
                question=request.question,
                snapshot=snapshot,
                catalogue=catalogue,
                bank_tenths=request.squad.bank_tenths,
                free_transfers=request.squad.free_transfers,
            )
            assert discovery.outcome is not None and discovery.message is not None
            return ConversationalRecommendationResponse(
                assistant_message=discovery.message,
                interpreted_outgoing_player_id=(
                    discovery.suggested_outgoing.id
                    if discovery.suggested_outgoing is not None
                    else None
                ),
                outcome=discovery.outcome,
                target=discovery.target,
                suggested_outgoing=discovery.suggested_outgoing,
                provider="deterministic",
                model="none",
                quota=usage.status(client_id, gameweek),
            )
        assert request.outgoing_player_id is not None
        assert request.outgoing_selling_price_tenths is not None
        snapshot, planning_state = RecommendationLoader.build_state(
            request.squad,
            request.outgoing_player_id,
            request.outgoing_selling_price_tenths,
            catalogue,
        )
        preflight = ConversationPreflightService().validate(
            question=request.question,
            outgoing_player_id=request.outgoing_player_id,
            snapshot=snapshot,
            catalogue=catalogue,
            state=planning_state,
        )
    except (ValueError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_conversation", "message": str(error)},
        ) from error
    if not preflight.can_recommend:
        assert preflight.outcome is not None and preflight.message is not None
        return ConversationalRecommendationResponse(
            assistant_message=preflight.message,
            interpreted_outgoing_player_id=request.outgoing_player_id,
            outcome=preflight.outcome,
            target=preflight.target,
            provider="deterministic",
            model="none",
            quota=usage.status(client_id, gameweek),
        )
    if groq is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "conversation_unconfigured",
                "message": "Conversational recommendations need a configured Groq API key.",
            },
        )
    try:
        quota = usage.reserve(client_id, gameweek)
    except FreeQuestionLimitExceededError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "free_question_limit_reached",
                "message": str(error),
                "quota": error.quota.model_dump(mode="json"),
            },
        ) from error
    completed = False
    try:
        squad_players = tuple(
            catalogue.players[player_id] for player_id in request.squad.player_ids
        )
        intent = await groq.interpret(request.question, squad_players, request.outgoing_player_id)
        recommendation_request = TransferRecommendationRequest(
            squad=request.squad,
            outgoing_player_id=request.outgoing_player_id,
            outgoing_selling_price_tenths=request.outgoing_selling_price_tenths,
            strategy=intent.strategy,
            target_player_id=preflight.target.id if preflight.target is not None else None,
        )
        result = await loader.recommend(recommendation_request)
        assistant_message = await groq.explain(request.question, result)
        response = ConversationalRecommendationResponse(
            assistant_message=assistant_message,
            interpreted_outgoing_player_id=intent.outgoing_player_id,
            outcome=ConversationOutcome.RECOMMENDATION,
            target=preflight.target,
            result=result,
            provider="groq",
            model=groq.model,
            quota=quota,
        )
        completed = True
        return response
    except (ValueError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_conversation", "message": str(error)},
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "conversation_unavailable", "message": "Groq is unavailable."},
        ) from error
    except (
        InvalidUpstreamFplResponseError,
        UpstreamFplTimeoutError,
        UpstreamFplUnavailableError,
    ) as error:
        raise upstream_http_exception(error) from error
    finally:
        if not completed:
            usage.release(client_id, gameweek)


@app.get("/v1/free/usage", response_model=FreeQuestionQuota, tags=["recommendations"])
async def free_question_usage(
    client_id: Annotated[str, Depends(free_client_id)],
    usage: Annotated[FreeQuestionUsageStore, Depends(get_free_usage)],
    loader: Annotated[PlayerCatalogueLoader, Depends(get_player_catalogue)],
) -> FreeQuestionQuota:
    """Return this anonymous browser's Free allowance for the active FPL Gameweek."""

    try:
        catalogue = await loader.load()
    except (
        InvalidUpstreamFplResponseError,
        UpstreamFplTimeoutError,
        UpstreamFplUnavailableError,
    ) as error:
        raise upstream_http_exception(error) from error
    return usage.status(client_id, select_quota_gameweek(catalogue.gameweeks))


@app.get("/v1/demo/squad", response_model=DemoSquadResponse, tags=["development"])
async def get_demo_squad(
    loader: Annotated[PlayerCatalogueLoader, Depends(get_player_catalogue)],
) -> DemoSquadResponse:
    """Resolve the versioned synthetic squad against today's live FPL catalogue."""

    if settings.environment == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    catalogue = await loader.load()
    definition, snapshot, state = load_synthetic_squad(DEFAULT_SYNTHETIC_SQUAD_PATH, catalogue)
    assert state.bank is not None and state.free_transfers is not None
    return DemoSquadResponse(
        squad=CurrentSquadInput(
            name=definition.name,
            player_ids=tuple(pick.player.id for pick in snapshot.picks),
            bank_tenths=state.bank.tenths,
            free_transfers=state.free_transfers,
        ),
        players=tuple(pick.player for pick in snapshot.picks),
    )
