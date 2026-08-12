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
    );
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
