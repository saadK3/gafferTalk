from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    create_engine,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.pool import StaticPool

from gaffertalk_api.domain.models import Player
from gaffertalk_api.domain.pro_plans import (
    MATERIAL_STATE_REASONS,
    PlanDraft,
    PlanLifecycle,
    PlanLifecycleUpdate,
    PlanReconciliation,
    PlanStaleReason,
    WorkspacePlan,
)
from gaffertalk_api.domain.pro_research import NamedTransferResearchResponse, ProDecisionReport
from gaffertalk_api.domain.pro_workspace import (
    ConfirmedPlanningState,
    ConfirmedPlanningStateInput,
    ProWorkspace,
    WorkspaceMessage,
    WorkspaceReport,
    WorkspaceRiskPreference,
)
from gaffertalk_api.domain.recommendation_requests import CurrentSquadInput

metadata = MetaData()

accounts = Table(
    "accounts",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("entitlement", String(32), nullable=False, server_default="pro_beta"),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

workspaces = Table(
    "pro_workspaces",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("current_squad_state_id", Uuid(as_uuid=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("account_id"),
)

squad_states = Table(
    "squad_state_versions",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "workspace_id",
        Uuid(as_uuid=True),
        ForeignKey("pro_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("version", Integer, nullable=False),
    Column("team_id", Integer, nullable=False),
    Column("team_name", String(80), nullable=False),
    Column("source_gameweek", Integer, nullable=False),
    Column("player_ids", JSON, nullable=False),
    Column("players", JSON, nullable=False),
    Column("squad_positions", JSON, nullable=False),
    Column("changes", JSON, nullable=False),
    Column("captain_id", Integer, nullable=False),
    Column("vice_captain_id", Integer, nullable=False),
    Column("bank_tenths", Integer, nullable=False),
    Column("free_transfers", Integer, nullable=False),
    Column("risk_preference", String(16), nullable=False),
    Column("confirmed_at", DateTime(timezone=True), nullable=False),
    Column("data_retrieved_at", DateTime(timezone=True), nullable=False),
    Column("freshness_status", String(24), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("workspace_id", "version"),
)

conversations = Table(
    "conversations",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "workspace_id",
        Uuid(as_uuid=True),
        ForeignKey("pro_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("title", String(120), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("workspace_id"),
)

messages = Table(
    "workspace_messages",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "conversation_id",
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("sequence", Integer, nullable=False),
    Column("role", String(16), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("conversation_id", "sequence"),
)

reports = Table(
    "decision_reports",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "conversation_id",
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "squad_state_id", Uuid(as_uuid=True), ForeignKey("squad_state_versions.id"), nullable=False
    ),
    Column("version", Integer, nullable=False),
    Column("report_type", String(40), nullable=False),
    Column("question", Text, nullable=False),
    Column("assistant_message", Text, nullable=False),
    Column("report_data", JSON, nullable=False),
    Column("provider", String(40), nullable=False),
    Column("model", String(100), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("data_retrieved_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("conversation_id", "version"),
)

plans = Table(
    "workspace_plans",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "workspace_id",
        Uuid(as_uuid=True),
        ForeignKey("pro_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("report_id", Uuid(as_uuid=True), ForeignKey("decision_reports.id"), nullable=False),
    Column(
        "squad_state_id",
        Uuid(as_uuid=True),
        ForeignKey("squad_state_versions.id"),
        nullable=False,
    ),
    Column("version", Integer, nullable=False),
    Column("lifecycle", String(24), nullable=False),
    Column("plan_data", JSON, nullable=False),
    Column("stale_reasons", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("activated_at", DateTime(timezone=True), nullable=False),
    Column("stale_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("superseded_at", DateTime(timezone=True), nullable=True),
    Column("abandoned_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("workspace_id", "version"),
)


class WorkspaceNotConfiguredError(RuntimeError):
    pass


class WorkspaceStateRequiredError(ValueError):
    pass


class WorkspaceStateStaleError(ValueError):
    pass


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class ProWorkspaceStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def from_url(cls, database_url: str) -> "ProWorkspaceStore":
        engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
        return cls(engine)

    @classmethod
    def in_memory(cls) -> "ProWorkspaceStore":
        engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        metadata.create_all(engine)
        return cls(engine)

    def close(self) -> None:
        self.engine.dispose()

    def save_confirmed_state(
        self,
        account_id: UUID,
        state: ConfirmedPlanningStateInput,
    ) -> ProWorkspace:
        now = datetime.now(UTC)
        account_key = account_id
        with self.engine.begin() as connection:
            account = connection.execute(
                select(accounts.c.id).where(accounts.c.id == account_key)
            ).first()
            if account is None:
                connection.execute(
                    insert(accounts).values(
                        id=account_key,
                        entitlement="pro_beta",
                        created_at=now,
                    )
                )
            workspace = connection.execute(
                select(workspaces.c.id).where(workspaces.c.account_id == account_key)
            ).first()
            if workspace is None:
                workspace_id = uuid4()
                connection.execute(
                    insert(workspaces).values(
                        id=workspace_id,
                        account_id=account_key,
                        current_squad_state_id=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                workspace_id = cast(UUID, workspace.id)
            current_version = connection.scalar(
                select(func.max(squad_states.c.version)).where(
                    squad_states.c.workspace_id == workspace_id
                )
            )
            state_id = uuid4()
            connection.execute(
                insert(squad_states).values(
                    id=state_id,
                    workspace_id=workspace_id,
                    version=int(current_version or 0) + 1,
                    team_id=state.team_id,
                    team_name=state.team_name,
                    source_gameweek=state.source_gameweek,
                    player_ids=list(state.player_ids),
                    players=[player.model_dump(mode="json") for player in state.players],
                    squad_positions={
                        str(key): value for key, value in state.squad_positions.items()
                    },
                    changes=list(state.changes),
                    captain_id=state.captain_id,
                    vice_captain_id=state.vice_captain_id,
                    bank_tenths=state.bank_tenths,
                    free_transfers=state.free_transfers,
                    risk_preference=state.risk_preference.value,
                    confirmed_at=state.confirmed_at,
                    data_retrieved_at=state.data_retrieved_at,
                    freshness_status="confirmed",
                    created_at=now,
                )
            )
            connection.execute(
                update(workspaces)
                .where(
                    workspaces.c.id == workspace_id,
                    workspaces.c.account_id == account_key,
                )
                .values(current_squad_state_id=state_id, updated_at=now)
            )
            connection.execute(
                update(plans)
                .where(
                    plans.c.workspace_id == workspace_id,
                    plans.c.lifecycle == PlanLifecycle.ACTIVE.value,
                )
                .values(
                    lifecycle=PlanLifecycle.STALE.value,
                    stale_reasons=[PlanStaleReason.SQUAD_STATE_CHANGED.value],
                    stale_at=now,
                    updated_at=now,
                )
            )
            conversation = connection.execute(
                select(conversations.c.id).where(conversations.c.workspace_id == workspace_id)
            ).first()
            if conversation is None:
                connection.execute(
                    insert(conversations).values(
                        id=uuid4(),
                        workspace_id=workspace_id,
                        title="Pro research",
                        created_at=now,
                        updated_at=now,
                    )
                )
        return self.get(account_id)

    def current_squad(self, account_id: UUID) -> tuple[UUID, CurrentSquadInput]:
        row = self._current_state_row(account_id)
        if row is None:
            raise WorkspaceStateRequiredError("Confirm your current squad before running research.")
        if str(row["freshness_status"]) == "stale":
            raise WorkspaceStateStaleError(
                "Your saved squad state is materially stale. Reconcile and reconfirm it before "
                "running new research."
            )
        positions = {
            int(key): int(value) for key, value in _mapping(row["squad_positions"]).items()
        }
        return UUID(str(row["id"])), CurrentSquadInput(
            name=str(row["team_name"]),
            player_ids=tuple(int(value) for value in _sequence(row["player_ids"])),
            squad_positions=positions,
            bank_tenths=int(row["bank_tenths"]),
            free_transfers=int(row["free_transfers"]),
        )

    def save_named_transfer_report(
        self,
        account_id: UUID,
        squad_state_id: UUID,
        question: str,
        response: NamedTransferResearchResponse,
    ) -> ProWorkspace:
        now = datetime.now(UTC)
        account_key = account_id
        with self.engine.begin() as connection:
            context = (
                connection.execute(
                    select(
                        workspaces.c.id.label("workspace_id"),
                        conversations.c.id.label("conversation_id"),
                    )
                    .select_from(
                        workspaces.join(
                            conversations,
                            conversations.c.workspace_id == workspaces.c.id,
                        ).join(
                            squad_states,
                            squad_states.c.workspace_id == workspaces.c.id,
                        )
                    )
                    .where(
                        workspaces.c.account_id == account_key,
                        squad_states.c.id == squad_state_id,
                        workspaces.c.current_squad_state_id == squad_states.c.id,
                    )
                )
                .mappings()
                .first()
            )
            if context is None:
                raise WorkspaceStateRequiredError(
                    "The confirmed squad changed before this report could be saved."
                )
            conversation_id = cast(UUID, context["conversation_id"])
            report_version = connection.scalar(
                select(func.max(reports.c.version)).where(
                    reports.c.conversation_id == conversation_id
                )
            )
            message_sequence = connection.scalar(
                select(func.max(messages.c.sequence)).where(
                    messages.c.conversation_id == conversation_id
                )
            )
            first_sequence = int(message_sequence or 0) + 1
            connection.execute(
                insert(messages),
                [
                    {
                        "id": uuid4(),
                        "conversation_id": conversation_id,
                        "sequence": first_sequence,
                        "role": "user",
                        "content": question,
                        "created_at": now,
                    },
                    {
                        "id": uuid4(),
                        "conversation_id": conversation_id,
                        "sequence": first_sequence + 1,
                        "role": "assistant",
                        "content": response.assistant_message,
                        "created_at": now,
                    },
                ],
            )
            connection.execute(
                insert(reports).values(
                    id=uuid4(),
                    conversation_id=conversation_id,
                    squad_state_id=squad_state_id,
                    version=int(report_version or 0) + 1,
                    report_type="named_transfer",
                    question=question,
                    assistant_message=response.assistant_message,
                    report_data=response.report.model_dump(mode="json"),
                    provider=response.provider,
                    model=response.model,
                    created_at=response.report.created_at,
                    data_retrieved_at=response.report.data_retrieved_at,
                )
            )
            connection.execute(
                update(conversations)
                .where(conversations.c.id == conversation_id)
                .values(updated_at=now)
            )
        return self.get(account_id)

    def plan_context(
        self, account_id: UUID, report_id: UUID
    ) -> tuple[WorkspaceReport, ConfirmedPlanningState]:
        workspace = self.get(account_id)
        if workspace.current_state is None:
            raise WorkspaceStateRequiredError("Confirm your current squad before building a plan.")
        report = next((item for item in workspace.reports if item.id == report_id), None)
        if report is None:
            raise ValueError("The selected report does not belong to this workspace.")
        if report.squad_state_version != workspace.current_state.version:
            raise WorkspaceStateStaleError(
                "The selected report predates the current squad. Run fresh research first."
            )
        return report, workspace.current_state

    def save_plan(self, account_id: UUID, draft: PlanDraft) -> ProWorkspace:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            context = (
                connection.execute(
                    select(workspaces.c.id.label("workspace_id"))
                    .select_from(
                        workspaces.join(
                            conversations,
                            conversations.c.workspace_id == workspaces.c.id,
                        )
                        .join(reports, reports.c.conversation_id == conversations.c.id)
                        .join(squad_states, squad_states.c.id == reports.c.squad_state_id)
                    )
                    .where(
                        workspaces.c.account_id == account_id,
                        reports.c.id == draft.report_id,
                        squad_states.c.id == draft.squad_state_id,
                        workspaces.c.current_squad_state_id == squad_states.c.id,
                    )
                )
                .mappings()
                .first()
            )
            if context is None:
                raise WorkspaceStateStaleError(
                    "The report or confirmed squad changed before the plan could be saved."
                )
            workspace_id = cast(UUID, context["workspace_id"])
            connection.execute(
                update(plans)
                .where(
                    plans.c.workspace_id == workspace_id,
                    plans.c.lifecycle.in_([PlanLifecycle.ACTIVE.value, PlanLifecycle.STALE.value]),
                )
                .values(
                    lifecycle=PlanLifecycle.SUPERSEDED.value,
                    superseded_at=now,
                    updated_at=now,
                )
            )
            current_version = connection.scalar(
                select(func.max(plans.c.version)).where(plans.c.workspace_id == workspace_id)
            )
            connection.execute(
                insert(plans).values(
                    id=uuid4(),
                    workspace_id=workspace_id,
                    report_id=draft.report_id,
                    squad_state_id=draft.squad_state_id,
                    version=int(current_version or 0) + 1,
                    lifecycle=PlanLifecycle.ACTIVE.value,
                    plan_data=draft.model_dump(mode="json"),
                    stale_reasons=[],
                    created_at=now,
                    updated_at=now,
                    activated_at=now,
                    stale_at=None,
                    completed_at=None,
                    superseded_at=None,
                    abandoned_at=None,
                )
            )
        return self.get(account_id)

    def get_plan(self, account_id: UUID, plan_id: UUID) -> WorkspacePlan:
        workspace = self.get(account_id)
        plan = next((item for item in workspace.plans if item.id == plan_id), None)
        if plan is None:
            raise ValueError("The selected plan does not belong to this workspace.")
        return plan

    def apply_reconciliation(
        self,
        account_id: UUID,
        reconciliation: PlanReconciliation,
    ) -> ProWorkspace:
        now = reconciliation.checked_at
        with self.engine.begin() as connection:
            owned_plan = (
                connection.execute(
                    select(
                        plans.c.id,
                        plans.c.squad_state_id,
                        workspaces.c.current_squad_state_id,
                    )
                    .select_from(plans.join(workspaces, workspaces.c.id == plans.c.workspace_id))
                    .where(
                        workspaces.c.account_id == account_id,
                        plans.c.id == reconciliation.plan_id,
                        plans.c.lifecycle.in_(
                            [PlanLifecycle.ACTIVE.value, PlanLifecycle.STALE.value]
                        ),
                    )
                )
                .mappings()
                .first()
            )
            if owned_plan is None:
                raise ValueError("Only the current active or stale plan can be reconciled.")
            lifecycle = (
                PlanLifecycle.STALE if reconciliation.stale_reasons else PlanLifecycle.ACTIVE
            )
            connection.execute(
                update(plans)
                .where(plans.c.id == reconciliation.plan_id)
                .values(
                    lifecycle=lifecycle.value,
                    stale_reasons=[reason.value for reason in reconciliation.stale_reasons],
                    stale_at=now if reconciliation.stale_reasons else None,
                    updated_at=now,
                )
            )
            if any(reason in MATERIAL_STATE_REASONS for reason in reconciliation.stale_reasons):
                connection.execute(
                    update(squad_states)
                    .where(squad_states.c.id == owned_plan["current_squad_state_id"])
                    .values(freshness_status="stale")
                )
        return self.get(account_id)

    def update_plan_lifecycle(
        self,
        account_id: UUID,
        plan_id: UUID,
        lifecycle_update: PlanLifecycleUpdate,
    ) -> ProWorkspace:
        now = datetime.now(UTC)
        lifecycle = PlanLifecycle(lifecycle_update.lifecycle)
        timestamp_column = (
            plans.c.completed_at if lifecycle is PlanLifecycle.COMPLETED else plans.c.abandoned_at
        )
        with self.engine.begin() as connection:
            owned_plan = (
                connection.execute(
                    select(plans.c.id, plans.c.lifecycle)
                    .select_from(plans.join(workspaces, workspaces.c.id == plans.c.workspace_id))
                    .where(workspaces.c.account_id == account_id, plans.c.id == plan_id)
                )
                .mappings()
                .first()
            )
            if owned_plan is None:
                raise ValueError("The selected plan does not belong to this workspace.")
            if PlanLifecycle(str(owned_plan["lifecycle"])) not in {
                PlanLifecycle.ACTIVE,
                PlanLifecycle.STALE,
            }:
                raise ValueError("Only the current active or stale plan can change lifecycle.")
            connection.execute(
                update(plans)
                .where(plans.c.id == plan_id)
                .values(
                    lifecycle=lifecycle.value,
                    updated_at=now,
                    **{timestamp_column.name: now},
                )
            )
        return self.get(account_id)

    def get(self, account_id: UUID) -> ProWorkspace:
        account_key = account_id
        with self.engine.connect() as connection:
            account = connection.execute(
                select(accounts.c.entitlement).where(accounts.c.id == account_key)
            ).first()
            if account is None:
                return ProWorkspace(entitlement="pro_beta")
            state_row = (
                connection.execute(self._current_state_query(account_key)).mappings().first()
            )
            conversation = connection.execute(
                select(conversations.c.id)
                .select_from(
                    conversations.join(
                        workspaces,
                        workspaces.c.id == conversations.c.workspace_id,
                    )
                )
                .where(workspaces.c.account_id == account_key)
            ).first()
            message_models: tuple[WorkspaceMessage, ...] = ()
            report_models: tuple[WorkspaceReport, ...] = ()
            plan_models: tuple[WorkspacePlan, ...] = ()
            if conversation is not None:
                conversation_id = cast(UUID, conversation.id)
                message_rows = connection.execute(
                    select(messages)
                    .where(messages.c.conversation_id == conversation_id)
                    .order_by(messages.c.sequence)
                ).mappings()
                message_models = tuple(self._message_model(row) for row in message_rows)
                report_rows = connection.execute(
                    select(reports, squad_states.c.version.label("squad_state_version"))
                    .select_from(
                        reports.join(squad_states, squad_states.c.id == reports.c.squad_state_id)
                    )
                    .where(reports.c.conversation_id == conversation_id)
                    .order_by(reports.c.version.desc())
                ).mappings()
                report_models = tuple(self._report_model(row) for row in report_rows)
            workspace_row = connection.execute(
                select(workspaces.c.id).where(workspaces.c.account_id == account_key)
            ).first()
            if workspace_row is not None:
                plan_rows = connection.execute(
                    select(plans)
                    .where(plans.c.workspace_id == workspace_row.id)
                    .order_by(plans.c.version.desc())
                ).mappings()
                plan_models = tuple(self._plan_model(row) for row in plan_rows)
        return ProWorkspace(
            entitlement=str(account.entitlement),
            current_state=self._state_model(state_row) if state_row is not None else None,
            messages=message_models,
            reports=report_models,
            plans=plan_models,
        )

    def _current_state_row(self, account_id: UUID) -> RowMapping | None:
        with self.engine.connect() as connection:
            return connection.execute(self._current_state_query(account_id)).mappings().first()

    @staticmethod
    def _current_state_query(account_key: UUID) -> Any:
        return (
            select(squad_states)
            .select_from(
                workspaces.join(
                    squad_states,
                    squad_states.c.id == workspaces.c.current_squad_state_id,
                )
            )
            .where(workspaces.c.account_id == account_key)
        )

    @staticmethod
    def _state_model(row: RowMapping) -> ConfirmedPlanningState:
        return ConfirmedPlanningState(
            id=UUID(str(row["id"])),
            version=int(row["version"]),
            team_id=int(row["team_id"]),
            team_name=str(row["team_name"]),
            source_gameweek=int(row["source_gameweek"]),
            player_ids=tuple(int(value) for value in _sequence(row["player_ids"])),
            players=tuple(Player.model_validate(item) for item in _sequence(row["players"])),
            squad_positions={
                int(key): int(value) for key, value in _mapping(row["squad_positions"]).items()
            },
            changes=tuple(
                {str(key): int(value) for key, value in _mapping(item).items()}
                for item in _sequence(row["changes"])
            ),
            captain_id=int(row["captain_id"]),
            vice_captain_id=int(row["vice_captain_id"]),
            bank_tenths=int(row["bank_tenths"]),
            free_transfers=int(row["free_transfers"]),
            risk_preference=WorkspaceRiskPreference(str(row["risk_preference"])),
            confirmed_at=cast(datetime, row["confirmed_at"]),
            data_retrieved_at=cast(datetime, row["data_retrieved_at"]),
            freshness_status=str(row["freshness_status"]),
        )

    @staticmethod
    def _message_model(row: RowMapping) -> WorkspaceMessage:
        return WorkspaceMessage(
            id=UUID(str(row["id"])),
            role=str(row["role"]),
            content=str(row["content"]),
            created_at=cast(datetime, row["created_at"]),
        )

    @staticmethod
    def _report_model(row: RowMapping) -> WorkspaceReport:
        return WorkspaceReport(
            id=UUID(str(row["id"])),
            version=int(row["version"]),
            report_type=str(row["report_type"]),
            question=str(row["question"]),
            assistant_message=str(row["assistant_message"]),
            report=ProDecisionReport.model_validate(row["report_data"]),
            provider=str(row["provider"]),
            model=str(row["model"]),
            squad_state_version=int(row["squad_state_version"]),
            created_at=cast(datetime, row["created_at"]),
            data_retrieved_at=cast(datetime, row["data_retrieved_at"]),
        )

    @staticmethod
    def _plan_model(row: RowMapping) -> WorkspacePlan:
        draft = PlanDraft.model_validate(row["plan_data"])
        return WorkspacePlan(
            **draft.model_dump(),
            id=UUID(str(row["id"])),
            version=int(row["version"]),
            lifecycle=PlanLifecycle(str(row["lifecycle"])),
            stale_reasons=tuple(
                PlanStaleReason(str(reason)) for reason in _sequence(row["stale_reasons"])
            ),
            created_at=cast(datetime, row["created_at"]),
            updated_at=cast(datetime, row["updated_at"]),
            activated_at=cast(datetime, row["activated_at"]),
            stale_at=cast(datetime | None, row["stale_at"]),
            completed_at=cast(datetime | None, row["completed_at"]),
            superseded_at=cast(datetime | None, row["superseded_at"]),
            abandoned_at=cast(datetime | None, row["abandoned_at"]),
        )


def _sequence(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("persisted workspace JSON must be an array")
    return value


def _mapping(value: Any) -> dict[Any, Any]:
    if not isinstance(value, dict):
        raise ValueError("persisted workspace JSON must be an object")
    return value
