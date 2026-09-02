import type {
  ApiPlayer,
  NamedTransferResearchResponse,
  ProDecisionReport,
  RiskPreference,
} from "./current-team-api";

export type ConfirmedWorkspaceState = {
  id: string;
  version: number;
  team_id: number;
  team_name: string;
  source_gameweek: number;
  player_ids: number[];
  players: ApiPlayer[];
  squad_positions: Record<number, number>;
  changes: Array<{ outgoing_player_id: number; incoming_player_id: number }>;
  captain_id: number;
  vice_captain_id: number;
  bank_tenths: number;
  free_transfers: number;
  risk_preference: RiskPreference;
  confirmed_at: string;
  data_retrieved_at: string;
  freshness_status: "confirmed" | "stale";
};

export type WorkspaceMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type WorkspaceReport = {
  id: string;
  version: number;
  report_type: "named_transfer";
  question: string;
  assistant_message: string;
  report: ProDecisionReport;
  provider: string;
  model: string;
  squad_state_version: number;
  created_at: string;
  data_retrieved_at: string;
};

export type ProWorkspace = {
  entitlement: "pro_beta" | "pro";
  current_state: ConfirmedWorkspaceState | null;
  messages: WorkspaceMessage[];
  reports: WorkspaceReport[];
  plans: WorkspacePlan[];
};

export type PlanLifecycle = "active" | "stale" | "completed" | "superseded" | "abandoned";
export type PlanActionKind = "commit_now" | "plan" | "watch" | "alternative";
export type PlanStaleReason =
  | "new_snapshot"
  | "outside_transfer"
  | "squad_state_changed"
  | "bank_changed"
  | "free_transfers_changed"
  | "selling_price_changed"
  | "player_unavailable"
  | "fixture_schedule_changed"
  | "deadline_passed";

export type PlanAction = {
  sequence: number;
  gameweek_id: number;
  kind: PlanActionKind;
  headline: string;
  condition: string;
  outgoing: ApiPlayer | null;
  incoming: ApiPlayer | null;
  expected_bank_after_tenths: number;
  expected_free_transfers_after: number;
};

export type PlanDraft = {
  schema_version: "1.0";
  report_id: string;
  report_version: number;
  squad_state_id: string;
  squad_state_version: number;
  horizon_gameweeks: [number, number, number];
  evidence_gameweeks: number[];
  initial_bank_tenths: number;
  initial_free_transfers: number;
  relevant_selling_price_tenths: number;
  actions: PlanAction[];
  conditions: string[];
  alternatives: string[];
  confidence: "high" | "medium" | "low";
  assumptions: string[];
  evidence: Array<{
    player: ApiPlayer;
    next_five_difficulties: number[];
    next_five_average: number | null;
  }>;
  data_retrieved_at: string;
  fixture_signature: string;
  baseline_snapshot_gameweek: number;
  baseline_public_player_ids: number[];
  current_deadline: string;
};

export type WorkspacePlan = PlanDraft & {
  id: string;
  version: number;
  lifecycle: PlanLifecycle;
  stale_reasons: PlanStaleReason[];
  created_at: string;
  updated_at: string;
  activated_at: string;
  stale_at: string | null;
  completed_at: string | null;
  superseded_at: string | null;
  abandoned_at: string | null;
};

export type PlanReconciliation = {
  plan_id: string;
  checked_at: string;
  newest_snapshot_gameweek: number;
  added_player_ids: number[];
  removed_player_ids: number[];
  stale_reasons: PlanStaleReason[];
  materially_stale: boolean;
  requires_state_confirmation: boolean;
};

export type ConfirmWorkspaceInput = Omit<ConfirmedWorkspaceState, "id" | "version" | "freshness_status">;

export class ProWorkspaceApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
  }
}

async function workspaceRequest<T>(
  path = "",
  options: { method?: "GET" | "PUT" | "POST" | "PATCH"; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/pro/workspace${path}`, {
      method: options.method ?? "GET",
      signal: options.signal,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ProWorkspaceApiError("GafferTalk could not reach your Pro workspace.", 0, "network_error");
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: { code?: string; message?: string } | string;
    } | null;
    const detail = typeof payload?.detail === "object" ? payload.detail : null;
    throw new ProWorkspaceApiError(
      detail?.message ?? "The Pro workspace request could not be completed.",
      response.status,
      detail?.code ?? "unknown_error",
    );
  }
  return response.json() as Promise<T>;
}

export function loadProWorkspace(signal?: AbortSignal): Promise<ProWorkspace> {
  return workspaceRequest("", { signal });
}

export function confirmProWorkspaceState(
  input: ConfirmWorkspaceInput,
  signal?: AbortSignal,
): Promise<ProWorkspace> {
  return workspaceRequest("/state", { method: "PUT", body: input, signal });
}

export function researchWorkspaceNamedTransfer(
  input: {
    outgoing_player_id: number;
    outgoing_selling_price_tenths: number;
    target_player_id: number;
    question: string;
  },
  signal?: AbortSignal,
): Promise<{ research: NamedTransferResearchResponse; workspace: ProWorkspace }> {
  return workspaceRequest("/research/named-transfer", { method: "POST", body: input, signal });
}

export function previewWorkspacePlan(
  reportId: string,
  signal?: AbortSignal,
): Promise<{ draft: PlanDraft }> {
  return workspaceRequest("/plans/preview", {
    method: "POST",
    body: { report_id: reportId },
    signal,
  });
}

export function saveWorkspacePlan(
  reportId: string,
  signal?: AbortSignal,
): Promise<{ plan: WorkspacePlan; workspace: ProWorkspace }> {
  return workspaceRequest("/plans", {
    method: "POST",
    body: { report_id: reportId },
    signal,
  });
}

export function reconcileWorkspacePlan(
  planId: string,
  input: {
    bank_tenths: number;
    free_transfers: number;
    relevant_selling_price_tenths: number;
  },
  signal?: AbortSignal,
): Promise<{ reconciliation: PlanReconciliation; workspace: ProWorkspace }> {
  return workspaceRequest(`/plans/${planId}/reconcile`, {
    method: "POST",
    body: input,
    signal,
  });
}

export function updateWorkspacePlanLifecycle(
  planId: string,
  lifecycle: "completed" | "abandoned",
  signal?: AbortSignal,
): Promise<ProWorkspace> {
  return workspaceRequest(`/plans/${planId}`, {
    method: "PATCH",
    body: { lifecycle },
    signal,
  });
}
