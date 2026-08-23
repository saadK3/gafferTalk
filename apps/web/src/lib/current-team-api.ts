export type Position = "GKP" | "DEF" | "MID" | "FWD";

export type ApiMoney = { tenths: number };

export type ApiPlayer = {
  id: number;
  web_name: string;
  club: { id: number; name: string; short_name: string };
  position: Position;
  current_price: ApiMoney;
  status: string;
  chance_of_playing_next_round: number | null;
  news: string;
};

export type SquadPick = {
  player: ApiPlayer;
  squad_position: number;
  multiplier: number;
  is_captain: boolean;
  is_vice_captain: boolean;
};

export type SquadLookupResult = {
  entry: {
    id: number;
    team_name: string;
    manager_first_name: string | null;
    manager_last_name: string | null;
  };
  availability: {
    status: "available" | "not_yet_published";
    reason: string;
    next_deadline: string | null;
  };
  snapshot: null | {
    gameweek: { id: number; name: string; deadline_time: string };
    picks: SquadPick[];
    bank: ApiMoney | null;
    squad_value: ApiMoney | null;
    retrieved_at: string;
  };
  retrieved_at: string;
};

export class CurrentTeamApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly detail?: unknown,
  ) {
    super(message);
  }
}

function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, { signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new CurrentTeamApiError("GafferTalk could not reach the team service. Try again shortly.", 0, "network_error");
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: { code?: string; message?: string } } | null;
    throw new CurrentTeamApiError(
      payload?.detail?.message ?? "The team service could not complete that request.",
      response.status,
      payload?.detail?.code ?? "unknown_error",
      payload?.detail,
    );
  }
  return response.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal, headers?: HeadersInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method: "POST",
      signal,
      headers: { Accept: "application/json", "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new CurrentTeamApiError("GafferTalk could not reach the recommendation service.", 0, "network_error");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: { code?: string; message?: string } } | null;
    throw new CurrentTeamApiError(payload?.detail?.message ?? "The recommendation could not be completed.", response.status, payload?.detail?.code ?? "unknown_error", payload?.detail);
  }
  return response.json() as Promise<T>;
}

export function loadSquad(teamId: string, signal?: AbortSignal): Promise<SquadLookupResult> {
  return request<SquadLookupResult>(`/v1/entries/${encodeURIComponent(teamId)}/squad`, signal);
}

export async function searchPlayers(position: Position, query: string, signal?: AbortSignal): Promise<ApiPlayer[]> {
  const params = new URLSearchParams({ position, query });
  const result = await request<{ players: ApiPlayer[] }>(`/v1/players?${params}`, signal);
  return result.players;
}

export type Recommendation = {
  rank: number;
  incoming: ApiPlayer;
  score: number;
  score_breakdown: { historical_output: number; upcoming_fixtures: number; value: number };
  average_fixture_difficulty: number | null;
  remaining_bank: ApiMoney;
  free_transfers_after: number;
  points_hit: number;
  reasons: string[];
  trade_off: string;
};

export type RecommendationStrategy = "balanced" | "fixture_first" | "value_first";

export type RecommendationResult = {
  squad_name: string;
  data_retrieved_at: string;
  outgoing: ApiPlayer;
  strategy: RecommendationStrategy;
  score_weights: {
    historical_output: number;
    upcoming_fixtures: number;
    value: number;
  };
  recommendations: Recommendation[];
  assumptions: string[];
};

export type CurrentSquadRequest = {
  name: string;
  player_ids: number[];
  squad_positions?: Record<number, number>;
  bank_tenths: number;
  free_transfers: number;
};

export type DemoSquad = { squad: CurrentSquadRequest; players: ApiPlayer[] };

export type FreeQuestionQuota = {
  gameweek_id: number;
  gameweek_name: string;
  deadline_time: string;
  limit: number;
  used: number;
  remaining: number;
};

export type ConversationOutcome =
  | "recommendation"
  | "already_owned"
  | "position_mismatch"
  | "target_unavailable"
  | "target_illegal"
  | "target_not_found"
  | "target_required"
  | "selling_price_required";

export type ConversationResponse = {
  assistant_message: string;
  outcome: ConversationOutcome;
  target: ApiPlayer | null;
  suggested_outgoing: ApiPlayer | null;
  result: RecommendationResult | null;
  provider: string;
  model: string;
  quota: FreeQuestionQuota;
};

