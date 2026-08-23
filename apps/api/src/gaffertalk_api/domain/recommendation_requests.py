from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from gaffertalk_api.domain.models import DomainModel, Player
from gaffertalk_api.domain.recommendations import RecommendationResult, RecommendationStrategy


class CurrentSquadInput(DomainModel):
    name: str = Field(min_length=1, max_length=80)
    player_ids: tuple[int, ...] = Field(min_length=15, max_length=15)
    squad_positions: dict[int, int] | None = None
    bank_tenths: int = Field(ge=0, le=200)
    free_transfers: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def unique_players(self) -> "CurrentSquadInput":
        if len(set(self.player_ids)) != 15:
            raise ValueError("current squad must contain 15 unique players")
        if self.squad_positions is not None:
            if set(self.squad_positions) != set(self.player_ids):
                raise ValueError("squad positions must cover every current player")
            if set(self.squad_positions.values()) != set(range(1, 16)):
                raise ValueError("squad positions must be the unique values 1 through 15")
        return self


class TransferRecommendationRequest(DomainModel):
    squad: CurrentSquadInput
    outgoing_player_id: int = Field(gt=0)
    outgoing_selling_price_tenths: int = Field(ge=0, le=300)
    strategy: RecommendationStrategy = RecommendationStrategy.BALANCED
    target_player_id: int | None = Field(default=None, gt=0)


class NamedTransferResearchRequest(DomainModel):
    squad: CurrentSquadInput
    outgoing_player_id: int = Field(gt=0)
    outgoing_selling_price_tenths: int = Field(ge=0, le=300)
    target_player_id: int = Field(gt=0)
    question: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def players_are_different(self) -> "NamedTransferResearchRequest":
        if self.outgoing_player_id == self.target_player_id:
            raise ValueError("outgoing and target players must be different")
        return self


class OutgoingSelectionMode(StrEnum):
    SELECTED = "selected"
    AUTO = "auto"


class ConversationalRecommendationRequest(DomainModel):
    squad: CurrentSquadInput
    selection_mode: OutgoingSelectionMode = OutgoingSelectionMode.SELECTED
    outgoing_player_id: int | None = Field(default=None, gt=0)
    outgoing_selling_price_tenths: int | None = Field(default=None, ge=0, le=300)
    question: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def selected_player_is_complete(self) -> "ConversationalRecommendationRequest":
        has_player = self.outgoing_player_id is not None
        has_price = self.outgoing_selling_price_tenths is not None
        if self.selection_mode is OutgoingSelectionMode.SELECTED and not (has_player and has_price):
            raise ValueError("selected mode requires an outgoing player and selling price")
        if self.selection_mode is OutgoingSelectionMode.AUTO and (has_player or has_price):
            raise ValueError("auto mode must not include an outgoing player or selling price")
        return self


class FreeQuestionQuota(DomainModel):
    gameweek_id: int = Field(ge=1, le=38)
    gameweek_name: str = Field(min_length=1)
    deadline_time: datetime
    limit: int = Field(gt=0)
    used: int = Field(ge=0)
    remaining: int = Field(ge=0)


class ConversationOutcome(StrEnum):
    RECOMMENDATION = "recommendation"
    ALREADY_OWNED = "already_owned"
    POSITION_MISMATCH = "position_mismatch"
    TARGET_UNAVAILABLE = "target_unavailable"
    TARGET_ILLEGAL = "target_illegal"
    TARGET_NOT_FOUND = "target_not_found"
    TARGET_REQUIRED = "target_required"
    SELLING_PRICE_REQUIRED = "selling_price_required"


class ConversationalRecommendationResponse(DomainModel):
    assistant_message: str
    interpreted_outgoing_player_id: int | None
    outcome: ConversationOutcome
    target: Player | None = None
    suggested_outgoing: Player | None = None
    result: RecommendationResult | None = None
    provider: str
    model: str
    quota: FreeQuestionQuota


class DemoSquadResponse(DomainModel):
    squad: CurrentSquadInput
    players: tuple[Player, ...]
