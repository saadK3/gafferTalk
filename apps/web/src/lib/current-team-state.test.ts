import { describe, expect, it } from "vitest";
import { applyRecordedChanges, assignLeadership, buildConfirmedCurrentTeam } from "./current-team-state";

const squad = Array.from({ length: 15 }, (_, index) => ({ id: index + 1, position: (index < 2 ? "GKP" : index < 7 ? "DEF" : index < 12 ? "MID" : "FWD") as "GKP" | "DEF" | "MID" | "FWD", group: index < 11 ? "starter" as const : "bench" as const }));

describe("current team state", () => {
  it("applies recorded changes without mutating the source squad", () => {
    const result = applyRecordedChanges(squad, [{ outgoingPlayerId: 8, incomingPlayerId: 108, incomingPosition: "MID" }]);
    expect(result).not.toBe(squad);
    expect(result.map((player) => player.id)).toContain(108);
    expect(squad.map((player) => player.id)).toContain(8);
  });

  it("rejects a recorded replacement in a different position", () => {
    expect(() => applyRecordedChanges(squad, [{ outgoingPlayerId: 8, incomingPlayerId: 108, incomingPosition: "FWD" }])).toThrow(/preserve position/);
  });

  it("swaps captaincy roles instead of duplicating them", () => {
    expect(assignLeadership(8, 9, "captain", 9)).toEqual([9, 8]);
    expect(assignLeadership(8, 9, "vice", 8)).toEqual([9, 8]);
  });

  it("builds a versioned state with explicit provenance", () => {
    const result = buildConfirmedCurrentTeam({ teamId: 123, sourceGameweek: 1, playerIds: squad.map((player) => player.id), changes: [], captainId: 8, viceCaptainId: 9, bankTenths: 15, freeTransfers: 1, confirmedAt: "2026-08-22T00:00:00Z" });
    expect(result.version).toBe(1);
    expect(result.provenance.bank).toBe("user_supplied");
  });

  it("rejects duplicate players and invalid leadership", () => {
    expect(() => buildConfirmedCurrentTeam({ teamId: 123, sourceGameweek: 1, playerIds: Array(15).fill(1), changes: [], captainId: 1, viceCaptainId: 1, bankTenths: 0, freeTransfers: 1, confirmedAt: "2026-08-22T00:00:00Z" })).toThrow(/15 unique/);
  });
});
