"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  CurrentTeamApiError,
  loadDemoSquad,
  recommendTransfer,
  type ApiPlayer,
  type CurrentSquadRequest,
  type Recommendation,
  type RecommendationResult,
  type RecommendationStrategy,
} from "@/lib/current-team-api";
import {
  applyRecommendationToSquad,
  parseSavedRecommendationSquad,
  RECOMMENDATION_STORAGE_KEY,
} from "@/lib/free-recommendation-state";
import styles from "./recommendation.module.css";

type QuickAction = {
  id: RecommendationStrategy;
  number: string;
  title: string;
  description: string;
  weights: string;
};

const quickActions: QuickAction[] = [
  {
    id: "balanced",
    number: "01",
    title: "Best all-rounder",
    description: "Balance proven output, the next five fixtures and price.",
    weights: "45% output · 35% fixtures · 20% value",
  },
  {
    id: "fixture_first",
    number: "02",
    title: "Attack the fixtures",
    description: "Lean into the strongest immediate run without ignoring output.",
    weights: "25% output · 60% fixtures · 15% value",
  },
  {
    id: "value_first",
    number: "03",
    title: "Stretch the budget",
    description: "Prioritise points per £m and leave more money in the bank.",
    weights: "25% output · 20% fixtures · 55% value",
  },
];

function money(tenths: number) {
  return `£${(tenths / 10).toFixed(1)}m`;
}

function actionName(strategy: RecommendationStrategy): string {
  return quickActions.find((action) => action.id === strategy)?.title ?? "Quick Action";
}

function defaultPlayer(nextPlayers: ApiPlayer[]): ApiPlayer {
  return (
    nextPlayers.find((player) => player.web_name === "Yates") ??
    nextPlayers.find((player) => player.position === "MID") ??
    nextPlayers[0]
  );
}

