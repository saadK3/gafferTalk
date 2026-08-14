from datetime import UTC, datetime

from gaffertalk_api.domain.models import (
    DataProvenance,
    FplCatalogue,
    Money,
    Player,
    SquadPick,
    SquadSnapshot,
)
from gaffertalk_api.domain.recommendation_requests import (
    CurrentSquadInput,
    TransferRecommendationRequest,
)
from gaffertalk_api.domain.recommendations import RecommendationResult
from gaffertalk_api.domain.transfers import TransferPlanningState
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.fpl.mapper import map_catalogue, map_fixtures
from gaffertalk_api.services.one_player_recommendations import OnePlayerRecommendationService


class RecommendationLoader:
    """Load live FPL inputs and run one-player recommendations for a confirmed squad."""

    def __init__(self, client: FplClient) -> None:
        self._client = client

    async def recommend(self, request: TransferRecommendationRequest) -> RecommendationResult:
        bootstrap = await self._client.get_bootstrap()
        raw_fixtures = await self._client.get_fixtures()
        retrieved_at = datetime.now(UTC)
        catalogue = map_catalogue(bootstrap, retrieved_at)
        fixtures = map_fixtures(raw_fixtures)
        snapshot, state = self._build_state(
            request.squad,
            request.outgoing_player_id,
            request.outgoing_selling_price_tenths,
            catalogue,
        )
        return OnePlayerRecommendationService().recommend(
            squad_name=request.squad.name,
            snapshot=snapshot,
            catalogue=catalogue,
            fixtures=fixtures,
            state=state,
            outgoing_player_id=request.outgoing_player_id,
            strategy=request.strategy,
        )

    @staticmethod
    def _build_state(
        squad: CurrentSquadInput,
        outgoing_id: int,
        selling_price_tenths: int,
        catalogue: FplCatalogue,
    ) -> tuple[SquadSnapshot, TransferPlanningState]:
        players_by_id = catalogue.players
        try:
            players = [players_by_id[player_id] for player_id in squad.player_ids]
        except KeyError as error:
            raise ValueError(f"squad references unknown current player {error.args[0]}") from error
        if outgoing_id not in squad.player_ids:
            raise ValueError("outgoing player must be in the confirmed squad")
        if selling_price_tenths > players_by_id[outgoing_id].current_price.tenths:
            raise ValueError("selling price cannot exceed the outgoing player's current FPL price")
        gameweek = next(
            (item for item in catalogue.gameweeks if item.is_next or item.is_current),
            catalogue.gameweeks[0],
        )
        positions = squad.squad_positions
        ordered_players = (
            sorted(players, key=lambda player: positions[player.id])
            if positions is not None
            else RecommendationLoader._order_for_valid_snapshot(players)
        )
        snapshot = SquadSnapshot(
            gameweek=gameweek,
            picks=tuple(
                SquadPick(
                    player=player,
                    squad_position=index,
                    multiplier=2 if index == 1 else 1 if index <= 11 else 0,
                    is_captain=index == 1,
                    is_vice_captain=index == 2,
                )
                for index, player in enumerate(ordered_players, start=1)
            ),
            bank=Money(tenths=squad.bank_tenths),
            squad_value=Money(tenths=sum(player.current_price.tenths for player in players)),
            provenance=DataProvenance.USER_SUPPLIED,
            retrieved_at=datetime.now(UTC),
        )
        state = TransferPlanningState(
            bank=Money(tenths=squad.bank_tenths),
            free_transfers=squad.free_transfers,
            selling_prices={outgoing_id: Money(tenths=selling_price_tenths)},
        )
        return snapshot, state

    @staticmethod
    def _order_for_valid_snapshot(players: list[Player]) -> list[Player]:
        starters: list[Player] = []
        bench: list[Player] = []
        target_starters = {"GKP": 1, "DEF": 4, "MID": 4, "FWD": 2}
        used = {position: 0 for position in target_starters}
        for player in players:
            position = player.position.value
            if used[position] < target_starters[position]:
                starters.append(player)
                used[position] += 1
            else:
                bench.append(player)
        return starters + bench
