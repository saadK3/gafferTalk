import { describe, expect, it } from "vitest";
import type { ApiPlayer, Recommendation } from "./current-team-api";
import {
  applyRecommendationToSquad,
  parseSavedRecommendationSquad,
  type SavedRecommendationSquad,
} from "./free-recommendation-state";

function player(id: number, position: ApiPlayer["position"] = "MID"): ApiPlayer {
  return {
    id,
    web_name: `Player ${id}`,
    club: { id, name: `Club ${id}`, short_name: `C${id}` },
    position,
    current_price: { tenths: 50 },
    status: "a",
    chance_of_playing_next_round: null,
    news: "",
  };
}

function state(): SavedRecommendationSquad {
  const players = Array.from({ length: 15 }, (_, index) => player(index + 1));
  return {
    squad: {
      name: "Test squad",
      player_ids: players.map((item) => item.id),
      squad_positions: Object.fromEntries(players.map((item, index) => [item.id, index + 1])),
      bank_tenths: 10,
      free_transfers: 1,
    },
    players,
  };
}

function recommendation(incoming = player(99)): Recommendation {
  return {
    rank: 1,
    incoming,
    score: 80,
    score_breakdown: { historical_output: 80, upcoming_fixtures: 80, value: 80 },
    average_fixture_difficulty: 2.5,
    remaining_bank: { tenths: 5 },
    free_transfers_after: 0,
    points_hit: 0,
    reasons: ["Legal"],
    trade_off: "A trade-off",
  };
}

describe("free recommendation squad state", () => {
  it("applies a legal recommendation and preserves the outgoing squad slot", () => {
    const next = applyRecommendationToSquad(state(), 8, recommendation());

    expect(next.squad.player_ids).toHaveLength(15);
    expect(next.squad.player_ids).not.toContain(8);
    expect(next.squad.player_ids).toContain(99);
    expect(next.squad.squad_positions?.[99]).toBe(8);
    expect(next.squad.bank_tenths).toBe(5);
    expect(next.squad.free_transfers).toBe(0);
  });

  it("rejects stale, duplicate, and wrong-position recommendations", () => {
    expect(() => applyRecommendationToSquad(state(), 404, recommendation())).toThrow(/no longer/);
    expect(() => applyRecommendationToSquad(state(), 8, recommendation(player(9)))).toThrow(/already/);
    expect(() => applyRecommendationToSquad(state(), 8, recommendation(player(99, "FWD")))).toThrow(/position/);
  });

  it("ignores corrupt browser state", () => {
    expect(parseSavedRecommendationSquad("not-json")).toBeNull();
    expect(parseSavedRecommendationSquad(JSON.stringify({ squad: {}, players: [] }))).toBeNull();
  });
});
