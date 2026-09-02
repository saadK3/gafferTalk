"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import {
  CurrentTeamApiError,
  loadSquad,
  searchPlayers,
  type ApiPlayer,
  type SquadLookupResult,
} from "@/lib/current-team-api";
import {
  confirmProWorkspaceState,
  loadProWorkspace,
  previewWorkspacePlan,
  ProWorkspaceApiError,
  reconcileWorkspacePlan,
  researchWorkspaceNamedTransfer,
  saveWorkspacePlan,
  updateWorkspacePlanLifecycle,
  type PlanDraft,
  type PlanReconciliation,
  type ProWorkspace,
  type WorkspacePlan,
  type WorkspaceReport,
} from "@/lib/pro-workspace-api";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import styles from "./workspace.module.css";

type RecordedChange = { outgoing: ApiPlayer; incoming: ApiPlayer };

function money(tenths: number): string {
  return `£${(tenths / 10).toFixed(1)}m`;
}

function timestamp(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(new Date(value));
}

function Header({ onSignOut }: { onSignOut: () => void }) {
  return (
    <header className={styles.header}>
      <Link className={styles.wordmark} href="/">GafferTalk<span>.</span></Link>
      <div><i /> Pro workspace</div>
      <button type="button" onClick={onSignOut}>Sign out</button>
    </header>
  );
}

