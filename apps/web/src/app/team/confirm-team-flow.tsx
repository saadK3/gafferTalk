"use client";

import type { CSSProperties, FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  CurrentTeamApiError,
  loadSquad,
  searchPlayers,
  type ApiPlayer,
  type Position,
  type SquadLookupResult,
} from "@/lib/current-team-api";
import { assignLeadership, buildConfirmedCurrentTeam } from "@/lib/current-team-state";
import styles from "./confirm-team.module.css";

type Player = {
  id: number;
  name: string;
  clubId: number;
  club: string;
  position: Position;
  price: number;
  kit: string;
  kitSecondary?: string;
  group: "starter" | "bench";
};

type Change = { outgoing: Player; incoming: Player };
type Stage = "lookup" | "confirm" | "review" | "ready";
type LeadershipRole = "captain" | "vice";

type LoadedTeam = {
  result: SquadLookupResult;
  squad: Player[];
  captainId: number;
  viceCaptainId: number;
};

const clubPalette: Record<string, [string, string?]> = {
  ARS: ["#d82946", "#ffffff"], AVL: ["#7b2648", "#82c8e5"], BOU: ["#d82946", "#101d2a"],
  CHE: ["#1646a0"], CRY: ["#d82946", "#1646a0"], EVE: ["#2354a5"], MCI: ["#74b9df"],
  MUN: ["#d51f35"], NEW: ["#f7f5ee", "#101d2a"], TOT: ["#f7f5ee", "#101d2a"], WHU: ["#7b2648", "#82c8e5"],
};

const positionNames: Record<Position, string> = {
  GKP: "Goalkeeper",
  DEF: "Defenders",
  MID: "Midfielders",
  FWD: "Forwards",
};

function money(value: number) { return `£${value.toFixed(1)}m`; }

function toPlayer(player: ApiPlayer, group: Player["group"] = "starter"): Player {
  const [kit, kitSecondary] = clubPalette[player.club.short_name] ?? ["#168594", "#0c2030"];
  return { id: player.id, name: player.web_name, clubId: player.club.id, club: player.club.short_name, position: player.position, price: player.current_price.tenths / 10, kit, kitSecondary, group };
}

function mapLoadedTeam(result: SquadLookupResult): LoadedTeam | null {
  if (!result.snapshot) return null;
  const captain = result.snapshot.picks.find((pick) => pick.is_captain);
  const viceCaptain = result.snapshot.picks.find((pick) => pick.is_vice_captain);
  if (!captain || !viceCaptain || result.snapshot.picks.length !== 15) return null;
  return {
    result,
    squad: result.snapshot.picks.map((pick) => toPlayer(pick.player, pick.squad_position <= 11 ? "starter" : "bench")),
    captainId: captain.player.id,
    viceCaptainId: viceCaptain.player.id,
  };
}

function formatDeadline(value: string): string {
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC", timeZoneName: "short" }).format(new Date(value));
}

function Shirt({ primary, secondary }: { primary: string; secondary?: string }) {
  return (
    <span className={styles.shirt} style={{ "--kit-primary": primary, "--kit-secondary": secondary ?? primary } as CSSProperties} aria-hidden="true" />
  );
}

function Header({ stage }: { stage: Stage }) {
  const step = stage === "lookup" ? 1 : stage === "confirm" ? 2 : 3;
  const label = stage === "lookup" ? "Load your team" : stage === "confirm" ? "Confirm your team" : stage === "review" ? "Review your state" : "Team ready";
  return (
    <header className={styles.header}>
      <Link className={styles.wordmark} href="/" aria-label="GafferTalk home">GafferTalk<span>.</span></Link>
      <div className={styles.progress} aria-label={`Step ${step} of 3`}>
        <span>0{step}</span>
        <div className={styles.progressTrack}><i style={{ width: `${step * 33.333}%` }} /></div>
        <p><strong>{label}</strong><small>Step {step} of 3</small></p>
      </div>
      <span className={styles.season}>26/27 · GW2 PLANNING</span>
    </header>
  );
}

