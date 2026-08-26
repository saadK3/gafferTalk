"use client";

import Link from "next/link";
import { type FormEvent, useMemo, useState, useSyncExternalStore } from "react";
import {
  CurrentTeamApiError,
  researchRoute,
  searchPlayers,
  type ApiPlayer,
  type Position,
  type RiskPreference,
  type RouteResearchResponse,
  type TransferRouteCandidate,
} from "@/lib/current-team-api";
import {
  parseSavedRecommendationSquad,
  RECOMMENDATION_STORAGE_KEY,
  type SavedRecommendationSquad,
} from "@/lib/free-recommendation-state";
import {
  parseSellingPriceSession,
  PRO_SELLING_PRICE_SESSION_KEY,
  serializeSellingPriceSession,
} from "@/lib/pro-selling-price-state";
import styles from "../pro.module.css";

function money(tenths: number) {
  return `£${(tenths / 10).toFixed(1)}m`;
}

function subscribeToBrowserReady() {
  return () => undefined;
}

function routeName(route: TransferRouteCandidate) {
  return route.transfers
    .map((transfer) => `${transfer.outgoing.web_name} → ${transfer.incoming.web_name}`)
    .join(" · ");
}

export function ProRouteExperience() {
  const browserReady = useSyncExternalStore(subscribeToBrowserReady, () => true, () => false);
  const saved = useMemo<SavedRecommendationSquad | null>(() => {
    if (!browserReady) return null;
    return parseSavedRecommendationSquad(window.localStorage.getItem(RECOMMENDATION_STORAGE_KEY));
  }, [browserReady]);
  const cachedPrices = useMemo(() => {
    if (!browserReady || !saved) return {};
    return parseSellingPriceSession(
      window.sessionStorage.getItem(PRO_SELLING_PRICE_SESSION_KEY),
      saved.squad.player_ids,
    );
  }, [browserReady, saved]);
  const [targetPosition, setTargetPosition] = useState<Position>("FWD");
  const [targetQuery, setTargetQuery] = useState("");
  const [target, setTarget] = useState<ApiPlayer | null>(null);
  const [candidates, setCandidates] = useState<ApiPlayer[]>([]);
  const [preserved, setPreserved] = useState<number[]>([]);
  const [excluded, setExcluded] = useState<number[]>([]);
  const [minimumBank, setMinimumBank] = useState(0);
  const [maximumTransfers, setMaximumTransfers] = useState<1 | 2>(2);
  const [risk, setRisk] = useState<RiskPreference>("balanced");
  const [proceed, setProceed] = useState(false);
  const [question, setQuestion] = useState("How can I reach this target in no more than two transfers?");
  const [confirmedPrices, setConfirmedPrices] = useState<Record<number, number>>({});
  const [priceEntries, setPriceEntries] = useState<Record<number, string>>({});
  const [result, setResult] = useState<RouteResearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const effectivePrices = useMemo(
    () => ({ ...cachedPrices, ...confirmedPrices }),
    [cachedPrices, confirmedPrices],
  );

  const findTarget = async () => {
    if (targetQuery.trim().length < 2) return;
    setSearching(true);
    setError("");
    try {
      const players = await searchPlayers(targetPosition, targetQuery.trim());
      const owned = new Set(saved?.squad.player_ids ?? []);
      setCandidates(players.filter((player) => !owned.has(player.id)).slice(0, 8));
    } catch {
      setError("Player search is unavailable. Try again shortly.");
    } finally {
      setSearching(false);
    }
  };

  const runResearch = async (prices: Record<number, number>) => {
    if (!saved || !target) return;
    setLoading(true);
    setError("");
    try {
      const next = await researchRoute({
        squad: saved.squad,
        target_player_id: target.id,
        preserved_player_ids: preserved,
        excluded_player_ids: excluded,
        minimum_remaining_bank_tenths: minimumBank,
        maximum_transfers: maximumTransfers,
        selling_prices_tenths: prices,
        risk_preference: risk,
        proceed_if_discouraged: proceed,
        question,
      });
      setResult(next);
      setPriceEntries(Object.fromEntries(
        next.report.requested_selling_prices_for.map((player) => [
          player.id,
          ((prices[player.id] ?? player.current_price.tenths) / 10).toFixed(1),
        ]),
      ));
    } catch (caught) {
      setError(caught instanceof CurrentTeamApiError
        ? caught.message
        : "The route report could not be completed. Try again shortly.");
    } finally {
      setLoading(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setResult(null);
    await runResearch(effectivePrices);
  };

  const confirmPrices = async () => {
    if (!saved || !result) return;
    const next = { ...effectivePrices };
    for (const player of result.report.requested_selling_prices_for) {
      const tenths = Math.round(Number(priceEntries[player.id]) * 10);
      if (!Number.isInteger(tenths) || tenths < 0 || tenths > player.current_price.tenths) {
        setError(`Enter ${player.web_name}'s selling price, no higher than ${money(player.current_price.tenths)}.`);
        return;
      }
      next[player.id] = tenths;
    }
    window.sessionStorage.setItem(
      PRO_SELLING_PRICE_SESSION_KEY,
      serializeSellingPriceSession(saved.squad.player_ids, next),
    );
    setConfirmedPrices(next);
    await runResearch(next);
  };

  const toggleConstraint = (playerId: number, kind: "preserve" | "exclude") => {
    if (kind === "preserve") {
      setPreserved((current) => current.includes(playerId)
        ? current.filter((id) => id !== playerId)
        : [...current, playerId]);
      setExcluded((current) => current.filter((id) => id !== playerId));
    } else {
      setExcluded((current) => current.includes(playerId)
        ? current.filter((id) => id !== playerId)
        : [...current, playerId]);
      setPreserved((current) => current.filter((id) => id !== playerId));
    }
    setResult(null);
  };

  if (!browserReady) return <main className={styles.loading}>Loading confirmed squad…</main>;
  if (!saved) {
    return (
      <main className={styles.emptyState}>
        <Link href="/" className={styles.wordmark}>GafferTalk<span>.</span></Link>
        <p>Route research needs a confirmed planning state.</p>
        <h1>Bring your squad<br />into the room.</h1>
        <Link href="/team" className={styles.primaryLink}>Confirm my team</Link>
      </main>
    );
  }

  const report = result?.report;
  const route = report?.recommended_route ?? report?.provisional_route;
  return (
    <main className={styles.app}>
      <header className={styles.header}>
        <Link href="/" className={styles.wordmark}>GafferTalk<span>.</span></Link>
        <nav className={styles.modeNav} aria-label="Pro research modes">
          <Link href="/pro">Named transfer</Link>
          <Link href="/pro/squad-action">Best squad action</Link>
          <Link href="/pro/routes" aria-current="page">Route finder</Link>
        </nav>
        <Link href="/pro/workspace">Signed-in workspace</Link>
      </header>

      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>A target is a constraint, not automatically the best decision.</p>
          <h1>Find the route.<br /><em>Price the sacrifice.</em></h1>
          <p>Search one or two transfers, protect players you refuse to sell, and see the exact hit, bank and strategic verdict.</p>
        </div>
        <aside><span>Confirmed planning state</span><strong>{saved.squad.name}</strong><dl><div><dt>Bank</dt><dd>{money(saved.squad.bank_tenths)}</dd></div><div><dt>Free transfers</dt><dd>{saved.squad.free_transfers}</dd></div><div><dt>Players</dt><dd>15</dd></div></dl></aside>
      </section>

      <form className={`${styles.researchForm} ${styles.routeForm}`} onSubmit={submit}>
        <section>
          <span className={styles.step}>01</span>
          <label htmlFor="route-position">Target position</label>
          <select id="route-position" value={targetPosition} onChange={(event) => { setTargetPosition(event.target.value as Position); setTarget(null); setCandidates([]); }}>
            <option value="GKP">Goalkeeper</option><option value="DEF">Defender</option><option value="MID">Midfielder</option><option value="FWD">Forward</option>
          </select>
          <label htmlFor="route-target">Named target</label>
          <div className={styles.searchRow}>
            <input id="route-target" value={targetQuery} onChange={(event) => { setTargetQuery(event.target.value); setTarget(null); setCandidates([]); }} placeholder="Search current FPL players" />
            <button type="button" onClick={findTarget} disabled={searching || targetQuery.trim().length < 2}>{searching ? "Searching…" : "Search"}</button>
          </div>
          {candidates.length ? <div className={styles.routeCandidates}>{candidates.map((player) => <button type="button" key={player.id} onClick={() => { setTarget(player); setTargetQuery(player.web_name); setCandidates([]); setQuestion(`How can I get ${player.web_name} in no more than ${maximumTransfers} transfers?`); }}><strong>{player.web_name}</strong><span>{player.club.short_name} · {money(player.current_price.tenths)}</span></button>)}</div> : null}
          {target ? <p className={styles.selected}>Target: {target.web_name} · {target.club.short_name} · {money(target.current_price.tenths)}</p> : null}
          <div className={styles.routeSettings}>
            <label>Maximum transfers<select value={maximumTransfers} onChange={(event) => setMaximumTransfers(Number(event.target.value) as 1 | 2)}><option value="1">One</option><option value="2">Two</option></select></label>
            <label>Keep in bank (£m)<input type="number" min="0" max="20" step="0.1" value={(minimumBank / 10).toFixed(1)} onChange={(event) => setMinimumBank(Math.round(Number(event.target.value) * 10))} /></label>
            <label>Decision style<select value={risk} onChange={(event) => setRisk(event.target.value as RiskPreference)}><option value="safe">Safe</option><option value="balanced">Balanced</option><option value="aggressive">Aggressive</option></select></label>
          </div>
        </section>
        <section>
          <span className={styles.step}>02</span>
          <h2>Squad constraints</h2>
          <p className={styles.formIntro}>Mark a player “keep” to protect them or “sell” to require that they leave. At most two owned players can be required sales.</p>
          <div className={styles.constraintGrid}>
            {saved.players.map((player) => <div key={player.id}><strong>{player.web_name}</strong><span>{player.position}</span><label><input aria-label={`Keep ${player.web_name}`} type="checkbox" checked={preserved.includes(player.id)} onChange={() => toggleConstraint(player.id, "preserve")} /> Keep</label><label><input aria-label={`Sell ${player.web_name}`} type="checkbox" checked={excluded.includes(player.id)} onChange={() => toggleConstraint(player.id, "exclude")} disabled={!excluded.includes(player.id) && excluded.length >= 2} /> Sell</label></div>)}
          </div>
          <label htmlFor="route-question">Your route question</label>
          <textarea id="route-question" minLength={3} maxLength={500} value={question} onChange={(event) => setQuestion(event.target.value)} required />
          <label className={styles.override}><input type="checkbox" checked={proceed} onChange={(event) => setProceed(event.target.checked)} /> Show the strongest legal route even when GafferTalk discourages it.</label>
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
          <button className={styles.submit} disabled={loading || !target || question.trim().length < 3}>{loading ? "Searching bounded routes…" : "Find my route"}</button>
        </section>
      </form>

      <section className={styles.report} aria-live="polite">
        {!report || !result ? <div className={styles.reportEmpty}><span>03 · Route report</span><strong>One target.<br />Every sacrifice priced.</strong><p>The engine will enumerate bounded routes and ask only for selling prices that can affect the result.</p></div> : (
          <>
            <header className={`${styles.reportHeader} ${styles.routeReportHeader}`}><div><span>{report.status.replaceAll("_", " ")} · policy {report.decision_policy_version}</span><h2>{report.status === "needs_selling_prices" ? "Check prices" : report.verdict.replaceAll("_", " ")}</h2></div><p>{route ? routeName(route) : `No route to ${report.target.web_name}`}</p><b className={`${styles.confidence} ${styles[report.confidence.level]}`}>{report.confidence.level} confidence</b></header>
            <div className={styles.answer}><span>GafferTalk says</span><p>{result.assistant_message}</p></div>
            {report.status === "needs_selling_prices" ? <section className={styles.priceRequest}><div><span>Exact validation needed</span><h3>Confirm the proposed sales</h3><p>These are the only private prices needed for the current leading route.</p></div><div className={styles.routePriceInputs}>{report.requested_selling_prices_for.map((player) => <label key={player.id}>{player.web_name} (£m)<input aria-label={`${player.web_name} selling price`} type="number" min="0" max={(player.current_price.tenths / 10).toFixed(1)} step="0.1" value={priceEntries[player.id] ?? ""} onChange={(event) => setPriceEntries((current) => ({ ...current, [player.id]: event.target.value }))} /></label>)}</div><button type="button" className={styles.submit} onClick={confirmPrices} disabled={loading}>{loading ? "Validating…" : "Confirm and validate"}</button></section> : null}
            <div className={styles.decisionGrid}><article><span>Strategic verdict</span><strong>{report.verdict.replaceAll("_", " ")}</strong><p>{report.strategic_explanation}</p></article><article><span>Opportunity cost</span><strong>{route ? `${money(route.remaining_bank.tenths)} · ${route.points_hit ? `−${route.points_hit} points` : "no hit"}` : "No action"}</strong><p>{report.opportunity_cost}</p></article><article><span>Constraints honored</span><strong>{report.constraints.preserved_players.length} kept · {report.constraints.excluded_players.length} sold</strong><p>Minimum bank {money(report.constraints.minimum_remaining_bank.tenths)} · maximum {report.constraints.maximum_transfers} transfers.</p></article><article><span>Search boundary</span><strong>{report.search_stats.routes_examined} routes checked</strong><p>{report.search_stats.elapsed_milliseconds.toFixed(1)}ms deterministic search · {report.search_stats.candidate_limit_per_position} secondary candidates per position.</p></article></div>
            {route ? <section className={styles.evidence}><div><span>{route.budget_status} route</span><h3>{routeName(route)}</h3></div><div className={styles.routeLegs}>{route.transfers.map((transfer) => <article key={`${transfer.outgoing.id}-${transfer.incoming.id}`}><strong>{transfer.outgoing.web_name} → {transfer.incoming.web_name}</strong><p>{transfer.outgoing.position} · sell {transfer.confirmed_selling_price ? money(transfer.confirmed_selling_price.tenths) : "price required"} · buy {money(transfer.incoming.current_price.tenths)}</p></article>)}</div><p>{route.explanation}</p></section> : null}
            {report.alternatives.length ? <section className={styles.evidence}><div><span>Compared routes</span><h3>Other supported paths</h3></div><div className={styles.actionList}>{report.alternatives.map((alternative) => <article key={routeName(alternative)}><span>{alternative.budget_status}</span><strong>{routeName(alternative)}</strong><p>{alternative.explanation}</p><small>{alternative.policy_adjusted_gain.toFixed(1)} adjusted gain · {money(alternative.remaining_bank.tenths)} left</small></article>)}</div></section> : null}
            <div className={styles.detailGrid}><details open><summary>Confidence reasons</summary><ul>{report.confidence.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></details><details open><summary>Assumptions and limits</summary><ul>{report.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></details></div>
          </>
        )}
      </section>
    </main>
  );
}