function TeamOnboarding({
  onConfirmed,
  initialTeamId,
}: {
  onConfirmed: (workspace: ProWorkspace) => void;
  initialTeamId?: number;
}) {
  const [teamId, setTeamId] = useState(initialTeamId ? String(initialTeamId) : "");
  const [loaded, setLoaded] = useState<SquadLookupResult | null>(null);
  const [changes, setChanges] = useState<RecordedChange[]>([]);
  const [bank, setBank] = useState("0.0");
  const [freeTransfers, setFreeTransfers] = useState("1");
  const [risk, setRisk] = useState<"safe" | "balanced" | "aggressive">("balanced");
  const [outgoingId, setOutgoingId] = useState("");
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<ApiPlayer[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const deadlinePlayers = useMemo(
    () => loaded?.snapshot?.picks.map((pick) => pick.player) ?? [],
    [loaded],
  );
  const currentPlayers = useMemo(
    () => deadlinePlayers.map((player) => changes.find((change) => change.outgoing.id === player.id)?.incoming ?? player),
    [changes, deadlinePlayers],
  );

  const lookup = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^\d{1,10}$/.test(teamId) || Number(teamId) < 1) {
      setError("Enter a valid numeric FPL Team ID.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await loadSquad(teamId);
      if (!result.snapshot) {
        setError(result.availability.reason);
        return;
      }
      setLoaded(result);
      setChanges([]);
      setBank(((result.snapshot.bank?.tenths ?? 0) / 10).toFixed(1));
    } catch (caught) {
      setError(caught instanceof CurrentTeamApiError ? caught.message : "The team could not be loaded.");
    } finally {
      setBusy(false);
    }
  };

  const findReplacement = async () => {
    const outgoing = currentPlayers.find((player) => player.id === Number(outgoingId));
    if (!outgoing || query.trim().length < 2) return;
    setBusy(true);
    setError("");
    try {
      const found = await searchPlayers(outgoing.position, query.trim());
      const currentIds = new Set(currentPlayers.map((player) => player.id));
      setCandidates(found.filter((player) => {
        if (currentIds.has(player.id)) return false;
        const clubCount = currentPlayers.filter((item) => item.id !== outgoing.id && item.club.id === player.club.id).length;
        return clubCount < 3;
      }));
    } catch (caught) {
      setError(caught instanceof CurrentTeamApiError ? caught.message : "Player search failed.");
    } finally {
      setBusy(false);
    }
  };

  const recordChange = (incoming: ApiPlayer) => {
    const displayedOutgoing = currentPlayers.find((player) => player.id === Number(outgoingId));
    if (!displayedOutgoing) return;
    const prior = changes.find((change) => change.incoming.id === displayedOutgoing.id);
    const outgoing = prior?.outgoing ?? displayedOutgoing;
    setChanges((items) => [
      ...items.filter((change) => change.outgoing.id !== outgoing.id),
      { outgoing, incoming },
    ]);
    setOutgoingId("");
    setQuery("");
    setCandidates([]);
  };

  const confirm = async (event: FormEvent) => {
    event.preventDefault();
    const snapshot = loaded?.snapshot;
    if (!loaded || !snapshot) return;
    const bankTenths = Math.round(Number(bank) * 10);
    if (!Number.isInteger(bankTenths) || bankTenths < 0 || bankTenths > 200) {
      setError("Enter a bank value between £0.0m and £20.0m.");
      return;
    }
    const originalCaptain = snapshot.picks.find((pick) => pick.is_captain)?.player.id;
    const originalVice = snapshot.picks.find((pick) => pick.is_vice_captain)?.player.id;
    if (!originalCaptain || !originalVice) {
      setError("FPL did not return complete captaincy state.");
      return;
    }
    const replacedId = (playerId: number) => changes.find((change) => change.outgoing.id === playerId)?.incoming.id ?? playerId;
    setBusy(true);
    setError("");
    try {
      const workspace = await confirmProWorkspaceState({
        team_id: loaded.entry.id,
        team_name: loaded.entry.team_name,
        source_gameweek: snapshot.gameweek.id,
        player_ids: currentPlayers.map((player) => player.id),
        players: currentPlayers,
        squad_positions: Object.fromEntries(currentPlayers.map((player, index) => [player.id, index + 1])),
        changes: changes.map((change) => ({ outgoing_player_id: change.outgoing.id, incoming_player_id: change.incoming.id })),
        captain_id: replacedId(originalCaptain),
        vice_captain_id: replacedId(originalVice),
        bank_tenths: bankTenths,
        free_transfers: Number(freeTransfers),
        risk_preference: risk,
        confirmed_at: new Date().toISOString(),
        data_retrieved_at: snapshot.retrieved_at,
      });
      onConfirmed(workspace);
    } catch (caught) {
      setError(caught instanceof ProWorkspaceApiError ? caught.message : "Your state could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className={styles.onboarding}>
      <section className={styles.intro}>
        <p className={styles.eyebrow}>Account connected · Team setup</p>
        <h1>Confirm what<br />you own now.</h1>
        <p>We load the latest public deadline squad. You add only what FPL cannot expose: post-deadline changes, current bank and free transfers.</p>
      </section>
      {!loaded ? (
        <form className={styles.setupCard} onSubmit={lookup}>
          <span>01 · Connect</span>
          <label htmlFor="workspace-team-id">Public FPL Team ID</label>
          <input id="workspace-team-id" inputMode="numeric" value={teamId} onChange={(event) => setTeamId(event.target.value.trim())} />
          <button type="submit" disabled={busy}>{busy ? "Loading…" : "Load my team"}</button>
          <small>No FPL password or session cookie is requested.</small>
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
        </form>
      ) : (
        <form className={styles.confirmGrid} onSubmit={confirm}>
          <section className={styles.squadPanel}>
            <div className={styles.panelHeading}>
              <div><span>Latest finalized squad</span><h2>{loaded.entry.team_name}</h2></div>
              <small>GW{loaded.snapshot?.gameweek.id} · retrieved {timestamp(loaded.snapshot!.retrieved_at)}</small>
            </div>
            <div className={styles.playerGrid}>
              {currentPlayers.map((player) => (
                <article key={player.id}>
                  <div><strong>{player.web_name}</strong><small>{player.club.short_name} · {player.position}</small></div>
                  <b>{money(player.current_price.tenths)}</b>
                </article>
              ))}
            </div>
          </section>
          <section className={styles.statePanel}>
            <span>02 · Reconcile</span>
            <h2>Changes since the deadline</h2>
            <p>If none were made, leave this empty. Otherwise record each completed transfer.</p>
            <label htmlFor="changed-outgoing">Player transferred out</label>
            <select id="changed-outgoing" value={outgoingId} onChange={(event) => { setOutgoingId(event.target.value); setCandidates([]); }}>
              <option value="">Choose a current player</option>
              {currentPlayers.map((player) => <option key={player.id} value={player.id}>{player.web_name} · {player.position}</option>)}
            </select>
            <label htmlFor="changed-incoming">Replacement search</label>
            <div className={styles.searchRow}>
              <input id="changed-incoming" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="At least 2 letters" />
              <button type="button" onClick={findReplacement} disabled={!outgoingId || query.trim().length < 2 || busy}>Search</button>
            </div>
            {candidates.length ? <div className={styles.candidates}>{candidates.map((player) => <button type="button" key={player.id} onClick={() => recordChange(player)}><strong>{player.web_name}</strong><span>{player.club.short_name} · {money(player.current_price.tenths)}</span></button>)}</div> : null}
            {changes.length ? <ul className={styles.changeList}>{changes.map((change) => <li key={change.outgoing.id}><span>{change.outgoing.web_name} → {change.incoming.web_name}</span><button type="button" onClick={() => setChanges((items) => items.filter((item) => item.outgoing.id !== change.outgoing.id))}>Remove</button></li>)}</ul> : <p className={styles.noChanges}>No post-deadline changes recorded.</p>}
            <div className={styles.stateFields}>
              <label>Current bank<input type="number" min="0" max="20" step="0.1" value={bank} onChange={(event) => setBank(event.target.value)} /></label>
              <label>Free transfers<select value={freeTransfers} onChange={(event) => setFreeTransfers(event.target.value)}>{[0, 1, 2, 3, 4, 5].map((value) => <option key={value}>{value}</option>)}</select></label>
              <label>Risk preference<select value={risk} onChange={(event) => setRisk(event.target.value as typeof risk)}><option value="safe">Safe</option><option value="balanced">Balanced</option><option value="aggressive">Aggressive</option></select></label>
            </div>
            <label className={styles.confirmation}><input type="checkbox" required /> I confirm this is my current planning state.</label>
            <button className={styles.primary} type="submit" disabled={busy}>{busy ? "Saving…" : "Enter Pro workspace"}</button>
            {error ? <p className={styles.error} role="alert">{error}</p> : null}
          </section>
        </form>
      )}
    </main>
  );
}

function ReportView({ report }: { report: WorkspaceReport }) {
  return (
    <article className={styles.reportView}>
      <header>
        <div><span>Report v{report.version} · Squad state v{report.squad_state_version}</span><h2>{report.report.verdict}</h2></div>
        <p>{report.report.recommended_action}</p>
        <b className={styles[report.report.confidence.level]}>{report.report.confidence.level} confidence</b>
      </header>
      <blockquote>{report.assistant_message}</blockquote>
      <div className={styles.reportColumns}>
        <section><span>Case for</span><ul>{report.report.case_for.map((reason) => <li key={reason}>{reason}</li>)}</ul></section>
        <section><span>Case against</span><ul>{report.report.case_against.map((reason) => <li key={reason}>{reason}</li>)}</ul></section>
      </div>
      <div className={styles.reportMeta}>
        <div><span>Resulting bank</span><strong>{money(report.report.requested_route.remaining_bank.tenths)}</strong></div>
        <div><span>Hit</span><strong>{report.report.requested_route.points_hit ? `−${report.report.requested_route.points_hit}` : "None"}</strong></div>
        <div><span>Evidence refreshed</span><strong>{timestamp(report.data_retrieved_at)}</strong></div>
      </div>
      <details><summary>Assumptions and change conditions</summary><ul>{[...report.report.assumptions, ...report.report.change_conditions].map((item) => <li key={item}>{item}</li>)}</ul></details>
    </article>
  );
}

function PlanTimeline({ plan }: { plan: PlanDraft | WorkspacePlan }) {
  return (
    <div className={styles.planTimeline}>
      {plan.actions.map((action) => (
        <article key={`${action.sequence}-${action.kind}`}>
          <div><span>GW{action.gameweek_id} · {action.kind.replaceAll("_", " ")}</span><b>{action.sequence}</b></div>
          <h3>{action.headline}</h3>
          <p>{action.condition}</p>
          <small>{money(action.expected_bank_after_tenths)} expected bank · {action.expected_free_transfers_after} FT</small>
        </article>
      ))}
    </div>
  );
}

function SavedPlanView({
  plan,
  stateBank,
  stateFreeTransfers,
  busy,
  reconciliation,
  onReconcile,
  onLifecycle,
}: {
  plan: WorkspacePlan;
  stateBank: number;
  stateFreeTransfers: number;
  busy: boolean;
  reconciliation: PlanReconciliation | null;
  onReconcile: (input: { bank_tenths: number; free_transfers: number; relevant_selling_price_tenths: number }) => void;
  onLifecycle: (lifecycle: "completed" | "abandoned") => void;
}) {
  const [bank, setBank] = useState(String(stateBank / 10));
  const [freeTransfers, setFreeTransfers] = useState(String(stateFreeTransfers));
  const [sellingPrice, setSellingPrice] = useState(String(plan.relevant_selling_price_tenths / 10));
  return (
    <section className={`${styles.planCard} ${plan.lifecycle === "stale" ? styles.stalePlan : ""}`}>
      <header>
        <div><span>Plan v{plan.version} · squad state v{plan.squad_state_version}</span><h2>GW{plan.horizon_gameweeks[0]}–{plan.horizon_gameweeks[2]}</h2></div>
        <b>{plan.lifecycle}</b>
        <p>Five-Gameweek evidence · three-Gameweek conditional horizon · {plan.confidence} confidence</p>
      </header>
      {plan.stale_reasons.length ? <div className={styles.staleReasons}><strong>Recalculation required</strong><p>{plan.stale_reasons.map((reason) => reason.replaceAll("_", " ")).join(" · ")}</p></div> : null}
      <PlanTimeline plan={plan} />
      <details><summary>Conditions, alternatives and assumptions</summary><ul>{[...plan.conditions, ...plan.alternatives, ...plan.assumptions].map((item) => <li key={item}>{item}</li>)}</ul></details>
      {plan.lifecycle === "active" || plan.lifecycle === "stale" ? (
        <form className={styles.reconcileForm} onSubmit={(event) => { event.preventDefault(); onReconcile({ bank_tenths: Math.round(Number(bank) * 10), free_transfers: Number(freeTransfers), relevant_selling_price_tenths: Math.round(Number(sellingPrice) * 10) }); }}>
          <div><span>Returning-session check</span><h3>Compare with the newest finalized snapshot</h3><p>Confirm private values that FPL cannot reliably expose before we decide whether this plan is still safe to use.</p></div>
          <label>Current bank (£m)<input type="number" min="0" max="20" step="0.1" value={bank} onChange={(event) => setBank(event.target.value)} /></label>
          <label>Free transfers<select value={freeTransfers} onChange={(event) => setFreeTransfers(event.target.value)}>{[0, 1, 2, 3, 4, 5].map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>Relevant selling price (£m)<input type="number" min="0" max="30" step="0.1" value={sellingPrice} onChange={(event) => setSellingPrice(event.target.value)} /></label>
          <button type="submit" disabled={busy}>{busy ? "Checking…" : "Check current evidence"}</button>
        </form>
      ) : null}
      {reconciliation?.plan_id === plan.id ? <div className={reconciliation.materially_stale ? styles.reconcileBlocked : styles.reconcileResult}><strong>{reconciliation.stale_reasons.length ? "Changes detected" : "Plan remains current"}</strong><p>Newest public snapshot: GW{reconciliation.newest_snapshot_gameweek}. {reconciliation.requires_state_confirmation ? "Reconfirm your full planning state before new research." : "No private-state confirmation is required."}</p></div> : null}
      {plan.lifecycle === "active" || plan.lifecycle === "stale" ? <div className={styles.planLifecycle}><button type="button" onClick={() => onLifecycle("completed")} disabled={busy}>Mark completed</button><button type="button" onClick={() => onLifecycle("abandoned")} disabled={busy}>Abandon plan</button></div> : null}
    </section>
  );
}

function WorkspaceDashboard({ workspace, setWorkspace, onReconfirm }: { workspace: ProWorkspace; setWorkspace: (workspace: ProWorkspace) => void; onReconfirm: () => void }) {
  const state = workspace.current_state!;
  const [outgoingId, setOutgoingId] = useState("");
  const [sellingPrice, setSellingPrice] = useState("");
  const [query, setQuery] = useState("");
  const [targets, setTargets] = useState<ApiPlayer[]>([]);
  const [target, setTarget] = useState<ApiPlayer | null>(null);
  const [question, setQuestion] = useState("");
  const [selectedReportId, setSelectedReportId] = useState(workspace.reports[0]?.id ?? "");
  const [planDraft, setPlanDraft] = useState<PlanDraft | null>(null);
  const [reconciliation, setReconciliation] = useState<PlanReconciliation | null>(null);
  const [busy, setBusy] = useState(false);
  const [planBusy, setPlanBusy] = useState(false);
  const [error, setError] = useState("");
  const [planError, setPlanError] = useState("");
  const selectedReport = workspace.reports.find((report) => report.id === selectedReportId) ?? workspace.reports[0];
  const currentPlan = workspace.plans.find((plan) => plan.lifecycle === "active" || plan.lifecycle === "stale") ?? workspace.plans[0];
  const materiallyStale = state.freshness_status === "stale";

  const selectOutgoing = (value: string) => {
    setOutgoingId(value);
    setTargets([]);
    setTarget(null);
    setQuestion("");
    setError("");
    const player = state.players.find((item) => item.id === Number(value));
    setSellingPrice(player ? (player.current_price.tenths / 10).toFixed(1) : "");
  };
  const findTarget = async () => {
    const outgoing = state.players.find((player) => player.id === Number(outgoingId));
    if (!outgoing || query.trim().length < 2) return;
    setBusy(true);
    setError("");
    setTarget(null);
    setQuestion("");
    try {
      const found = await searchPlayers(outgoing.position, query.trim());
      setTargets(found.filter((player) => {
        if (state.player_ids.includes(player.id)) return false;
        const clubCountAfterSale = state.players.filter(
          (squadPlayer) => squadPlayer.id !== outgoing.id && squadPlayer.club.id === player.club.id,
        ).length;
        return clubCountAfterSale < 3;
      }));
    } catch (caught) {
      setError(caught instanceof CurrentTeamApiError ? caught.message : "Player search failed.");
    } finally {
      setBusy(false);
    }
  };
  const chooseTarget = (player: ApiPlayer) => {
    setTarget(player);
    setTargets([]);
    const outgoing = state.players.find((item) => item.id === Number(outgoingId));
    setQuestion(`Should I replace ${outgoing?.web_name ?? "this player"} with ${player.web_name}?`);
  };
  const runResearch = async (event: FormEvent) => {
    event.preventDefault();
    if (!target || !outgoingId) return;
    setBusy(true);
    setError("");
    try {
      const result = await researchWorkspaceNamedTransfer({
        outgoing_player_id: Number(outgoingId),
        outgoing_selling_price_tenths: Math.round(Number(sellingPrice) * 10),
        target_player_id: target.id,
        question,
      });
      setWorkspace(result.workspace);
      setSelectedReportId(result.workspace.reports[0]?.id ?? "");
    } catch (caught) {
      setError(caught instanceof ProWorkspaceApiError ? caught.message : "Research could not be completed.");
    } finally {
      setBusy(false);
    }
  };
  const previewPlan = async () => {
    if (!selectedReport) return;
    setPlanBusy(true);
    setPlanError("");
    try {
      const result = await previewWorkspacePlan(selectedReport.id);
      setPlanDraft(result.draft);
    } catch (caught) {
      setPlanError(caught instanceof ProWorkspaceApiError ? caught.message : "The plan preview could not be built.");
    } finally {
      setPlanBusy(false);
    }
  };
  const savePlan = async () => {
    if (!selectedReport) return;
    setPlanBusy(true);
    setPlanError("");
    try {
      const result = await saveWorkspacePlan(selectedReport.id);
      setWorkspace(result.workspace);
      setPlanDraft(null);
      setReconciliation(null);
    } catch (caught) {
      setPlanError(caught instanceof ProWorkspaceApiError ? caught.message : "The plan could not be saved.");
    } finally {
      setPlanBusy(false);
    }
  };
  const reconcilePlan = async (input: { bank_tenths: number; free_transfers: number; relevant_selling_price_tenths: number }) => {
    if (!currentPlan) return;
    setPlanBusy(true);
    setPlanError("");
    try {
      const result = await reconcileWorkspacePlan(currentPlan.id, input);
      setWorkspace(result.workspace);
      setReconciliation(result.reconciliation);
    } catch (caught) {
      setPlanError(caught instanceof ProWorkspaceApiError ? caught.message : "The plan could not be reconciled.");
    } finally {
      setPlanBusy(false);
    }
  };
  const changePlanLifecycle = async (lifecycle: "completed" | "abandoned") => {
    if (!currentPlan) return;
    setPlanBusy(true);
    setPlanError("");
    try {
      setWorkspace(await updateWorkspacePlanLifecycle(currentPlan.id, lifecycle));
      setReconciliation(null);
    } catch (caught) {
      setPlanError(caught instanceof ProWorkspaceApiError ? caught.message : "The plan could not be updated.");
    } finally {
      setPlanBusy(false);
    }
  };

  return (
    <main className={styles.workspace}>
      <section className={styles.workspaceHero}>
        <div><p className={styles.eyebrow}>Persistent Pro workspace</p><h1>{state.team_name}</h1><p>Confirmed squad state v{state.version} · {state.freshness_status} {timestamp(state.confirmed_at)}</p></div>
        <dl><div><dt>Bank</dt><dd>{money(state.bank_tenths)}</dd></div><div><dt>Free transfers</dt><dd>{state.free_transfers}</dd></div><div><dt>Risk</dt><dd>{state.risk_preference}</dd></div></dl>
        <button type="button" onClick={onReconfirm}>Update current state</button>
      </section>
      <div className={styles.workspaceLayout}>
        <aside className={styles.sidebar}>
          <section><span>Current squad</span><div className={styles.compactSquad}>{state.players.map((player) => <div key={player.id}><strong>{player.web_name}</strong><small>{player.position} · {money(player.current_price.tenths)}</small></div>)}</div></section>
          <section><span>Report history</span>{workspace.reports.length ? <div className={styles.history}>{workspace.reports.map((report) => <button className={report.id === selectedReport?.id ? styles.active : ""} type="button" key={report.id} onClick={() => setSelectedReportId(report.id)}><strong>v{report.version} · {report.report.requested_route.outgoing.web_name} → {report.report.requested_route.incoming.web_name}</strong><small>{timestamp(report.created_at)} · {report.report.verdict}</small></button>)}</div> : <p>No saved reports yet.</p>}</section>
          <section><span>Plan history</span>{workspace.plans.length ? <div className={styles.planHistory}>{workspace.plans.map((plan) => <div key={plan.id}><strong>v{plan.version} · GW{plan.horizon_gameweeks[0]}–{plan.horizon_gameweeks[2]}</strong><small>{plan.lifecycle} · report v{plan.report_version}</small></div>)}</div> : <p>No saved plans yet.</p>}</section>
        </aside>
        <div className={styles.researchArea}>
          {materiallyStale ? <section className={styles.materialBlock}><strong>Planning state needs confirmation</strong><p>A material change was detected. New research is blocked until you update and confirm the current squad, bank and free transfers.</p><button type="button" onClick={onReconfirm}>Reconcile current state</button></section> : null}
          {currentPlan ? <SavedPlanView plan={currentPlan} stateBank={state.bank_tenths} stateFreeTransfers={state.free_transfers} busy={planBusy} reconciliation={reconciliation} onReconcile={reconcilePlan} onLifecycle={changePlanLifecycle} /> : null}
          <form className={styles.researchCard} onSubmit={runResearch}>
            <div><span>Ask about a named transfer</span><h2>Make the case. Challenge the move.</h2></div>
            <div className={styles.researchFields}>
              <label>Player out<select value={outgoingId} onChange={(event) => selectOutgoing(event.target.value)} required><option value="">Choose player</option>{state.players.map((player) => <option key={player.id} value={player.id}>{player.web_name} · {player.position}</option>)}</select></label>
              <label>Selling price (£m)<input type="number" min="0" max="30" step="0.1" value={sellingPrice} onChange={(event) => setSellingPrice(event.target.value)} required /></label>
            </div>
            <label>Target player</label><div className={styles.searchRow}><input value={query} onChange={(event) => { setQuery(event.target.value); setTargets([]); setTarget(null); setQuestion(""); }} placeholder="Search a same-position replacement" /><button type="button" onClick={findTarget} disabled={!outgoingId || query.trim().length < 2 || busy}>Search</button></div>
            {targets.length ? <div className={styles.candidates}>{targets.map((player) => <button type="button" key={player.id} onClick={() => chooseTarget(player)}><strong>{player.web_name}</strong><span>{player.club.short_name} · {money(player.current_price.tenths)}</span></button>)}</div> : null}
            {target ? <p className={styles.selectedTarget}>Target: <strong>{target.web_name}</strong> · {money(target.current_price.tenths)}</p> : null}
            <label>Question<textarea value={question} onChange={(event) => setQuestion(event.target.value)} minLength={3} maxLength={500} required /></label>
            <button className={styles.primary} type="submit" disabled={!target || busy || materiallyStale}>{busy ? "Researching…" : materiallyStale ? "Reconfirm state to research" : "Run and save research"}</button>
            {error ? <p className={styles.error} role="alert">{error}</p> : null}
          </form>
          {selectedReport ? <><ReportView report={selectedReport} /><section className={styles.planBuilder}><div><span>Conditional planning</span><h2>Turn this report into a bounded 3GW plan.</h2><p>The next five Gameweeks inform the evidence. The plan prescribes only this Gameweek and the following two.</p></div><button type="button" onClick={previewPlan} disabled={planBusy || materiallyStale || selectedReport.squad_state_version !== state.version}>{planBusy ? "Building…" : "Preview conditional plan"}</button>{planDraft ? <div className={styles.planPreview}><header><strong>Preview · GW{planDraft.horizon_gameweeks[0]}–{planDraft.horizon_gameweeks[2]}</strong><small>{planDraft.confidence} confidence · evidence GW{planDraft.evidence_gameweeks.join(", ")}</small></header><PlanTimeline plan={planDraft} /><button className={styles.primary} type="button" onClick={savePlan} disabled={planBusy}>{workspace.plans.length ? "Save recalculated plan" : "Save as active plan"}</button></div> : null}{planError ? <p className={styles.error} role="alert">{planError}</p> : null}</section></> : <section className={styles.emptyReport}><span>Durable decision reports</span><h2>Your first saved report will appear here.</h2><p>It will remain attached to this exact squad-state version when you return on another authenticated session.</p></section>}
          <section className={styles.conversation}><span>Visible conversation history</span>{workspace.messages.length ? workspace.messages.map((message) => <article className={message.role === "user" ? styles.userMessage : styles.assistantMessage} key={message.id}><strong>{message.role === "user" ? "You" : "GafferTalk"}</strong><p>{message.content}</p><small>{timestamp(message.created_at)}</small></article>) : <p>No messages saved yet.</p>}</section>
        </div>
      </div>
    </main>
  );
}

export function ProWorkspaceExperience() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<ProWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingState, setEditingState] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    loadProWorkspace(controller.signal).then(setWorkspace).catch((caught) => {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      if (caught instanceof ProWorkspaceApiError && caught.status === 401) {
        router.replace("/pro/sign-in");
        return;
      }
      setError(caught instanceof Error ? caught.message : "Your workspace could not be loaded.");
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, [router]);

  const signOut = async () => {
    await createSupabaseBrowserClient().auth.signOut();
    router.replace("/pro/sign-in");
    router.refresh();
  };

  return (
    <div className={styles.app}>
      <Header onSignOut={signOut} />
      {loading ? <main className={styles.loading}>Opening your saved workspace…</main> : null}
      {!loading && error ? <main className={styles.failure}><h1>Workspace unavailable.</h1><p>{error}</p><button type="button" onClick={() => window.location.reload()}>Try again</button></main> : null}
      {!loading && !error && workspace && (!workspace.current_state || editingState) ? <TeamOnboarding initialTeamId={workspace.current_state?.team_id} onConfirmed={(saved) => { setWorkspace(saved); setEditingState(false); }} /> : null}
      {!loading && !error && workspace?.current_state && !editingState ? <WorkspaceDashboard workspace={workspace} setWorkspace={setWorkspace} onReconfirm={() => setEditingState(true)} /> : null}
    </div>
  );
}