function PlayerRow({ player, onChange, benchNumber, change, marker }: { player: Player; onChange?: (player: Player) => void; benchNumber?: number; change?: Change; marker?: "C" | "V" }) {
  return (
    <div className={`${styles.playerRow} ${change ? styles.changedRow : ""}`}>
      {benchNumber ? <span className={styles.benchNumber}>{benchNumber}</span> : null}
      <Shirt primary={player.kit} secondary={player.kitSecondary} />
      <div className={styles.playerIdentity}>
        <strong>{player.name}</strong>
        <span>{player.club} · {player.position}</span>
      </div>
      {marker ? <span className={styles.playerMarker} aria-label={marker === "C" ? "Captain" : "Vice-captain"}>{marker}</span> : null}
      {change ? <span className={styles.inTag}>IN</span> : <span className={styles.price}>{money(player.price)}</span>}
      {onChange ? <button className={styles.changeButton} type="button" onClick={() => onChange(player)} aria-label={`Change ${player.name}`}>{change ? "Edit" : "Change"}</button> : null}
    </div>
  );
}

function Lookup({ onLoaded }: { onLoaded: (team: LoadedTeam) => void }) {
  const [id, setId] = useState(() => {
    if (typeof window === "undefined") return "";
    const savedId = window.localStorage.getItem("gaffertalk.teamId");
    return savedId && /^\d{1,10}$/.test(savedId) ? savedId : "";
  });
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^\d{1,10}$/.test(id) || Number(id) <= 0) { setError("Enter a valid numeric Team ID."); return; }
    setIsLoading(true);
    setError("");
    try {
      const result = await loadSquad(id);
      if (result.availability.status === "not_yet_published") {
        const nextDeadline = result.availability.next_deadline ? ` The next deadline is ${formatDeadline(result.availability.next_deadline)}.` : "";
        setError(`${result.availability.reason}${nextDeadline}`);
        return;
      }
      const loaded = mapLoadedTeam(result);
      if (!loaded) { setError("FPL returned an incomplete squad. Please try again shortly."); return; }
      onLoaded(loaded);
    } catch (caught) {
      if (caught instanceof CurrentTeamApiError && caught.code === "invalid_team_id") setError("We couldn’t find that FPL Team ID. Check it and try again.");
      else if (caught instanceof CurrentTeamApiError) setError(caught.message);
      else setError("The team could not be loaded. Try again shortly.");
    } finally {
      setIsLoading(false);
    }
  };
  return (
    <section className={styles.lookupStage}>
      <div>
        <p className={styles.eyebrow}><span>Start here</span> Public FPL data</p>
        <h1>Bring in<br />your team.</h1>
        <p className={styles.lede}>Enter your public FPL Team ID. We’ll load the latest deadline squad—without asking for your password.</p>
      </div>
      <form className={styles.lookupCard} onSubmit={submit}>
        <span className={styles.cardStep}>01</span>
        <label htmlFor="team-id">FPL Team ID</label>
        <input id="team-id" inputMode="numeric" value={id} onChange={(event) => { setId(event.target.value.trim()); setError(""); }} aria-describedby="team-id-help team-id-error" />
        <p id="team-id-help">Find this number in the URL of your public FPL points page.</p>
        {error ? <p className={styles.fieldError} id="team-id-error" role="alert">{error}</p> : null}
        <button className={styles.primaryAction} type="submit" disabled={isLoading}>{isLoading ? "Loading squad…" : "Load my team"}</button>
        <small>No FPL password needed</small>
      </form>
    </section>
  );
}

