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
  options: { method?: "GET" | "PUT" | "POST"; body?: unknown; signal?: AbortSignal } = {},
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
