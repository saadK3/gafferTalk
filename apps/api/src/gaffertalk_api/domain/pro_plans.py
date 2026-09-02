from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from gaffertalk_api.domain.models import DomainModel, Player
from gaffertalk_api.domain.pro_research import ConfidenceLevel


class PlanLifecycle(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"
    ABANDONED = "abandoned"


class PlanActionKind(StrEnum):
    COMMIT_NOW = "commit_now"
    PLAN = "plan"
    WATCH = "watch"
    ALTERNATIVE = "alternative"


class PlanStaleReason(StrEnum):
    NEW_SNAPSHOT = "new_snapshot"
    OUTSIDE_TRANSFER = "outside_transfer"
    SQUAD_STATE_CHANGED = "squad_state_changed"
    BANK_CHANGED = "bank_changed"
    FREE_TRANSFERS_CHANGED = "free_transfers_changed"
    SELLING_PRICE_CHANGED = "selling_price_changed"
    PLAYER_UNAVAILABLE = "player_unavailable"
    FIXTURE_SCHEDULE_CHANGED = "fixture_schedule_changed"
    DEADLINE_PASSED = "deadline_passed"


MATERIAL_STATE_REASONS = frozenset(
    {
        PlanStaleReason.NEW_SNAPSHOT,
        PlanStaleReason.OUTSIDE_TRANSFER,
        PlanStaleReason.SQUAD_STATE_CHANGED,
        PlanStaleReason.BANK_CHANGED,
        PlanStaleReason.FREE_TRANSFERS_CHANGED,
        PlanStaleReason.SELLING_PRICE_CHANGED,
    }
)


class PlanAction(DomainModel):
    sequence: int = Field(ge=1, le=6)
    gameweek_id: int = Field(ge=1, le=38)
    kind: PlanActionKind
    headline: str = Field(min_length=1, max_length=160)
    condition: str = Field(min_length=1, max_length=500)
    outgoing: Player | None = None
    incoming: Player | None = None
    expected_bank_after_tenths: int = Field(ge=0, le=500)
    expected_free_transfers_after: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def transfer_is_complete(self) -> "PlanAction":
        has_outgoing = self.outgoing is not None
        has_incoming = self.incoming is not None
        if has_outgoing != has_incoming:
            raise ValueError("a transfer action must include both players")
        if self.kind is PlanActionKind.COMMIT_NOW and not has_outgoing:
            raise ValueError("commit_now must identify a transfer")
        return self


class PlanEvidenceSummary(DomainModel):
    player: Player
    next_five_difficulties: tuple[int, ...] = Field(max_length=5)
    next_five_average: float | None = Field(default=None, ge=1, le=5)


class PlanDraft(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    report_id: UUID
    report_version: int = Field(gt=0)
    squad_state_id: UUID
    squad_state_version: int = Field(gt=0)
    horizon_gameweeks: tuple[int, int, int]
    evidence_gameweeks: tuple[int, ...] = Field(min_length=3, max_length=5)
    initial_bank_tenths: int = Field(ge=0, le=200)
    initial_free_transfers: int = Field(ge=0, le=5)
    relevant_selling_price_tenths: int = Field(ge=0, le=300)
    actions: tuple[PlanAction, ...] = Field(min_length=3, max_length=6)
    conditions: tuple[str, ...] = Field(min_length=1)
    alternatives: tuple[str, ...] = Field(min_length=1)
    confidence: ConfidenceLevel
    assumptions: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[PlanEvidenceSummary, ...] = Field(min_length=2)
    data_retrieved_at: datetime
    fixture_signature: str = Field(min_length=64, max_length=64)
    baseline_snapshot_gameweek: int = Field(ge=1, le=38)
    baseline_public_player_ids: tuple[int, ...] = Field(min_length=15, max_length=15)
    current_deadline: datetime

    @model_validator(mode="after")
    def bounded_horizon(self) -> "PlanDraft":
        if tuple(sorted(self.horizon_gameweeks)) != self.horizon_gameweeks:
            raise ValueError("plan horizon Gameweeks must be ordered")
        if len(set(self.horizon_gameweeks)) != 3:
            raise ValueError("plan horizon must contain three Gameweeks")
        if any(action.gameweek_id not in self.horizon_gameweeks for action in self.actions):
            raise ValueError("every action must fall within the three-Gameweek horizon")
        transfers = [action for action in self.actions if action.outgoing is not None]
        current_transfers = [
            action for action in transfers if action.gameweek_id == self.horizon_gameweeks[0]
        ]
        if len(current_transfers) > 2:
            raise ValueError("the current Gameweek may contain at most two transfers")
        if len(transfers) > 3:
            raise ValueError("a plan may contain at most three planned transfers")
        for action in self.actions:
            if action.gameweek_id != self.horizon_gameweeks[0] and action.kind not in {
                PlanActionKind.PLAN,
                PlanActionKind.WATCH,
                PlanActionKind.ALTERNATIVE,
            }:
                raise ValueError("future actions must be plan, watch or alternative")
        return self


class WorkspacePlan(PlanDraft):
    id: UUID
    version: int = Field(gt=0)
    lifecycle: PlanLifecycle
    stale_reasons: tuple[PlanStaleReason, ...] = ()
    created_at: datetime
    updated_at: datetime
    activated_at: datetime
    stale_at: datetime | None = None
    completed_at: datetime | None = None
    superseded_at: datetime | None = None
    abandoned_at: datetime | None = None


class PlanEvidenceContext(DomainModel):
    retrieved_at: datetime
    horizon_gameweeks: tuple[int, int, int]
    evidence_gameweeks: tuple[int, ...] = Field(min_length=3, max_length=5)
    deadlines: dict[int, datetime]
    fixture_signature: str = Field(min_length=64, max_length=64)
    player_statuses: dict[int, str]
    player_chances: dict[int, int | None]
    public_snapshot_gameweek: int = Field(ge=1, le=38)
    public_player_ids: tuple[int, ...] = Field(min_length=15, max_length=15)


class PlanReconciliationInput(DomainModel):
    bank_tenths: int = Field(ge=0, le=200)
    free_transfers: int = Field(ge=0, le=5)
    relevant_selling_price_tenths: int = Field(ge=0, le=300)


class PlanReconciliation(DomainModel):
    plan_id: UUID
    checked_at: datetime
    newest_snapshot_gameweek: int = Field(ge=1, le=38)
    added_player_ids: tuple[int, ...] = ()
    removed_player_ids: tuple[int, ...] = ()
    stale_reasons: tuple[PlanStaleReason, ...] = ()
    materially_stale: bool
    requires_state_confirmation: bool


class PlanPreviewResponse(DomainModel):
    draft: PlanDraft


class PlanMutationResponse(DomainModel):
    plan: WorkspacePlan


class PlanLifecycleUpdate(DomainModel):
    lifecycle: Literal["completed", "abandoned"]


class PlanFromReportRequest(DomainModel):
    report_id: UUID
