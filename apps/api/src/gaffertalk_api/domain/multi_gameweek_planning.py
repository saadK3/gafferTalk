from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from gaffertalk_api.domain.models import DomainModel, Money, Player, SquadSnapshot
from gaffertalk_api.domain.transfers import ProposedTransfer, TransferRejection


class RollAction(DomainModel):
    """Use no transfers during a planning Gameweek."""

    kind: Literal["roll"] = "roll"


class TransferBatchAction(DomainModel):
    """Submit one or more normal transfers at one deadline."""

    kind: Literal["transfer_batch"] = "transfer_batch"
    transfers: tuple[ProposedTransfer, ...] = Field(min_length=1, max_length=15)


GameweekAction = Annotated[
    RollAction | TransferBatchAction,
    Field(discriminator="kind"),
]


class MultiGameweekPlanningState(DomainModel):
    """Manager-confirmed state at the start of the first planning Gameweek."""

    snapshot: SquadSnapshot
    bank: Money
    free_transfers: int = Field(ge=0)
    selling_prices: dict[int, Money] = Field(default_factory=dict)

    @model_validator(mode="after")
    def selling_prices_belong_to_squad(self) -> "MultiGameweekPlanningState":
        squad_ids = {pick.player.id for pick in self.snapshot.picks}
        unknown = set(self.selling_prices) - squad_ids
        if unknown:
            raise ValueError("selling prices may only be supplied for players in the squad")
        return self


class MultiGameweekRouteRequest(DomainModel):
    """A bounded, facts-only target-player route query."""

    schema_version: Literal["1.0"] = "1.0"
    state: MultiGameweekPlanningState
    target_player_id: int = Field(gt=0)
    horizon_gameweek_ids: tuple[int, ...] = Field(min_length=1, max_length=2)
    protected_player_ids: tuple[int, ...] = ()
    maximum_points_hit: int = Field(default=0, ge=0, multiple_of=4)
    minimum_remaining_bank: Money = Money(tenths=0)

    @model_validator(mode="after")
    def validate_constraints(self) -> "MultiGameweekRouteRequest":
        if tuple(sorted(self.horizon_gameweek_ids)) != self.horizon_gameweek_ids:
            raise ValueError("planning Gameweeks must be ordered")
        if len(set(self.horizon_gameweek_ids)) != len(self.horizon_gameweek_ids):
            raise ValueError("planning Gameweeks must be unique")
        if len(set(self.protected_player_ids)) != len(self.protected_player_ids):
            raise ValueError("protected players must be unique")
        squad_ids = {pick.player.id for pick in self.state.snapshot.picks}
        if not set(self.protected_player_ids).issubset(squad_ids):
            raise ValueError("protected players must belong to the confirmed squad")
        return self


class SellingPriceBasis(StrEnum):
    MANAGER_CONFIRMED = "manager_confirmed"
    CURRENT_PRICE_UPPER_BOUND = "current_price_upper_bound"


class PlannedTransfer(DomainModel):
    outgoing: Player
    incoming: Player
    selling_price_used: Money
    selling_price_basis: SellingPriceBasis
    purchase_price_used: Money


class GameweekPlanStep(DomainModel):
    gameweek_id: int = Field(ge=1, le=38)
    action: GameweekAction
    transfers: tuple[PlannedTransfer, ...] = ()
    bank_before: Money
    bank_after: Money
    free_transfers_before: int = Field(ge=0)
    free_transfers_used: int = Field(ge=0)
    free_transfers_next_gameweek: int = Field(ge=0)
    points_hit: int = Field(ge=0, multiple_of=4)
    resulting_player_ids: tuple[int, ...] = Field(min_length=15, max_length=15)

    @model_validator(mode="after")
    def action_matches_transfers(self) -> "GameweekPlanStep":
        if isinstance(self.action, RollAction):
            if self.transfers or self.free_transfers_used or self.points_hit:
                raise ValueError("a roll step cannot contain or charge for transfers")
        elif len(self.transfers) != len(self.action.transfers):
            raise ValueError("a transfer step must explain every proposed transfer")
        return self


class MultiGameweekRoute(DomainModel):
    steps: tuple[GameweekPlanStep, ...] = Field(min_length=1, max_length=2)
    target: Player
    target_arrival_gameweek_id: int = Field(ge=1, le=38)
    total_transfers: int = Field(ge=1, le=3)
    total_points_hit: int = Field(ge=0, multiple_of=4)
    remaining_bank: Money
    resulting_player_ids: tuple[int, ...] = Field(min_length=15, max_length=15)
    conditional_on_unchanged_prices: bool = True


class MultiGameweekSearchStatus(StrEnum):
    ROUTES = "routes"
    NEEDS_SELLING_PRICES = "needs_selling_prices"
    TARGET_ALREADY_OWNED = "target_already_owned"
    NO_LEGAL_ROUTE = "no_legal_route"
    NO_ROUTE_FOUND_WITHIN_BOUNDS = "no_route_found_within_bounds"


class MultiGameweekSearchBounds(DomainModel):
    maximum_gameweeks: Literal[2] = 2
    maximum_total_transfers: Literal[3] = 3
    replacements_per_outgoing_player: int = Field(gt=0)
    maximum_route_simulations: int = Field(gt=0)


class MultiGameweekSearchStats(DomainModel):
    transfer_blueprints_generated: int = Field(ge=0)
    route_simulations: int = Field(ge=0)
    valid_routes: int = Field(ge=0)
    search_truncated: bool


class MultiGameweekRouteReport(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    status: MultiGameweekSearchStatus
    target: Player
    horizon_gameweek_ids: tuple[int, ...] = Field(min_length=1, max_length=2)
    primary_route: MultiGameweekRoute | None = None
    alternatives: tuple[MultiGameweekRoute, ...] = Field(default=(), max_length=2)
    requested_selling_price_player_ids: tuple[int, ...] = ()
    rejections: tuple[TransferRejection, ...] = ()
    selection_basis: str = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    bounds: MultiGameweekSearchBounds
    stats: MultiGameweekSearchStats

    @model_validator(mode="after")
    def status_matches_payload(self) -> "MultiGameweekRouteReport":
        has_route = self.primary_route is not None
        if (
            self.status
            in {
                MultiGameweekSearchStatus.ROUTES,
                MultiGameweekSearchStatus.NEEDS_SELLING_PRICES,
            }
            and not has_route
        ):
            raise ValueError("a successful or provisional report must contain a route")
        if self.status is MultiGameweekSearchStatus.ROUTES:
            if self.requested_selling_price_player_ids:
                raise ValueError("a resolved route cannot request selling prices")
        elif self.status is MultiGameweekSearchStatus.NEEDS_SELLING_PRICES:
            if not self.requested_selling_price_player_ids:
                raise ValueError("a provisional route must request selling prices")
        elif has_route or self.alternatives or self.requested_selling_price_player_ids:
            raise ValueError("an unsuccessful report cannot contain routes or price requests")
        return self