export function loadDemoSquad(signal?: AbortSignal): Promise<DemoSquad> {
  return request<DemoSquad>("/v1/demo/squad", signal);
}

export function recommendTransfer(input: { squad: CurrentSquadRequest; outgoing_player_id: number; outgoing_selling_price_tenths: number; strategy?: RecommendationStrategy }, signal?: AbortSignal): Promise<RecommendationResult> {
  return post<RecommendationResult>("/v1/recommendations/transfers", input, signal);
}

export function loadFreeUsage(clientId: string, signal?: AbortSignal): Promise<FreeQuestionQuota> {
  return requestWithHeaders<FreeQuestionQuota>("/v1/free/usage", { "X-GafferTalk-Client-ID": clientId }, signal);
}

async function requestWithHeaders<T>(path: string, headers: HeadersInit, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, { signal, headers: { Accept: "application/json", ...headers } });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new CurrentTeamApiError("GafferTalk could not reach the recommendation service.", 0, "network_error");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: { code?: string; message?: string } } | null;
    throw new CurrentTeamApiError(payload?.detail?.message ?? "Free usage could not be loaded.", response.status, payload?.detail?.code ?? "unknown_error", payload?.detail);
  }
  return response.json() as Promise<T>;
}

export type ConversationRequest =
  | { squad: CurrentSquadRequest; selection_mode: "selected"; outgoing_player_id: number; outgoing_selling_price_tenths: number; question: string }
  | { squad: CurrentSquadRequest; selection_mode: "auto"; question: string };

export function askGafferTalk(input: ConversationRequest, clientId: string, signal?: AbortSignal): Promise<ConversationResponse> {
  return post("/v1/recommendations/conversation", input, signal, { "X-GafferTalk-Client-ID": clientId });
}

export type ProVerdict = "buy" | "hold" | "wait" | "avoid";

export type ProEvidenceMetric = {
  key: string;
  label: string;
  value: number;
  display_value: string;
  provenance: "observed" | "derived" | "user_supplied" | "unavailable";
  source: string;
};

export type ProPlayerEvidence = {
  player: ApiPlayer;
  metrics: ProEvidenceMetric[];
  next_five: {
    difficulties: number[];
    average_difficulty: number | null;
    fixtures_considered: number;
  };
  next_three: {
    difficulties: number[];
    average_difficulty: number | null;
    fixtures_considered: number;
  };
  recent_gameweeks: number[];
  evidence_score: number;
  source_retrieved_at: string;
};

export type ProDecisionReport = {
  schema_version: "1.0";
  squad_name: string;
  created_at: string;
  data_retrieved_at: string;
  verdict: ProVerdict;
  recommended_action: string;
  compared_actions: Array<"requested_transfer" | "hold" | "wait" | "alternative_transfer">;
  requested_route: {
    outgoing: ApiPlayer;
    incoming: ApiPlayer;
    remaining_bank: ApiMoney;
    free_transfers_after: number;
    points_hit: number;
  };
  case_for: string[];
  case_against: string[];
  best_alternative: {
    action: "requested_transfer" | "hold" | "wait" | "alternative_transfer";
    player: ApiPlayer | null;
    explanation: string;
  };
  squad_priority: {
    more_urgent: boolean;
    player: ApiPlayer | null;
    explanation: string;
  };
  opportunity_cost: {
    free_transfers_used: number;
    points_hit: number;
    remaining_bank: ApiMoney;
    flexibility: "strong" | "moderate" | "limited";
    explanation: string;
  };
  planning_impact: string;
  confidence: {
    level: "high" | "medium" | "low";
    policy_version: "1.0";
    reasons: string[];
  };
  change_conditions: string[];
  evidence: ProPlayerEvidence[];
  assumptions: string[];
};

export type NamedTransferResearchResponse = {
  report: ProDecisionReport;
  assistant_message: string;
  provider: string;
  model: string;
};

export function researchNamedTransfer(
  input: {
    squad: CurrentSquadRequest;
    outgoing_player_id: number;
    outgoing_selling_price_tenths: number;
    target_player_id: number;
    question: string;
  },
  signal?: AbortSignal,
): Promise<NamedTransferResearchResponse> {
  return post("/v1/pro/research/named-transfer", input, signal);
}

export type RiskPreference = "safe" | "balanced" | "aggressive";

