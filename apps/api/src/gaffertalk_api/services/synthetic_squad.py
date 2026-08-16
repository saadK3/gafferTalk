from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gaffertalk_api.domain.models import (
    DataProvenance,
    FplCatalogue,
    Money,
    Position,
    SquadPick,
    SquadSnapshot,
)
from gaffertalk_api.domain.transfers import TransferPlanningState

DEFAULT_SYNTHETIC_SQUAD_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "synthetic-squad.json"
)


class SyntheticPlayerSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    web_name: str
    club: str
    position: Position


class SyntheticSquadDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    bank_tenths: int = Field(ge=0)
    free_transfers: int = Field(ge=0, le=5)
    captain: str
    vice_captain: str
    players: tuple[SyntheticPlayerSelector, ...]


def load_synthetic_squad(
    path: Path, catalogue: FplCatalogue
) -> tuple[SyntheticSquadDefinition, SquadSnapshot, TransferPlanningState]:
    definition = SyntheticSquadDefinition.model_validate_json(path.read_text())
    selected = []
    for selector in definition.players:
        matches = [
            player
            for player in catalogue.players.values()
            if player.web_name == selector.web_name
            and player.club.short_name == selector.club
            and player.position is selector.position
        ]
        if len(matches) != 1:
            raise ValueError(
                f"synthetic player {selector.web_name} ({selector.club}) "
                "did not resolve uniquely in live FPL data"
            )
        selected.append(matches[0])

    gameweek = next(
        (item for item in catalogue.gameweeks if item.is_next or item.is_current),
        catalogue.gameweeks[0],
    )
    picks = tuple(
        SquadPick(
            player=player,
            squad_position=index,
            multiplier=2 if player.web_name == definition.captain else 1 if index <= 11 else 0,
            is_captain=player.web_name == definition.captain,
            is_vice_captain=player.web_name == definition.vice_captain,
        )
        for index, player in enumerate(selected, start=1)
    )
    squad_value = sum(player.current_price.tenths for player in selected)
    snapshot = SquadSnapshot(
        gameweek=gameweek,
        picks=picks,
        bank=Money(tenths=definition.bank_tenths),
        squad_value=Money(tenths=squad_value),
        event_transfers=0,
        event_transfer_cost=0,
        provenance=DataProvenance.DERIVED,
        retrieved_at=datetime.now(UTC),
    )
    state = TransferPlanningState(
        bank=Money(tenths=definition.bank_tenths),
        free_transfers=definition.free_transfers,
        selling_prices={player.id: player.current_price for player in selected},
    )
    return definition, snapshot, state
