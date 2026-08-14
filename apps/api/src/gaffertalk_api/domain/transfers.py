from enum import StrEnum

from pydantic import Field, model_validator

from gaffertalk_api.domain.models import DomainModel, Money


class TransferLegalityStatus(StrEnum):
    LEGAL = "legal"
    ILLEGAL = "illegal"
    MISSING_STATE = "missing_state"
    UNSUPPORTED = "unsupported"


class TransferRejectionCode(StrEnum):
    OUTGOING_PLAYER_NOT_IN_SQUAD = "outgoing_player_not_in_squad"
    DUPLICATE_OUTGOING_PLAYER = "duplicate_outgoing_player"
    DUPLICATE_INCOMING_PLAYER = "duplicate_incoming_player"
    INCOMING_PLAYER_ALREADY_IN_SQUAD = "incoming_player_already_in_squad"
    UNKNOWN_INCOMING_PLAYER = "unknown_incoming_player"
    SQUAD_SIZE = "squad_size"
    POSITION_COMPOSITION = "position_composition"
    CLUB_LIMIT = "club_limit"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    SELLING_PRICE_ABOVE_CURRENT = "selling_price_above_current"
    MISSING_BANK = "missing_bank"
    MISSING_FREE_TRANSFERS = "missing_free_transfers"
    MISSING_SELLING_PRICE = "missing_selling_price"
    UNSUPPORTED_CHIP = "unsupported_chip"


class ProposedTransfer(DomainModel):
    outgoing_player_id: int = Field(gt=0)
    incoming_player_id: int = Field(gt=0)


class TransferPlanningState(DomainModel):
    """Current state confirmed by the manager, separate from a public snapshot."""

    bank: Money | None = None
    free_transfers: int | None = Field(default=None, ge=0)
    selling_prices: dict[int, Money] = Field(default_factory=dict)
    active_chip: str | None = None


class TransferRejection(DomainModel):
    code: TransferRejectionCode
    detail: str
    player_id: int | None = Field(default=None, gt=0)


class TransferLegalityResult(DomainModel):
    status: TransferLegalityStatus
    transfers_requested: int = Field(ge=0)
    free_transfers_used: int = Field(ge=0)
    paid_transfers: int = Field(ge=0)
    points_hit: int = Field(ge=0)
    remaining_bank: Money | None = None
    rejections: tuple[TransferRejection, ...] = ()
    assumptions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_status(self) -> "TransferLegalityResult":
        if self.status is TransferLegalityStatus.LEGAL and self.rejections:
            raise ValueError("a legal transfer result cannot include rejections")
        if self.status is not TransferLegalityStatus.LEGAL and not self.rejections:
            raise ValueError("a non-legal transfer result must explain why")
        return self
