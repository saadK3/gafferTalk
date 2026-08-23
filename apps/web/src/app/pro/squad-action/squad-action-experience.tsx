"use client";

import Link from "next/link";
import { type FormEvent, useMemo, useState, useSyncExternalStore } from "react";
import {
  CurrentTeamApiError,
  researchSquadAction,
  type RiskPreference,
  type SquadActionResearchResponse,
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

export function ProSquadActionExperience() {
  const browserReady = useSyncExternalStore(subscribeToBrowserReady, () => true, () => false);
  const saved = useMemo<SavedRecommendationSquad | null>(() => {
    if (!browserReady) return null;
    return parseSavedRecommendationSquad(window.localStorage.getItem(RECOMMENDATION_STORAGE_KEY));
  }, [browserReady]);
  const [risk, setRisk] = useState<RiskPreference>("balanced");
  const [question, setQuestion] = useState("What should I do with my transfer this week?");
  const [confirmedPrices, setConfirmedPrices] = useState<Record<number, number>>({});
  const [priceEntry, setPriceEntry] = useState("");
  const [result, setResult] = useState<SquadActionResearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const cachedPrices = useMemo(() => {
    if (!browserReady || !saved) return {};
    return parseSellingPriceSession(
      window.sessionStorage.getItem(PRO_SELLING_PRICE_SESSION_KEY),
      saved.squad.player_ids,
    );
  }, [browserReady, saved]);
  const effectiveConfirmedPrices = useMemo(
    () => ({ ...cachedPrices, ...confirmedPrices }),
    [cachedPrices, confirmedPrices],
  );

  const runResearch = async (prices: Record<number, number>) => {
    if (!saved) return;
    setLoading(true);
    setError("");
    try {
      const nextResult = await researchSquadAction({
        squad: saved.squad,
        selling_prices_tenths: prices,
        risk_preference: risk,
        question,
      });
      setResult(nextResult);
      const nextRequested = nextResult.report.requested_selling_price_for;
      if (nextRequested) {
        const known = prices[nextRequested.id];
        setPriceEntry(((known ?? nextRequested.current_price.tenths) / 10).toFixed(1));
      }
    } catch (caught) {
      setError(caught instanceof CurrentTeamApiError
        ? caught.message
        : "The whole-squad report could not be completed. Try again shortly.");
    } finally {
      setLoading(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!saved) return;
    setResult(null);
    await runResearch(effectiveConfirmedPrices);
  };

  const requestedPlayer = result?.report.requested_selling_price_for ?? null;
  const confirmRequestedPrice = async () => {
    if (!saved || !requestedPlayer) return;
    const tenths = Math.round(Number(priceEntry) * 10);
    if (!Number.isInteger(tenths) || tenths < 0 || tenths > requestedPlayer.current_price.tenths) {
      setError(`Enter ${requestedPlayer.web_name}'s actual selling price, no higher than ${money(requestedPlayer.current_price.tenths)}.`);
      return;
    }
    const nextPrices = { ...effectiveConfirmedPrices, [requestedPlayer.id]: tenths };
    window.sessionStorage.setItem(
      PRO_SELLING_PRICE_SESSION_KEY,
      serializeSellingPriceSession(saved.squad.player_ids, nextPrices),
    );
    setConfirmedPrices(nextPrices);
    await runResearch(nextPrices);
  };

  if (!browserReady) return <main className={styles.loading}>Loading confirmed squad…</main>;
  if (!saved) {
    return (
      <main className={styles.emptyState}>
        <Link href="/" className={styles.wordmark}>GafferTalk<span>.</span></Link>
        <p>Whole-squad research needs a confirmed planning state.</p>
        <h1>Bring your squad<br />into the room.</h1>
        <p>Load your latest squad, then confirm the bank and free transfers.</p>
        <Link href="/team" className={styles.primaryLink}>Confirm my team</Link>
      </main>
    );
  }

  const report = result?.report;
  const action = report?.recommended_action ?? report?.provisional_action;
  const isPreliminary = report?.status === "needs_selling_price";
  return (
    <main className={styles.app}>
      <header className={styles.header}>
        <Link href="/" className={styles.wordmark}>GafferTalk<span>.</span></Link>
        <nav className={styles.modeNav} aria-label="Pro research modes">
          <Link href="/pro">Named transfer</Link>
          <Link href="/pro/squad-action" aria-current="page">Best squad action</Link>
        </nav>
        <Link href="/team">Reconfirm team</Link>
      </header>

      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>Pro scans the whole squad before recommending a move.</p>
          <h1>Act now.<br /><em>Or keep your powder dry.</em></h1>
          <p>Rank all 15 squad concerns, screen one-transfer routes against rolling, and ask for a selling price only when it can change the answer.</p>
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

      <form className={`${styles.researchForm} ${styles.actionForm}`} onSubmit={submit}>
        <section>
          <span className={styles.step}>01</span>
          <label htmlFor="risk-policy">Decision style</label>
          <select id="risk-policy" value={risk} onChange={(event) => { setRisk(event.target.value as RiskPreference); setResult(null); }}>
            <option value="safe">Safe · demand a larger advantage</option>
            <option value="balanced">Balanced · standard thresholds</option>
            <option value="aggressive">Aggressive · act on smaller advantages</option>
          </select>
          <label htmlFor="squad-question">Your question</label>
          <textarea id="squad-question" minLength={3} maxLength={500} value={question} onChange={(event) => setQuestion(event.target.value)} required />
          <small>The style changes documented thresholds and hit penalties. It never relaxes legality.</small>
        </section>
        <section>
          <span className={styles.step}>02</span>
          <h2>Analyze first, confirm only what matters</h2>
          <p className={styles.formIntro}>The first pass uses current FPL prices only as an optimistic ceiling. A transfer is never called affordable or legal until the outgoing player’s actual selling price is confirmed.</p>
          <ol className={styles.workflowList}>
            <li>Diagnose the whole squad and compare likely routes with rolling.</li>
            <li>If rolling already wins, finish without asking for any selling price.</li>
            <li>If a move looks worthwhile, validate only its outgoing player’s price.</li>
          </ol>
          {Object.keys(effectiveConfirmedPrices).length ? <small>{Object.keys(effectiveConfirmedPrices).length} relevant selling price{Object.keys(effectiveConfirmedPrices).length === 1 ? "" : "s"} remembered for this browser session.</small> : null}
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
          <button className={styles.submit} disabled={loading || question.trim().length < 3}>
            {loading ? "Ranking the whole squad…" : "Analyze my squad"}
          </button>
        </section>
      </form>

      <section className={styles.report} aria-live="polite">
        {!report || !result || !action ? (
          <div className={styles.reportEmpty}>
            <span>03 · Whole-squad decision</span>
            <strong>Transfer, roll,<br />or take the hit?</strong>
            <p>The engine will rank concerns and compare its strongest provisional routes with doing nothing, then validate only the price it needs.</p>
          </div>
        ) : (
          <>
            <header className={styles.reportHeader}>
              <div><span>{isPreliminary ? "Preliminary screen" : "Final decision"} · policy {report.decision_policy_version}</span><h2>{isPreliminary ? "Check price" : action.action}</h2></div>
              <p>{action.outgoing && action.incoming ? `${action.outgoing.web_name} → ${action.incoming.web_name}` : "Save the transfer"}</p>
              <b className={`${styles.confidence} ${styles[report.confidence.level]}`}>{report.confidence.level} confidence</b>
            </header>
            <div className={styles.answer}><span>GafferTalk says</span><p>{result.assistant_message}</p></div>
            {isPreliminary && requestedPlayer ? (
              <section className={styles.priceRequest} aria-labelledby="price-request-title">
                <div>
                  <span>One detail needed</span>
                  <h3 id="price-request-title">Confirm {requestedPlayer.web_name}&apos;s selling price</h3>
                  <p>The provisional {action.outgoing?.web_name} → {action.incoming?.web_name} route cleared the decision threshold using {money(requestedPlayer.current_price.tenths)} as the maximum possible sale value. Enter the price shown on FPL&apos;s transfer screen to run exact budget and legality checks.</p>
                </div>
                <label htmlFor="requested-selling-price">
                  Selling price (£m)
                  <input
                    id="requested-selling-price"
                    type="number"
                    min="0"
                    max={(requestedPlayer.current_price.tenths / 10).toFixed(1)}
                    step="0.1"
                    value={priceEntry}
                    onChange={(event) => setPriceEntry(event.target.value)}
                  />
                </label>
                <button type="button" className={styles.submit} disabled={loading || !priceEntry} onClick={confirmRequestedPrice}>
                  {loading ? "Validating route…" : "Confirm price and validate"}
                </button>
              </section>
            ) : null}
            <div className={styles.decisionGrid}>
              <article><span>Leading squad priority</span><strong>{report.ranked_concerns[0].player.web_name}</strong><p>{report.priority_explanation}</p></article>
              <article className={report.hit_analysis.points_hit && !report.hit_analysis.justified ? styles.warning : ""}><span>Hit test</span><strong>{report.hit_analysis.points_hit ? `${report.hit_analysis.justified ? "Justified" : "Avoid"} −${report.hit_analysis.points_hit}` : "No hit required"}</strong><p>{report.hit_analysis.comparison}</p></article>
              <article><span>Opportunity cost</span><strong>{money(action.remaining_bank.tenths)} · {action.free_transfers_after} FT after</strong><p>{action.explanation}</p></article>
              <article><span>Planning impact</span><strong>{report.risk_preference} policy</strong><p>{report.planning_impact}</p></article>
            </div>
            <section className={styles.evidence}>
              <div><span>Squad priorities</span><h3>What needs attention</h3><small>Roll threshold {report.roll_threshold.toFixed(1)}</small></div>
              <ol className={styles.concernList}>
                {report.ranked_concerns.map((concern) => (
                  <li key={`${concern.player.id}-${concern.kind}`}>
                    <b>{concern.rank}</b><div><strong>{concern.player.web_name}</strong><span>{concern.kind.replaceAll("_", " ")} · {concern.starting_slot ? "starter" : "bench"}</span><p>{concern.explanation}</p></div><em>{concern.priority_score.toFixed(1)}</em>
                  </li>
                ))}
              </ol>
            </section>
            <section className={styles.evidence}>
              <div><span>Compared actions</span><h3>Transfer versus roll</h3></div>
              <div className={styles.actionList}>
                {report.compared_actions.map((candidate, index) => (
                  <article key={`${candidate.action}-${candidate.outgoing?.id ?? "roll"}-${candidate.incoming?.id ?? index}`}>
                    <span>{candidate.action} · {candidate.budget_status.replaceAll("_", " ")}</span>
                    <strong>{candidate.outgoing && candidate.incoming ? `${candidate.outgoing.web_name} → ${candidate.incoming.web_name}` : "Carry the transfer"}</strong>
                    <p>{candidate.explanation}</p>
                    <small>{candidate.policy_adjusted_gain.toFixed(1)} adjusted gain · {candidate.points_hit ? `−${candidate.points_hit} hit` : "no hit"}</small>
                  </article>
                ))}
              </div>
            </section>
            <div className={styles.detailGrid}>
              <details open><summary>Confidence reasons</summary><ul>{report.confidence.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></details>
              <details open><summary>What would change the action</summary><ul>{report.change_conditions.map((condition) => <li key={condition}>{condition}</li>)}</ul></details>
              <details><summary>Assumptions and limits</summary><ul>{report.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></details>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
