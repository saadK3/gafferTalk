from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from gaffertalk_api.domain.models import DomainModel, Player
from gaffertalk_api.domain.pro_plans import (
    PlanDraft,
    PlanReconciliation,
    WorkspacePlan,
)
from gaffertalk_api.domain.pro_research import NamedTransferResearchResponse, ProDecisionReport


class WorkspaceRiskPreference(StrEnum):
    SAFE = "safe"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class ConfirmedPlanningStateInput(DomainModel):
    team_id: int = Field(gt=0)
    team_name: str = Field(min_length=1, max_length=80)
    source_gameweek: int = Field(ge=1, le=38)
    player_ids: tuple[int, ...] = Field(min_length=15, max_length=15)
    players: tuple[Player, ...] = Field(min_length=15, max_length=15)
    squad_positions: dict[int, int]
    changes: tuple[dict[str, int], ...] = Field(default=(), max_length=15)
    captain_id: int = Field(gt=0)
    vice_captain_id: int = Field(gt=0)
    bank_tenths: int = Field(ge=0, le=200)
    free_transfers: int = Field(ge=0, le=5)
    risk_preference: WorkspaceRiskPreference = WorkspaceRiskPreference.BALANCED
    confirmed_at: datetime
    data_retrieved_at: datetime

    @model_validator(mode="after")
    def state_is_complete(self) -> "ConfirmedPlanningStateInput":
        player_ids = set(self.player_ids)
        if len(player_ids) != 15:
            raise ValueError("confirmed squad must contain 15 unique players")
        if {player.id for player in self.players} != player_ids:
            raise ValueError("normalized players must cover every confirmed player")
        if set(self.squad_positions) != player_ids:
            raise ValueError("squad positions must cover every confirmed player")
        if set(self.squad_positions.values()) != set(range(1, 16)):
            raise ValueError("squad positions must be the unique values 1 through 15")
        if self.captain_id not in player_ids or self.vice_captain_id not in player_ids:
            raise ValueError("captain and vice-captain must belong to the confirmed squad")
        if self.captain_id == self.vice_captain_id:
            raise ValueError("captain and vice-captain must be different")
        for change in self.changes:
            if set(change) != {"outgoing_player_id", "incoming_player_id"}:
                raise ValueError(
                    "every recorded change must identify outgoing and incoming players"
                )
        return self


class ConfirmedPlanningState(DomainModel):
    id: UUID
    version: int = Field(gt=0)
    team_id: int = Field(gt=0)
    team_name: str
    source_gameweek: int = Field(ge=1, le=38)
    player_ids: tuple[int, ...]
    players: tuple[Player, ...]
    squad_positions: dict[int, int]
    changes: tuple[dict[str, int], ...]
    captain_id: int
    vice_captain_id: int
    bank_tenths: int
    free_transfers: int
    risk_preference: WorkspaceRiskPreference
    confirmed_at: datetime
    data_retrieved_at: datetime
    freshness_status: str


class WorkspaceMessage(DomainModel):
    id: UUID
    role: str
    content: str
    created_at: datetime


class WorkspaceReport(DomainModel):
    id: UUID
    version: int = Field(gt=0)
    report_type: str
    question: str
    assistant_message: str
    report: ProDecisionReport
    provider: str
    model: str
    squad_state_version: int = Field(gt=0)
    created_at: datetime
    data_retrieved_at: datetime


class ProWorkspace(DomainModel):
    entitlement: str
    current_state: ConfirmedPlanningState | None = None
    messages: tuple[WorkspaceMessage, ...] = ()
    reports: tuple[WorkspaceReport, ...] = ()
    plans: tuple[WorkspacePlan, ...] = ()


class WorkspaceNamedTransferRequest(DomainModel):
    outgoing_player_id: int = Field(gt=0)
    outgoing_selling_price_tenths: int = Field(ge=0, le=300)
    target_player_id: int = Field(gt=0)
    question: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def players_are_different(self) -> "WorkspaceNamedTransferRequest":
        if self.outgoing_player_id == self.target_player_id:
            raise ValueError("outgoing and target players must be different")
        return self


class WorkspaceResearchResult(DomainModel):
    research: NamedTransferResearchResponse
    workspace: ProWorkspace


class WorkspacePlanPreviewResult(DomainModel):
    draft: PlanDraft


class WorkspacePlanMutationResult(DomainModel):
    plan: WorkspacePlan
    workspace: ProWorkspace


class WorkspaceReconciliationResult(DomainModel):
    reconciliation: PlanReconciliation
    workspace: ProWorkspace
