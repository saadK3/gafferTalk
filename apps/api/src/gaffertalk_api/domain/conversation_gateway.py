from enum import StrEnum

from pydantic import Field, model_validator

from gaffertalk_api.domain.general_research import (
    GeneralResearchResponse,
    ResearchCapability,
)
from gaffertalk_api.domain.models import DomainModel
from gaffertalk_api.domain.multi_gameweek_planning import SellingPriceBasis
from gaffertalk_api.domain.pro_research import RiskPreference
from gaffertalk_api.domain.recommendation_requests import CurrentSquadInput


class ConversationIntentStatus(StrEnum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class ConversationResponseStatus(StrEnum):
    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class ConversationIntent(DomainModel):
    """The validated meaning extracted from one natural-language turn."""

    capability: ResearchCapability
    status: ConversationIntentStatus
    target_player_name: str | None = None
    horizon_gameweeks: int | None = Field(default=None, ge=1, le=2)
    maximum_points_hit: int | None = Field(default=None, ge=0, multiple_of=4)
    protected_player_names: tuple[str, ...] = Field(default=(), max_length=15)
    risk_preference: RiskPreference = RiskPreference.BALANCED
    objective: str | None = Field(default=None, max_length=160)
    missing_information: tuple[str, ...] = Field(default=(), max_length=8)
    clarification_question: str | None = None
    explanation: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def status_matches_question(self) -> "ConversationIntent":
        needs_question = self.status is ConversationIntentStatus.NEEDS_CLARIFICATION
        if needs_question != (self.clarification_question is not None):
            raise ValueError(
                "clarification intents must contain exactly one clarification question"
            )
        if self.status is ConversationIntentStatus.UNSUPPORTED:
            if self.capability is not ResearchCapability.UNSUPPORTED:
                raise ValueError("unsupported intents must use the unsupported capability")
        elif self.capability is ResearchCapability.UNSUPPORTED:
            raise ValueError("supported intents cannot use the unsupported capability")
        return self


class ConversationTurnRequest(DomainModel):
    """One user turn with optional manager state and conversation identifier."""

    conversation_id: str | None = Field(default=None, min_length=1, max_length=100)
    question: str = Field(min_length=3, max_length=500)
    squad: CurrentSquadInput | None = None
    selling_prices_tenths: dict[int, int] = Field(default_factory=dict)
    risk_preference: RiskPreference | None = None
    horizon_gameweeks: int | None = Field(default=None, ge=1, le=2)
    maximum_points_hit: int | None = Field(default=None, ge=0, multiple_of=4)
    protected_player_ids: tuple[int, ...] = Field(default=(), max_length=15)

    @model_validator(mode="after")
    def state_references_are_valid(self) -> "ConversationTurnRequest":
        squad_ids = set(self.squad.player_ids) if self.squad is not None else set()
        if self.squad is None and self.selling_prices_tenths and self.conversation_id is None:
            raise ValueError("selling prices require a confirmed squad")
        if self.squad is not None and not set(self.selling_prices_tenths).issubset(squad_ids):
            raise ValueError("selling prices may only reference players in the confirmed squad")
        if any(price < 0 or price > 300 for price in self.selling_prices_tenths.values()):
            raise ValueError("every selling price must be between £0.0m and £30.0m")
        if len(set(self.protected_player_ids)) != len(self.protected_player_ids):
            raise ValueError("protected players must be unique")
        if self.squad is None and self.protected_player_ids and self.conversation_id is None:
            raise ValueError("protected players require a confirmed squad")
        if self.squad is not None and not set(self.protected_player_ids).issubset(squad_ids):
            raise ValueError("protected players must belong to the confirmed squad")
        return self


class ConversationTurnRecord(DomainModel):
    question: str = Field(min_length=1, max_length=500)
    intent: ConversationIntent
    response_status: ConversationResponseStatus


class SellingPriceRequest(DomainModel):
    """A price the manager must confirm before a route can be treated as exact."""

    player_id: int = Field(gt=0)
    player_name: str = Field(min_length=1)
    current_fpl_price_tenths: int = Field(ge=0, le=300)
    reference_price_basis: SellingPriceBasis = SellingPriceBasis.CURRENT_PRICE_UPPER_BOUND
    reason: str = Field(min_length=1, max_length=300)


class ConversationResponse(DomainModel):
    """A natural conversation response with inspectable interpretation and research."""

    conversation_id: str
    question: str = Field(min_length=1, max_length=500)
    status: ConversationResponseStatus
    intent: ConversationIntent
    assistant_message: str = Field(min_length=1)
    research: GeneralResearchResponse | None = None
    selling_price_requests: tuple[SellingPriceRequest, ...] = Field(default=(), max_length=2)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class ConversationHistory(DomainModel):
    turns: tuple[ConversationTurnRecord, ...] = Field(default=(), max_length=8)


class ConversationContext(DomainModel):
    """Short-lived manager context retained between turns."""

    conversation_id: str
    squad: CurrentSquadInput | None = None
    selling_prices_tenths: dict[int, int] = Field(default_factory=dict)
    target_player_name: str | None = None
    risk_preference: RiskPreference = RiskPreference.BALANCED
    horizon_gameweeks: int | None = None
    maximum_points_hit: int | None = None
    protected_player_ids: tuple[int, ...] = ()
    history: ConversationHistory = Field(default_factory=ConversationHistory)