export type SquadActionCandidate = {
  action: "transfer" | "roll";
  outgoing: ApiPlayer | null;
  incoming: ApiPlayer | null;
  evidence_gain: number;
  policy_adjusted_gain: number;
  remaining_bank: ApiMoney;
  free_transfers_used: number;
  free_transfers_after: number;
  points_hit: number;
  budget_status: "optimistic" | "exact" | "not_applicable";
  explanation: string;
};

export type SquadActionReport = {
  schema_version: "1.0";
  decision_policy_version: "1.0";
  squad_name: string;
  created_at: string;
  data_retrieved_at: string;
  risk_preference: RiskPreference;
  status: "needs_selling_price" | "transfer" | "roll" | "insufficient_gain";
  recommended_action: SquadActionCandidate | null;
  provisional_action: SquadActionCandidate | null;
  requested_selling_price_for: ApiPlayer | null;
  ranked_concerns: Array<{
    rank: number;
    player: ApiPlayer;
    kind: "availability" | "minutes" | "upgrade" | "bench_reliance";
    priority_score: number;
    starting_slot: boolean;
    explanation: string;
  }>;
  compared_actions: SquadActionCandidate[];
  roll_threshold: number;
  priority_explanation: string;
  hit_analysis: {
    points_hit: number;
    justified: boolean;
    transfer_adjusted_gain: number;
    required_gain: number;
    comparison: string;
  };
  planning_impact: string;
  confidence: {
    level: "high" | "medium" | "low";
    policy_version: "1.0";
    reasons: string[];
  };
  change_conditions: string[];
  evidence: ProPlayerEvidence[];
  assumptions: string[];
};

export type SquadActionResearchResponse = {
  report: SquadActionReport;
  assistant_message: string;
  provider: string;
  model: string;
};

export function researchSquadAction(
  input: {
    squad: CurrentSquadRequest;
    selling_prices_tenths: Record<number, number>;
    risk_preference: RiskPreference;
    question: string;
  },
  signal?: AbortSignal,
): Promise<SquadActionResearchResponse> {
  return post("/v1/pro/research/squad-action", input, signal);
}

export type RouteTransfer = {
  outgoing: ApiPlayer;
  incoming: ApiPlayer;
  confirmed_selling_price: ApiMoney | null;
};

export type TransferRouteCandidate = {
  transfers: RouteTransfer[];
  budget_status: "optimistic" | "exact";
  evidence_gain: number;
  policy_adjusted_gain: number;
  remaining_bank: ApiMoney;
  free_transfers_used: number;
  free_transfers_after: number;
  points_hit: number;
  resulting_player_ids: number[];
  explanation: string;
};

export type RouteResearchReport = {
  schema_version: "1.0";
  decision_policy_version: "1.0";
  squad_name: string;
  created_at: string;
  data_retrieved_at: string;
  risk_preference: RiskPreference;
  target: ApiPlayer;
  constraints: {
    preserved_players: ApiPlayer[];
    excluded_players: ApiPlayer[];
    minimum_remaining_bank: ApiMoney;
    maximum_transfers: 1 | 2;
  };
  status: "needs_selling_prices" | "route" | "no_legal_route";
  verdict: "recommended" | "discouraged" | "no_route";
  manager_override: boolean;
  recommended_route: TransferRouteCandidate | null;
  provisional_route: TransferRouteCandidate | null;
  requested_selling_prices_for: ApiPlayer[];
  alternatives: TransferRouteCandidate[];
  strategic_explanation: string;
  opportunity_cost: string;
  confidence: {
    level: "high" | "medium" | "low";
    policy_version: "1.0";
    reasons: string[];
  };
  evidence: ProPlayerEvidence[];
  assumptions: string[];
  search_stats: {
    routes_examined: number;
    optimistic_routes: number;
    candidate_limit_per_position: number;
    elapsed_milliseconds: number;
  };
};

export type RouteResearchResponse = {
  report: RouteResearchReport;
  assistant_message: string;
  provider: string;
  model: string;
};

export function researchRoute(
  input: {
    squad: CurrentSquadRequest;
    target_player_id: number;
    preserved_player_ids: number[];
    excluded_player_ids: number[];
    minimum_remaining_bank_tenths: number;
    maximum_transfers: 1 | 2;
    selling_prices_tenths: Record<number, number>;
    risk_preference: RiskPreference;
    proceed_if_discouraged: boolean;
    question: string;
  },
  signal?: AbortSignal,
): Promise<RouteResearchResponse> {
  return post("/v1/pro/research/route", input, signal);
}
