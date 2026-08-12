import type { Position } from "./current-team-api";

export type SquadSlot = {
  id: number;
  position: Position;
  group: "starter" | "bench";
};

export type RecordedChange = {
  outgoingPlayerId: number;
  incomingPlayerId: number;
  incomingPosition: Position;
};

export type ConfirmedCurrentTeam = {
  version: 1;
  teamId: number;
  sourceGameweek: number;
  playerIds: number[];
  changes: Array<{ outgoingPlayerId: number; incomingPlayerId: number }>;
  captainId: number;
  viceCaptainId: number;
  bankTenths: number;
  freeTransfers: number;
  confirmedAt: string;
  provenance: {
    squad: "observed_and_user_confirmed";
    bank: "user_supplied";
    freeTransfers: "user_supplied";
    captaincy: "user_supplied";
  };
};

export function applyRecordedChanges(squad: SquadSlot[], changes: RecordedChange[]): SquadSlot[] {
  const outgoingIds = new Set<number>();
  const incomingIds = new Set<number>();
  const sourceIds = new Set(squad.map((player) => player.id));

  for (const change of changes) {
    if (outgoingIds.has(change.outgoingPlayerId) || incomingIds.has(change.incomingPlayerId)) {
      throw new Error("Each player can appear in only one recorded change.");
    }
    const outgoing = squad.find((player) => player.id === change.outgoingPlayerId);
    if (!outgoing || sourceIds.has(change.incomingPlayerId)) throw new Error("Recorded change references an invalid player.");
    if (outgoing.position !== change.incomingPosition) throw new Error("Recorded changes must preserve position.");
    outgoingIds.add(change.outgoingPlayerId);
    incomingIds.add(change.incomingPlayerId);
  }

  return squad.map((player) => {
    const change = changes.find((item) => item.outgoingPlayerId === player.id);
    return change ? { ...player, id: change.incomingPlayerId } : player;
  });
}

export function assignLeadership(captainId: number, viceCaptainId: number, role: "captain" | "vice", playerId: number): [number, number] {
  if (role === "captain") return playerId === viceCaptainId ? [playerId, captainId] : [playerId, viceCaptainId];
  return playerId === captainId ? [viceCaptainId, playerId] : [captainId, playerId];
}

export function buildConfirmedCurrentTeam(input: Omit<ConfirmedCurrentTeam, "version" | "provenance">): ConfirmedCurrentTeam {
  if (input.playerIds.length !== 15 || new Set(input.playerIds).size !== 15) throw new Error("Current squad must contain 15 unique players.");
  if (!input.playerIds.includes(input.captainId) || !input.playerIds.includes(input.viceCaptainId) || input.captainId === input.viceCaptainId) throw new Error("Captain and vice-captain must be different current squad players.");
  if (!Number.isInteger(input.bankTenths) || input.bankTenths < 0 || input.bankTenths > 200) throw new Error("Bank must be between £0.0m and £20.0m.");
  if (!Number.isInteger(input.freeTransfers) || input.freeTransfers < 0 || input.freeTransfers > 5) throw new Error("Free transfers must be between 0 and 5.");
  return { ...input, version: 1, provenance: { squad: "observed_and_user_confirmed", bank: "user_supplied", freeTransfers: "user_supplied", captaincy: "user_supplied" } };
}