export function ConfirmTeamFlow() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("lookup");
  const [loadedTeam, setLoadedTeam] = useState<LoadedTeam | null>(null);
  const [changes, setChanges] = useState<Change[]>([]);
  const [selectedOutgoing, setSelectedOutgoing] = useState<Player | null>(null);
  const [selectedIncoming, setSelectedIncoming] = useState<Player | null>(null);
  const [query, setQuery] = useState("");
  const [bank, setBank] = useState("1.5");
  const [freeTransfers, setFreeTransfers] = useState("1");
  const [reviewError, setReviewError] = useState("");
  const [captainId, setCaptainId] = useState(0);
  const [viceCaptainId, setViceCaptainId] = useState(0);
  const [leadershipRole, setLeadershipRole] = useState<LeadershipRole | null>(null);
  const [candidates, setCandidates] = useState<Player[]>([]);
  const [searchState, setSearchState] = useState<"idle" | "loading" | "error">("idle");
  const currentSquad = useMemo(() => (loadedTeam?.squad ?? []).map((player) => changes.find((item) => item.outgoing.id === player.id)?.incoming ?? player), [changes, loadedTeam]);

  useEffect(() => {
    if (!selectedOutgoing || query.trim().length < 2) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setSearchState("loading");
      try {
        const players = await searchPlayers(selectedOutgoing.position, query.trim(), controller.signal);
        const currentIds = new Set(currentSquad.map((player) => player.id));
        setCandidates(players.filter((player) => {
          if (currentIds.has(player.id)) return false;
          const currentClubCount = currentSquad.filter((squadPlayer) => squadPlayer.clubId === player.club.id && squadPlayer.id !== selectedOutgoing.id).length;
          return currentClubCount < 3;
        }).map((player) => toPlayer(player)));
        setSearchState("idle");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setSearchState("error");
      }
    }, 250);
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [currentSquad, query, selectedOutgoing]);

  const openReplacement = (displayedPlayer: Player) => {
    const existing = changes.find((item) => item.incoming.id === displayedPlayer.id);
    setSelectedOutgoing(existing?.outgoing ?? displayedPlayer);
    setSelectedIncoming(existing?.incoming ?? null);
    setQuery("");
    setCandidates([]);
    setSearchState("idle");
  };
  const confirmReplacement = () => {
    if (!selectedOutgoing || !selectedIncoming) return;
    setChanges((items) => [...items.filter((item) => item.outgoing.id !== selectedOutgoing.id), { outgoing: selectedOutgoing, incoming: { ...selectedIncoming, group: selectedOutgoing.group } }]);
    if (captainId === selectedOutgoing.id) setCaptainId(selectedIncoming.id);
    if (viceCaptainId === selectedOutgoing.id) setViceCaptainId(selectedIncoming.id);
    setSelectedOutgoing(null);
    setSelectedIncoming(null);
  };
  const removeChange = (outgoingId: number) => {
    const change = changes.find((item) => item.outgoing.id === outgoingId);
    if (change && captainId === change.incoming.id) setCaptainId(change.outgoing.id);
    if (change && viceCaptainId === change.incoming.id) setViceCaptainId(change.outgoing.id);
    setChanges((items) => items.filter((item) => item.outgoing.id !== outgoingId));
  };
  const changeLeader = (player: Player) => {
    if (!leadershipRole) return;
    const [nextCaptain, nextViceCaptain] = assignLeadership(captainId, viceCaptainId, leadershipRole, player.id);
    setCaptainId(nextCaptain);
    setViceCaptainId(nextViceCaptain);
    setLeadershipRole(null);
  };
  const saveState = (event: FormEvent) => {
    event.preventDefault();
    const parsedBank = Number(bank);
    if (!Number.isFinite(parsedBank) || parsedBank < 0 || parsedBank > 20) { setReviewError("Enter a bank value between £0.0m and £20.0m."); return; }
    setReviewError("");
    if (!loadedTeam?.result.snapshot) return;
    const confirmedState = buildConfirmedCurrentTeam({ teamId: loadedTeam.result.entry.id, sourceGameweek: loadedTeam.result.snapshot.gameweek.id, playerIds: currentSquad.map((player) => player.id), changes: changes.map((change) => ({ outgoingPlayerId: change.outgoing.id, incomingPlayerId: change.incoming.id })), captainId, viceCaptainId, bankTenths: Math.round(parsedBank * 10), freeTransfers: Number(freeTransfers), confirmedAt: new Date().toISOString() });
    window.localStorage.setItem("gaffertalk.currentTeam.v1", JSON.stringify(confirmedState));
    window.localStorage.setItem("gaffertalk.recommendationSquad.v1", JSON.stringify({
      squad: {
        name: loadedTeam.result.entry.team_name,
        player_ids: currentSquad.map((player) => player.id),
        squad_positions: Object.fromEntries(currentSquad.map((player, index) => [player.id, index + 1])),
        bank_tenths: Math.round(parsedBank * 10),
        free_transfers: Number(freeTransfers),
      },
      players: currentSquad.map((player) => ({
        id: player.id,
        web_name: player.name,
        club: { id: player.clubId, name: player.club, short_name: player.club },
        position: player.position,
        current_price: { tenths: Math.round(player.price * 10) },
        status: "a",
        chance_of_playing_next_round: null,
        news: "",
      })),
    }));
    setStage("ready");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const groups = (["GKP", "DEF", "MID", "FWD"] as Position[]).map((position) => ({ position, players: currentSquad.filter((player) => player.group === "starter" && player.position === position) }));
  const bench = currentSquad.filter((player) => player.group === "bench");
  const captain = currentSquad.find((player) => player.id === captainId);
  const viceCaptain = currentSquad.find((player) => player.id === viceCaptainId);
  const entry = loadedTeam?.result.entry;
  const snapshot = loadedTeam?.result.snapshot;
  const managerName = [entry?.manager_first_name, entry?.manager_last_name].filter(Boolean).join(" ") || "FPL manager";

  return (
    <main className={styles.app}>
      <Header stage={stage} />
      {stage === "lookup" ? <Lookup onLoaded={(team) => { setLoadedTeam(team); window.localStorage.setItem("gaffertalk.teamId", String(team.result.entry.id)); setBank(team.result.snapshot?.bank ? (team.result.snapshot.bank.tenths / 10).toFixed(1) : ""); setCaptainId(team.captainId); setViceCaptainId(team.viceCaptainId); setChanges([]); setStage("confirm"); window.scrollTo({ top: 0 }); }} /> : null}

      {stage === "confirm" ? (
        <>
          <section className={styles.intro}>
            <div><p className={styles.eyebrow}><span>Squad check</span> Public FPL snapshot</p><h1>Is this still<br />your team?</h1><p className={styles.lede}>We loaded your squad as it stood at the {snapshot?.gameweek.name} deadline. Check it once, then GafferTalk can work from the right team.</p></div>
            <article className={styles.snapshotCard}><div className={styles.snapshotTopline}><span>Locked team</span><span>GW{String(snapshot?.gameweek.id ?? "").padStart(2, "0")}</span></div><strong>Deadline snapshot</strong><time dateTime={snapshot?.gameweek.deadline_time}>{snapshot ? formatDeadline(snapshot.gameweek.deadline_time) : "Unavailable"}</time><p>This comes from public FPL data. Any changes made after the deadline need your confirmation.</p></article>
          </section>
          <section className={styles.managerStrip} aria-label="Loaded FPL manager"><div><span>Manager</span><strong>{managerName}</strong></div><div><span>Team</span><strong>{entry?.team_name}</strong></div><div><span>Team ID</span><strong>{entry?.id}</strong></div><span className={styles.loadedStatus}><i /> Squad loaded</span></section>
          <div className={styles.squadLayout}>
            <section className={styles.squadPanel} aria-labelledby="starting-xi-title">
              <div className={styles.panelHeader}><div><span>11 players</span><h2 id="starting-xi-title">Starting XI</h2></div><p>Use <strong>Change</strong> only for transfers you have already made.</p></div>
              {groups.map(({ position, players }) => <div className={styles.positionGroup} key={position}><div className={styles.positionLabel}><span>{position}</span><strong>{positionNames[position]}</strong></div><div>{players.map((player) => <PlayerRow player={player} onChange={openReplacement} marker={player.id === captainId ? "C" : player.id === viceCaptainId ? "V" : undefined} change={changes.find((item) => item.incoming.id === player.id)} key={player.id} />)}</div></div>)}
            </section>
            <aside className={styles.sidebar}>
              <section className={styles.benchPanel} aria-labelledby="bench-title"><div className={styles.panelHeaderCompact}><div><span>4 players</span><h2 id="bench-title">Bench</h2></div><span className={styles.dataTag}>{changes.length ? "Updated" : "From FPL"}</span></div><div className={styles.benchList}>{bench.map((player, index) => <PlayerRow player={player} benchNumber={index + 1} onChange={openReplacement} marker={player.id === captainId ? "C" : player.id === viceCaptainId ? "V" : undefined} change={changes.find((item) => item.incoming.id === player.id)} key={player.id} />)}</div></section>
              <section className={styles.leadershipPanel} aria-labelledby="leadership-title">
                <div className={styles.panelHeaderCompact}><div><span>Matchday roles</span><h2 id="leadership-title">Captaincy</h2></div><span className={styles.dataTag}>Confirmed by you</span></div>
                {captain ? <div className={styles.leaderRow}><span className={styles.playerMarker}>C</span><Shirt primary={captain.kit} secondary={captain.kitSecondary} /><p><small>Captain</small><strong>{captain.name}</strong></p><button className={styles.changeButton} type="button" onClick={() => setLeadershipRole("captain")}>Change</button></div> : null}
                {viceCaptain ? <div className={styles.leaderRow}><span className={`${styles.playerMarker} ${styles.viceMarker}`}>V</span><Shirt primary={viceCaptain.kit} secondary={viceCaptain.kitSecondary} /><p><small>Vice-captain</small><strong>{viceCaptain.name}</strong></p><button className={styles.changeButton} type="button" onClick={() => setLeadershipRole("vice")}>Change</button></div> : null}
              </section>
              <section className={styles.decisionCard}><span className={styles.decisionNumber}>02</span><p className={styles.decisionKicker}>{changes.length ? `${changes.length} change${changes.length === 1 ? "" : "s"} recorded` : "One quick check"}</p><h2>{changes.length ? "Ready to review?" : "Made any transfers since GW1?"}</h2><p>{changes.length ? "Your edited players are marked IN. Review them, then confirm your current bank and free transfers." : <>If the squad is right, continue. If not, use <strong>Change</strong> beside the players who moved.</>}</p><button className={styles.primaryAction} type="button" onClick={() => { setStage("review"); window.scrollTo({ top: 0, behavior: "smooth" }); }}>{changes.length ? "Review changes" : "No changes — continue"}</button><small>No FPL password needed</small></section>
            </aside>
          </div>
        </>
      ) : null}

      {stage === "review" ? (
        <section className={styles.reviewStage}>
          <div className={styles.reviewHeading}><p className={styles.eyebrow}><span>Final check</span> Confirmed by you</p><h1>{changes.length ? "Review your changes." : "Confirm your state."}</h1><p className={styles.lede}>{changes.length ? "Make sure we recorded the transfers you already made." : "You confirmed that the deadline squad is still current."} Add the two details FPL cannot reliably give us during an open Gameweek.</p></div>
          <div className={styles.reviewGrid}>
            <section className={styles.changeSummary}>
              <div className={styles.panelHeaderCompact}><div><span>{changes.length} recorded</span><h2>{changes.length === 1 ? "Transfer" : "Transfers"}</h2></div><button type="button" className={styles.textButton} onClick={() => setStage("confirm")}>Edit squad</button></div>
              {changes.length ? changes.map((change) => <article className={styles.transferPair} key={change.outgoing.id}><div><span className={styles.outTag}>OUT</span><Shirt primary={change.outgoing.kit} secondary={change.outgoing.kitSecondary} /><p><strong>{change.outgoing.name}</strong><small>{change.outgoing.club} · {change.outgoing.position}</small></p></div><span className={styles.transferArrow}>→</span><div><span className={styles.inTag}>IN</span><Shirt primary={change.incoming.kit} secondary={change.incoming.kitSecondary} /><p><strong>{change.incoming.name}</strong><small>{change.incoming.club} · {money(change.incoming.price)}</small></p></div><button type="button" onClick={() => removeChange(change.outgoing.id)}>Undo</button></article>) : <div className={styles.noChanges}><span>✓</span><div><strong>No transfers recorded</strong><p>Your public deadline squad will be used as your current squad.</p></div></div>}
            </section>
            <form className={styles.stateForm} onSubmit={saveState}>
              <p className={styles.formKicker}>Planning state</p><h2>Two details, then we’re ready.</h2>
              <label htmlFor="bank">Current money in the bank</label><div className={styles.moneyInput}><span>£</span><input id="bank" type="number" min="0" max="20" step="0.1" value={bank} onChange={(event) => { setBank(event.target.value); setReviewError(""); }} /><span>m</span></div>
              <label htmlFor="free-transfers">Free transfers available</label><select id="free-transfers" value={freeTransfers} onChange={(event) => setFreeTransfers(event.target.value)}>{[0, 1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value}</option>)}</select>
              <p className={styles.formNote}>We’ll only ask for an outgoing player’s selling price later if an exact budget check needs it.</p>
              {reviewError ? <p className={styles.fieldError} role="alert">{reviewError}</p> : null}
              <button className={styles.primaryAction} type="submit">Save current team</button>
            </form>
          </div>
        </section>
      ) : null}

      {stage === "ready" ? (
        <section className={styles.readyStage}>
          <span className={styles.readyTick}>✓</span><p className={styles.eyebrow}><span>Team ready</span> Trusted planning state</p><h1>You’re ready<br />to make the call.</h1><p className={styles.lede}>GafferTalk now has your current 15-player squad, <strong>£{Number(bank).toFixed(1)}m</strong> in the bank and <strong>{freeTransfers}</strong> free transfer{freeTransfers === "1" ? "" : "s"}.</p>
          <div className={styles.provenanceGrid}><article><span>From public FPL data</span><strong>{snapshot?.gameweek.name} squad snapshot</strong><p>Players, clubs, positions and deadline context.</p></article><article><span>Confirmed by you</span><strong>{changes.length} squad change{changes.length === 1 ? "" : "s"}</strong><p>Current bank, captaincy and free-transfer count.</p></article></div>
          <div className={styles.readyActions}><button className={styles.primaryAction} type="button" onClick={() => router.push("/recommend")}>Continue to GafferTalk</button><button className={styles.textButton} type="button" onClick={() => setStage("confirm")}>Edit current team</button></div>
          <p className={styles.prototypeNote}>Your confirmed state is saved on this device. The assistant screen comes next.</p>
        </section>
      ) : null}

      {selectedOutgoing ? (
        <div className={styles.drawerBackdrop} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedOutgoing(null); }}>
          <section className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby="replacement-title">
            <div className={styles.drawerHeader}><div><span>Record a past transfer</span><h2 id="replacement-title">Who came in for {selectedOutgoing.name}?</h2></div><button type="button" onClick={() => setSelectedOutgoing(null)} aria-label="Close replacement panel">×</button></div>
            <div className={styles.outgoingSummary}><span className={styles.outTag}>OUT</span><Shirt primary={selectedOutgoing.kit} secondary={selectedOutgoing.kitSecondary} /><p><strong>{selectedOutgoing.name}</strong><small>{selectedOutgoing.club} · {selectedOutgoing.position} · {money(selectedOutgoing.price)}</small></p></div>
            <label className={styles.searchLabel} htmlFor="player-search">Search {selectedOutgoing.position} players</label><input className={styles.searchInput} id="player-search" autoFocus placeholder="Type a player name…" value={query} onChange={(event) => { setQuery(event.target.value); setCandidates([]); setSearchState("idle"); }} />
            <div className={styles.candidateList}>{candidates.length ? candidates.map((player) => <button className={`${styles.candidate} ${selectedIncoming?.id === player.id ? styles.selectedCandidate : ""}`} type="button" onClick={() => setSelectedIncoming(player)} key={player.id}><Shirt primary={player.kit} secondary={player.kitSecondary} /><span><strong>{player.name}</strong><small>{player.club} · {player.position}</small></span><b>{money(player.price)}</b><i>{selectedIncoming?.id === player.id ? "✓" : ""}</i></button>) : <p className={styles.emptyCandidates}>{query.trim().length < 2 ? "Type at least two characters to search." : searchState === "loading" ? "Searching current FPL players…" : searchState === "error" ? "Player search is unavailable. Try again." : "No matching players found."}</p>}</div>
            <div className={styles.drawerActions}><button className={styles.textButton} type="button" onClick={() => setSelectedOutgoing(null)}>Cancel</button><button className={styles.primaryAction} type="button" disabled={!selectedIncoming} onClick={confirmReplacement}>Confirm replacement</button></div>
          </section>
        </div>
      ) : null}

      {leadershipRole ? (
        <div className={styles.drawerBackdrop} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setLeadershipRole(null); }}>
          <section className={`${styles.drawer} ${styles.leadershipDrawer}`} role="dialog" aria-modal="true" aria-labelledby="leadership-drawer-title">
            <div className={styles.drawerHeader}><div><span>Matchday role</span><h2 id="leadership-drawer-title">Choose your {leadershipRole === "captain" ? "captain" : "vice-captain"}</h2></div><button type="button" onClick={() => setLeadershipRole(null)} aria-label="Close captaincy panel">×</button></div>
            <p className={styles.drawerIntro}>Select from your current Starting XI. Choosing the other role-holder will neatly swap the two roles.</p>
            <div className={`${styles.candidateList} ${styles.leadershipList}`}>
              {currentSquad.filter((player) => player.group === "starter").map((player) => {
                const active = player.id === (leadershipRole === "captain" ? captainId : viceCaptainId);
                const otherRole = player.id === (leadershipRole === "captain" ? viceCaptainId : captainId);
                return <button className={`${styles.candidate} ${active ? styles.selectedCandidate : ""}`} type="button" onClick={() => changeLeader(player)} key={player.id}><Shirt primary={player.kit} secondary={player.kitSecondary} /><span><strong>{player.name}</strong><small>{player.club} · {player.position}</small></span>{otherRole ? <b>{leadershipRole === "captain" ? "V" : "C"}</b> : <b /> }<i>{active ? "✓" : ""}</i></button>;
              })}
            </div>
          </section>
        </div>
      ) : null}

      <footer className={styles.footer}><span>GafferTalk does the homework.</span><span>You make the call.</span></footer>
    </main>
  );
}
