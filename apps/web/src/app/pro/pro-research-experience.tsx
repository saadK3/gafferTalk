"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import {
  CurrentTeamApiError,
  researchNamedTransfer,
  searchPlayers,
  type ApiPlayer,
  type NamedTransferResearchResponse,
} from "@/lib/current-team-api";
import {
  parseSavedRecommendationSquad,
  RECOMMENDATION_STORAGE_KEY,
  type SavedRecommendationSquad,
} from "@/lib/free-recommendation-state";
import styles from "./pro.module.css";

const shownMetrics = [
  "total_points",
  "starts",
  "minutes",
  "expected_goal_involvement",
  "points_per_start",
  "xgi_per_90",
];

function money(tenths: number) {
  return `£${(tenths / 10).toFixed(1)}m`;
}

function timestamp(value: string) {
  return `${new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value))} UTC`;
}

function subscribeToBrowserReady() {
  return () => undefined;
}

export function ProResearchExperience() {
  const browserReady = useSyncExternalStore(subscribeToBrowserReady, () => true, () => false);
  const saved = useMemo<SavedRecommendationSquad | null>(() => {
    if (!browserReady) return null;
    return parseSavedRecommendationSquad(
      window.localStorage.getItem(RECOMMENDATION_STORAGE_KEY),
    );
  }, [browserReady]);
  const [outgoingId, setOutgoingId] = useState(0);
  const [sellingPrice, setSellingPrice] = useState(0);
  const [target, setTarget] = useState<ApiPlayer | null>(null);
  const [targetQuery, setTargetQuery] = useState("");
  const [candidates, setCandidates] = useState<ApiPlayer[]>([]);
  const [searching, setSearching] = useState(false);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<NamedTransferResearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const outgoing = useMemo(
    () => saved?.players.find((player) => player.id === outgoingId)
      ?? saved?.players.find((player) => player.position === "MID")
      ?? saved?.players[0]
      ?? null,
    [outgoingId, saved],
  );
  const effectiveSellingPrice = sellingPrice || outgoing?.current_price.tenths || 0;

  useEffect(() => {
    if (!outgoing || targetQuery.trim().length < 2 || target?.web_name === targetQuery) {
      return;
    }
    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setSearching(true);
      try {
        const players = await searchPlayers(outgoing.position, targetQuery.trim(), controller.signal);
        const owned = new Set(saved?.squad.player_ids ?? []);
        setCandidates(players.filter((player) => !owned.has(player.id)).slice(0, 8));
      } catch (caught) {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setError("Player search is unavailable. Try again shortly.");
        }
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [outgoing, saved, target, targetQuery]);

  const chooseOutgoing = (playerId: number) => {
    const player = saved?.players.find((item) => item.id === playerId);
    if (!player) return;
    setOutgoingId(player.id);
    setSellingPrice(player.current_price.tenths);
    setTarget(null);
    setTargetQuery("");
    setQuestion("");
    setResult(null);
    setError("");
  };

  const chooseTarget = (player: ApiPlayer) => {
    setTarget(player);
    setTargetQuery(player.web_name);
    setCandidates([]);
    setQuestion(`Should I sell ${outgoing?.web_name ?? "this player"} for ${player.web_name}?`);
    setResult(null);
    setError("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!saved || !outgoing || !target) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await researchNamedTransfer({
        squad: saved.squad,
        outgoing_player_id: outgoing.id,
        outgoing_selling_price_tenths: effectiveSellingPrice,
        target_player_id: target.id,
        question,
      }));
    } catch (caught) {
      setError(
        caught instanceof CurrentTeamApiError
          ? caught.message
          : "The Pro report could not be completed. Try again shortly.",
      );
    } finally {
      setLoading(false);
    }
  };

  if (!browserReady) return <main className={styles.loading}>Loading confirmed squad…</main>;

  if (!saved) {
    return (
      <main className={styles.emptyState}>
        <Link href="/" className={styles.wordmark}>GafferTalk<span>.</span></Link>
        <p>Pro research needs a confirmed planning state.</p>
        <h1>Bring your squad<br />into the room.</h1>
        <p>Load your latest finalized FPL squad, then confirm transfers, bank and free transfers.</p>
        <Link href="/team" className={styles.primaryLink}>Confirm my team</Link>
      </main>
    );
  }

  const report = result?.report;
  const comparedEvidence = report?.evidence.filter((item) =>
    [report.requested_route.outgoing.id, report.requested_route.incoming.id].includes(item.player.id),
  );

  return (
    <main className={styles.app}>
      <header className={styles.header}>
        <Link href="/" className={styles.wordmark}>GafferTalk<span>.</span></Link>
        <nav className={styles.modeNav} aria-label="Pro research modes">
          <Link href="/pro" aria-current="page">Named transfer</Link>
          <Link href="/pro/squad-action">Best squad action</Link>
          <Link href="/pro/routes">Route finder</Link>
        </nav>
        <Link href="/pro/workspace">Signed-in workspace</Link>
      </header>

      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>Free finds a legal move. Pro investigates the decision.</p>
          <h1>Make the case.<br /><em>Challenge the move.</em></h1>
          <p>Compare buying, holding, waiting and the strongest legal alternative using your whole confirmed squad.</p>
        </div>
        <aside>
          <span>Confirmed planning state</span>
          <strong>{saved.squad.name}</strong>
          <dl>
            <div><dt>Bank</dt><dd>{money(saved.squad.bank_tenths)}</dd></div>
            <div><dt>Free transfers</dt><dd>{saved.squad.free_transfers}</dd></div>
            <div><dt>Players</dt><dd>{saved.players.length}</dd></div>
          </dl>
        </aside>
      </section>

      <form className={styles.researchForm} onSubmit={submit}>
        <section>
          <span className={styles.step}>01</span>
          <label htmlFor="pro-outgoing">Player you may sell</label>
          <select id="pro-outgoing" value={outgoing?.id ?? 0} onChange={(event) => chooseOutgoing(Number(event.target.value))}>
            {saved.players.map((player) => (
              <option key={player.id} value={player.id}>
                {player.web_name} · {player.position} · {money(player.current_price.tenths)}
              </option>
            ))}
          </select>
          <label htmlFor="pro-selling-price">Confirmed selling price</label>
          <div className={styles.priceInput}>
            <span>£</span>
            <input
              id="pro-selling-price"
              type="number"
              min="3.5"
              max={(outgoing?.current_price.tenths ?? 300) / 10}
              step="0.1"
              value={(effectiveSellingPrice / 10).toFixed(1)}
              onChange={(event) => setSellingPrice(Math.round(Number(event.target.value) * 10))}
              required
            />
            <span>m</span>
          </div>
          <small>Exact selling price is user-supplied because FPL does not publish it live.</small>
        </section>

        <section className={styles.targetSection}>
          <span className={styles.step}>02</span>
          <label htmlFor="pro-target">Player you may buy</label>
          <input
            id="pro-target"
            value={targetQuery}
            onChange={(event) => {
              setTargetQuery(event.target.value);
              setTarget(null);
              setCandidates([]);
              setResult(null);
            }}
            placeholder={`Search ${outgoing?.position ?? "same-position"} players`}
            autoComplete="off"
            required
          />
          {searching ? <small>Searching current FPL players…</small> : null}
          {candidates.length ? (
            <div className={styles.candidates}>
              {candidates.map((player) => (
                <button type="button" key={player.id} onClick={() => chooseTarget(player)}>
                  <strong>{player.web_name}</strong>
                  <span>{player.club.short_name} · {money(player.current_price.tenths)} · {player.status === "a" ? "Available" : "Flagged"}</span>
                </button>
              ))}
            </div>
          ) : null}
          {target ? <p className={styles.selected}>Selected: {target.web_name} · {target.club.short_name}</p> : null}
          <label htmlFor="pro-question">Your decision question</label>
          <textarea id="pro-question" minLength={3} maxLength={500} value={question} onChange={(event) => setQuestion(event.target.value)} required />
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
          <button className={styles.submit} disabled={loading || !target || question.trim().length < 3}>
            {loading ? "Investigating the decision…" : "Run Pro research"}
          </button>
        </section>
      </form>

      <section className={styles.report} aria-live="polite">
        {!report || !result ? (
          <div className={styles.reportEmpty}>
            <span>03 · Decision report</span>
            <strong>Not a shortlist.<br />A second opinion.</strong>
            <p>The report will test the requested move against holding, waiting, alternatives and other squad concerns.</p>
          </div>
        ) : (
          <>
            <header className={styles.reportHeader}>
              <div><span>Verdict · {report.schema_version}</span><h2>{report.verdict}</h2></div>
              <p>{report.recommended_action}</p>
              <b className={`${styles.confidence} ${styles[report.confidence.level]}`}>{report.confidence.level} confidence</b>
            </header>
            <div className={styles.answer}><span>GafferTalk says</span><p>{result.assistant_message}</p></div>
            <div className={styles.compared}><span>Compared</span>{report.compared_actions.map((action) => <b key={action}>{action.replaceAll("_", " ")}</b>)}</div>
            <div className={styles.arguments}>
              <article><span>Case for</span><ul>{report.case_for.map((reason) => <li key={reason}>{reason}</li>)}</ul></article>
              <article><span>Case against</span><ul>{report.case_against.map((reason) => <li key={reason}>{reason}</li>)}</ul></article>
            </div>
            <div className={styles.decisionGrid}>
              <article><span>Best alternative</span><strong>{report.best_alternative.player?.web_name ?? report.best_alternative.action}</strong><p>{report.best_alternative.explanation}</p></article>
              <article className={report.squad_priority.more_urgent ? styles.warning : ""}><span>Squad priority</span><strong>{report.squad_priority.more_urgent ? "Another issue comes first" : "No stronger availability issue"}</strong><p>{report.squad_priority.explanation}</p></article>
              <article><span>Opportunity cost</span><strong>{money(report.opportunity_cost.remaining_bank.tenths)} left · {report.opportunity_cost.points_hit ? `−${report.opportunity_cost.points_hit} points` : "no hit"}</strong><p>{report.opportunity_cost.explanation}</p></article>
              <article><span>Three-Gameweek impact</span><strong>{report.opportunity_cost.flexibility} flexibility</strong><p>{report.planning_impact}</p></article>
            </div>
            <section className={styles.evidence}>
              <div><span>Evidence</span><h3>What the verdict used</h3><small>FPL data retrieved {timestamp(report.data_retrieved_at)}</small></div>
              <div className={styles.evidencePlayers}>
                {comparedEvidence?.map((item) => (
                  <article key={item.player.id}>
                    <header><strong>{item.player.web_name}</strong><b>{item.evidence_score.toFixed(1)}</b></header>
                    <p>Next five: {item.next_five.difficulties.join(" · ") || "Unavailable"} · avg {item.next_five.average_difficulty?.toFixed(2) ?? "—"}</p>
                    <dl>
                      {item.metrics.filter((metric) => shownMetrics.includes(metric.key)).map((metric) => (
                        <div key={metric.key}><dt>{metric.label}<small>{metric.provenance}</small></dt><dd>{metric.display_value}</dd></div>
                      ))}
                    </dl>
                  </article>
                ))}
              </div>
            </section>
            <div className={styles.detailGrid}>
              <details open><summary>Confidence reasons</summary><ul>{report.confidence.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></details>
              <details open><summary>What would change the verdict</summary><ul>{report.change_conditions.map((condition) => <li key={condition}>{condition}</li>)}</ul></details>
              <details><summary>Assumptions and limits</summary><ul>{report.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></details>
            </div>
            <p className={styles.freshness}>Report created {timestamp(report.created_at)} · Explanation selected by {result.provider}/{result.model} from backend-approved reasons only.</p>
          </>
        )}
      </section>
    </main>
  );
}