export function RecommendationExperience() {
  const [squad, setSquad] = useState<CurrentSquadRequest | null>(null);
  const [players, setPlayers] = useState<ApiPlayer[]>([]);
  const [outgoingId, setOutgoingId] = useState(0);
  const [sellingPrice, setSellingPrice] = useState(0);
  const [strategy, setStrategy] = useState<RecommendationStrategy>("balanced");
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const installSquad = useCallback((nextSquad: CurrentSquadRequest, nextPlayers: ApiPlayer[]) => {
    const selected = defaultPlayer(nextPlayers);
    setSquad(nextSquad);
    setPlayers(nextPlayers);
    setOutgoingId(selected.id);
    setSellingPrice(selected.current_price.tenths);
    setResult(null);
    setError("");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const confirmed = parseSavedRecommendationSquad(
      window.localStorage.getItem(RECOMMENDATION_STORAGE_KEY),
    );
    if (confirmed) {
      Promise.resolve().then(() => {
        installSquad(confirmed.squad, confirmed.players);
        setIsLoading(false);
      });
      return () => controller.abort();
    }
    loadDemoSquad(controller.signal)
      .then((demo) => installSquad(demo.squad, demo.players))
      .catch((caught) => {
        if (!(caught instanceof DOMException) || caught.name !== "AbortError") {
          setError("The live demo squad could not be loaded. Start the API and try again.");
        }
      })
      .finally(() => setIsLoading(false));
    return () => controller.abort();
  }, [installSquad]);

  const outgoing = useMemo(
    () => players.find((player) => player.id === outgoingId),
    [outgoingId, players],
  );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!squad || !outgoing) return;
    setIsLoading(true);
    setError("");
    setNotice("");
    setResult(null);
    try {
      const recommendation = await recommendTransfer({
        squad,
        outgoing_player_id: outgoing.id,
        outgoing_selling_price_tenths: sellingPrice,
        strategy,
      });
      setResult(recommendation);
    } catch (caught) {
      setError(
        caught instanceof CurrentTeamApiError
          ? caught.message
          : "GafferTalk could not complete that recommendation.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const addToPlan = (recommendation: Recommendation) => {
    if (!squad || !outgoing) return;
    try {
      const next = applyRecommendationToSquad(
        { squad, players },
        outgoing.id,
        recommendation,
      );
      window.localStorage.setItem(RECOMMENDATION_STORAGE_KEY, JSON.stringify(next));
      setSquad(next.squad);
      setPlayers(next.players);
      setOutgoingId(recommendation.incoming.id);
      setSellingPrice(recommendation.incoming.current_price.tenths);
      setResult(null);
      setError("");
      setNotice(
        `${outgoing.web_name} → ${recommendation.incoming.web_name} added to this device’s plan. ` +
          `${money(recommendation.remaining_bank.tenths)} remains in the bank.`,
      );
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That option could not be added.");
    }
  };

  const resetDemo = async () => {
    setIsLoading(true);
    setError("");
    setNotice("");
    window.localStorage.removeItem(RECOMMENDATION_STORAGE_KEY);
    try {
      const demo = await loadDemoSquad();
      installSquad(demo.squad, demo.players);
      setNotice("The original synthetic squad has been restored.");
    } catch {
      setError("The demo squad could not be restored.");
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading && !squad) {
    return <main className={styles.loading}>Loading today’s FPL data…</main>;
  }

  return (
    <main className={styles.app}>
      <header className={styles.header}>
        <Link href="/" className={styles.wordmark}>
          GafferTalk<span>.</span>
        </Link>
        <div>
          <span>Free beta</span><i />
          <b>{squad?.name === "GafferTalk Synthetic XI" ? "Synthetic squad" : "Confirmed squad"}</b>
        </div>
        <Link href="/team">Use my Team ID</Link>
      </header>

      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>Three Quick Actions · no AI credits required</p>
          <h1>Pick the job.<br /><em>Get the shortlist.</em></h1>
          <p>
            Choose the player you are considering selling. GafferTalk checks live prices,
            fixtures, availability, budget and FPL squad rules before ranking three options.
          </p>
        </div>
        <aside>
          <span>Current planning state</span>
          <strong>{squad?.name ?? "Unavailable"}</strong>
          <dl>
            <div><dt>Bank</dt><dd>{money(squad?.bank_tenths ?? 0)}</dd></div>
            <div><dt>Free transfers</dt><dd>{squad?.free_transfers ?? 0}</dd></div>
            <div><dt>Players</dt><dd>{players.length}</dd></div>
          </dl>
          <button type="button" onClick={resetDemo} disabled={isLoading}>Reset demo squad</button>
        </aside>
      </section>

      {notice ? <p className={styles.notice} role="status">✓ {notice}</p> : null}

      <form className={styles.flow} onSubmit={submit}>
        <section className={styles.setupPanel}>
          <div className={styles.panelHeading}>
            <span>01</span><div><small>Your squad</small><h2>Choose who could go</h2></div>
          </div>
          <label htmlFor="outgoing">Player to replace</label>
          <select
            id="outgoing"
            value={outgoingId}
            onChange={(event) => {
              const id = Number(event.target.value);
              const player = players.find((item) => item.id === id);
              setOutgoingId(id);
              if (player) setSellingPrice(player.current_price.tenths);
              setResult(null);
              setNotice("");
            }}
          >
            {players.map((player) => (
              <option value={player.id} key={player.id}>
                {player.web_name} · {player.position} · {player.club.short_name} · {money(player.current_price.tenths)}
              </option>
            ))}
          </select>
          <label htmlFor="selling-price">Your selling price</label>
          <div className={styles.priceInput}>
            <span>£</span>
            <input
              id="selling-price"
              type="number"
              min="3.5"
              max={(outgoing?.current_price.tenths ?? 300) / 10}
              step="0.1"
              required
              value={(sellingPrice / 10).toFixed(1)}
              onChange={(event) => setSellingPrice(Math.round(Number(event.target.value) * 10))}
            />
            <span>m</span>
          </div>
          <p className={styles.fieldHelp}>
            FPL’s public feed does not expose your private selling price during an open Gameweek.
          </p>
        </section>

        <fieldset className={styles.actionPanel}>
          <legend><span>02</span><div><small>Quick Action</small><strong>What should we optimise?</strong></div></legend>
          <div className={styles.actionGrid}>
            {quickActions.map((action) => (
              <label
                className={`${styles.actionCard} ${strategy === action.id ? styles.selectedAction : ""}`}
                key={action.id}
              >
                <input
                  type="radio"
                  name="strategy"
                  value={action.id}
                  checked={strategy === action.id}
                  onChange={() => {
                    setStrategy(action.id);
                    setResult(null);
                  }}
                />
                <span>{action.number}</span>
                <strong>{action.title}</strong>
                <p>{action.description}</p>
                <small>{action.weights}</small>
              </label>
            ))}
          </div>
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
          <button className={styles.primary} disabled={isLoading || !squad || !outgoing}>
            {isLoading ? "Doing the homework…" : `Run ${actionName(strategy)}`}
          </button>
          <small className={styles.security}>Deterministic engine only. No prompt, Groq call or FPL password.</small>
        </fieldset>
      </form>

      <section className={styles.results} aria-live="polite">
        <div className={styles.panelHeading}>
          <span>03</span><div><small>Legal shortlist</small><h2>Compare the trade-offs</h2></div>
          {result ? <b>{actionName(result.strategy)}</b> : null}
        </div>
        {!result ? (
          <div className={styles.empty}>
            <strong>One player.<br />One Quick Action.</strong>
            <p>The engine will return up to three legal options with the evidence and the catch.</p>
          </div>
        ) : result.recommendations.length === 0 ? (
          <div className={styles.empty}>
            <strong>No legal move found.</strong>
            <p>Try another outgoing player. GafferTalk will never pad the list with an illegal or unavailable option.</p>
          </div>
        ) : (
          <>
            <div className={styles.cards}>
              {result.recommendations.map((item) => (
                <article className={styles.card} key={item.incoming.id}>
                  <header>
                    <span>#{item.rank}</span>
                    <div><strong>{item.incoming.web_name}</strong><small>{item.incoming.club.short_name} · {item.incoming.position}</small></div>
                    <b>{item.score.toFixed(1)}</b>
                  </header>
                  <div className={styles.metrics}>
                    <div><span>Price</span><strong>{money(item.incoming.current_price.tenths)}</strong></div>
                    <div><span>Bank after</span><strong>{money(item.remaining_bank.tenths)}</strong></div>
                    <div><span>Fixture avg.</span><strong>{item.average_fixture_difficulty?.toFixed(2) ?? "—"}</strong></div>
                    <div><span>Transfer cost</span><strong>{item.points_hit ? `−${item.points_hit} pts` : "Free"}</strong></div>
                  </div>
                  <p>{item.reasons[1]}</p>
                  <footer><div><span>The catch</span>{item.trade_off}</div><button type="button" onClick={() => addToPlan(item)}>Add to my plan</button></footer>
                </article>
              ))}
            </div>
            <details className={styles.assumptions}>
              <summary>How this shortlist was calculated</summary>
              <ul>{result.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
            </details>
            <p className={styles.disclaimer}>Adding a move updates this browser only. GafferTalk never changes your official FPL team.</p>
          </>
        )}
      </section>

      <aside className={styles.proTeaser}>
        <span>Coming later · GafferTalk Pro</span>
        <div><strong>Want to ask your own question?</strong><p>Conversational planning, richer context and follow-up questions will live in Pro. The free engine stays useful without an LLM.</p></div>
      </aside>

      <footer className={styles.footer}><span>GafferTalk does the homework.</span><b>You make the call.</b></footer>
    </main>
  );
}
