from pydantic import Field, model_validator

from gaffertalk_api.domain.models import DomainModel, Player
from gaffertalk_api.domain.recommendations import RecommendationResult


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


class ConversationalRecommendationRequest(DomainModel):
    squad: CurrentSquadInput
    outgoing_player_id: int = Field(gt=0)
    outgoing_selling_price_tenths: int = Field(ge=0, le=300)
    question: str = Field(min_length=3, max_length=500)


class ConversationalRecommendationResponse(DomainModel):
    assistant_message: str
    interpreted_outgoing_player_id: int
    result: RecommendationResult
    provider: str
    model: str


class DemoSquadResponse(DomainModel):
    squad: CurrentSquadInput
    players: tuple[Player, ...]
