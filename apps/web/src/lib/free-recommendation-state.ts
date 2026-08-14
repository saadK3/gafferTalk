import type {
  ApiPlayer,
  CurrentSquadRequest,
  Recommendation,
} from "./current-team-api";

export const RECOMMENDATION_STORAGE_KEY = "gaffertalk.recommendationSquad.v1";

export type SavedRecommendationSquad = {
  squad: CurrentSquadRequest;
  players: ApiPlayer[];
};

export function parseSavedRecommendationSquad(raw: string | null): SavedRecommendationSquad | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<SavedRecommendationSquad>;
    if (!value.squad || !value.players) return null;
    if (value.squad.player_ids.length !== 15 || value.players.length !== 15) return null;
    if (new Set(value.squad.player_ids).size !== 15) return null;
    if (new Set(value.players.map((player) => player.id)).size !== 15) return null;
    if (!value.squad.player_ids.every((id) => value.players?.some((player) => player.id === id))) {
      return null;
    }
    return { squad: value.squad, players: value.players };
  } catch {
    return null;
  }
}

export function applyRecommendationToSquad(
  current: SavedRecommendationSquad,
  outgoingId: number,
  recommendation: Recommendation,
): SavedRecommendationSquad {
  const outgoing = current.players.find((player) => player.id === outgoingId);
  if (!outgoing || !current.squad.player_ids.includes(outgoingId)) {
    throw new Error("The outgoing player is no longer in this squad.");
  }
  if (current.squad.player_ids.includes(recommendation.incoming.id)) {
    throw new Error("The recommended player is already in this squad.");
  }
  if (outgoing.position !== recommendation.incoming.position) {
    throw new Error("A one-player transfer must preserve the FPL position.");
  }

  const nextIds = current.squad.player_ids.map((id) =>
    id === outgoingId ? recommendation.incoming.id : id,
  );
  const nextPlayers = current.players.map((player) =>
    player.id === outgoingId ? recommendation.incoming : player,
  );
  if (nextIds.length !== 15 || new Set(nextIds).size !== 15) {
    throw new Error("The planned squad must contain 15 unique players.");
  }

  const oldPosition = current.squad.squad_positions?.[outgoingId];
  const squadPositions = current.squad.squad_positions
    ? Object.fromEntries(
        Object.entries(current.squad.squad_positions)
          .filter(([id]) => Number(id) !== outgoingId)
          .concat(oldPosition ? [[String(recommendation.incoming.id), oldPosition]] : []),
      )
    : undefined;

  return {
    squad: {
      ...current.squad,
      player_ids: nextIds,
      squad_positions: squadPositions,
      bank_tenths: recommendation.remaining_bank.tenths,
      free_transfers: recommendation.free_transfers_after,
    },
    players: nextPlayers,
  };
}
