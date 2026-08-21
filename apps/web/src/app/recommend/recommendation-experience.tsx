"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  askGafferTalk,
  CurrentTeamApiError,
  loadDemoSquad,
  loadFreeUsage,
  type ApiPlayer,
  type CurrentSquadRequest,
  type ConversationOutcome,
  type FreeQuestionQuota,
  type Recommendation,
  type RecommendationResult,
} from "@/lib/current-team-api";
import { getOrCreateFreeClientId } from "@/lib/free-plan";
import {
  applyRecommendationToSquad,
  parseSavedRecommendationSquad,
  RECOMMENDATION_STORAGE_KEY,
} from "@/lib/free-recommendation-state";
import styles from "./recommendation.module.css";

type StarterQuestion = {
  number: string;
  title: string;
  question: (player: string) => string;
};

type SelectionMode = "selected" | "auto";

const starterQuestions: StarterQuestion[] = [
  {
    number: "01",
    title: "Best all-rounder",
    question: (player) => `Who is the best all-round replacement for ${player}?`,
  },
  {
    number: "02",
    title: "Attack the fixtures",
    question: (player) => `Who should replace ${player} if I want to attack the next five fixtures?`,
  },
  {
    number: "03",
    title: "Stretch the budget",
    question: (player) => `What is the best value replacement for ${player} that leaves money in the bank?`,
  },
];

function money(tenths: number) {
  return `£${(tenths / 10).toFixed(1)}m`;
}

function retrievedAt(value: string) {
  return `${new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value))} UTC`;
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
  const [selectionMode, setSelectionMode] = useState<SelectionMode>("selected");
  const [confirmingSuggestedRoute, setConfirmingSuggestedRoute] = useState(false);
  const [sellingPrice, setSellingPrice] = useState(0);
  const [question, setQuestion] = useState("");
  const [assistantMessage, setAssistantMessage] = useState("");
  const [outcome, setOutcome] = useState<ConversationOutcome | null>(null);
  const [clientId, setClientId] = useState("");
  const [quota, setQuota] = useState<FreeQuestionQuota | null>(null);
  const [quotaError, setQuotaError] = useState("");
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const installSquad = useCallback((nextSquad: CurrentSquadRequest, nextPlayers: ApiPlayer[]) => {
    const selected = defaultPlayer(nextPlayers);
    setSquad(nextSquad);
    setPlayers(nextPlayers);
    setOutgoingId(selected.id);
    setSelectionMode("selected");
    setConfirmingSuggestedRoute(false);
    setSellingPrice(selected.current_price.tenths);
    setQuestion(starterQuestions[0].question(selected.web_name));
    setAssistantMessage("");
    setOutcome(null);
    setResult(null);
    setError("");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const browserId = getOrCreateFreeClientId(window.localStorage);
    Promise.resolve().then(() => setClientId(browserId));
    loadFreeUsage(browserId, controller.signal)
      .then(setQuota)
      .catch((caught) => {
        if (!(caught instanceof DOMException) || caught.name !== "AbortError") {
          setQuotaError("Your Free Gameweek allowance could not be loaded. Start the API and try again.");
        }
      });
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
    if (!squad || !clientId || !quota || quota.remaining === 0) return;
    if (selectionMode === "selected" && !outgoing) return;
    setIsLoading(true);
    setError("");
    setNotice("");
    setResult(null);
    setAssistantMessage("");
    setOutcome(null);
    try {
      const response = await askGafferTalk(
        selectionMode === "auto"
          ? { squad, selection_mode: "auto", question }
          : {
              squad,
              selection_mode: "selected",
              outgoing_player_id: outgoing!.id,
              outgoing_selling_price_tenths: sellingPrice,
              question,
            },
        clientId,
      );
      setResult(response.result);
      setAssistantMessage(response.assistant_message);
      setOutcome(response.outcome);
      setQuota(response.quota);
      if (response.outcome === "selling_price_required" && response.suggested_outgoing) {
        setOutgoingId(response.suggested_outgoing.id);
        setSellingPrice(response.suggested_outgoing.current_price.tenths);
        setSelectionMode("selected");
        setConfirmingSuggestedRoute(true);
      } else {
        setConfirmingSuggestedRoute(false);
      }
    } catch (caught) {
      if (caught instanceof CurrentTeamApiError && caught.code === "free_question_limit_reached") {
        setQuota((current) => current ? { ...current, used: current.limit, remaining: 0 } : current);
      }
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
      setAssistantMessage("");
      setOutcome(null);
      setConfirmingSuggestedRoute(false);
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
          <b>{quota ? `${quota.remaining} of ${quota.limit} questions left` : "Loading allowance"}</b>
        </div>
        <Link href="/team">Use my Team ID</Link>
      </header>

      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>Three transfer questions every Gameweek</p>
          <h1>Ask the question.<br /><em>Get the shortlist.</em></h1>
          <p>
            Tell GafferTalk what matters to you. It does the research, then checks live prices,
            fixtures, availability, budget and FPL squad rules before answering.
          </p>
        </div>
        <aside>
          <span>Current planning state</span>
          <strong>{squad?.name ?? "Unavailable"}</strong>
          <dl>
            <div><dt>Bank</dt><dd>{money(squad?.bank_tenths ?? 0)}</dd></div>
            <div><dt>Free transfers</dt><dd>{squad?.free_transfers ?? 0}</dd></div>
            <div><dt>Questions left</dt><dd>{quota?.remaining ?? "—"}</dd></div>
          </dl>
          <button type="button" onClick={resetDemo} disabled={isLoading}>Reset demo squad</button>
        </aside>
      </section>

      {notice ? <p className={styles.notice} role="status">✓ {notice}</p> : null}
      {quotaError ? <p className={styles.errorBanner} role="alert">{quotaError}</p> : null}

      <form className={styles.flow} onSubmit={submit}>
        <section className={styles.setupPanel}>
          <div className={styles.panelHeading}>
            <span>01</span><div><small>Your squad</small><h2>Choose who could go</h2></div>
          </div>
          <div className={styles.modeSwitch} aria-label="Choose how to plan the transfer">
            <button
              type="button"
              className={selectionMode === "selected" ? styles.activeMode : ""}
              onClick={() => {
                setSelectionMode("selected");
                setConfirmingSuggestedRoute(false);
                setAssistantMessage("");
                setOutcome(null);
              }}
            >I know who to sell</button>
            <button
              type="button"
              className={selectionMode === "auto" ? styles.activeMode : ""}
              onClick={() => {
                setSelectionMode("auto");
                setConfirmingSuggestedRoute(false);
                setQuestion("What is the best way to get Ødegaard into my squad?");
                setAssistantMessage("");
                setOutcome(null);
                setResult(null);
              }}
            >Find who to sell</button>
          </div>
          {selectionMode === "auto" ? (
            <div className={styles.autoHelp}>
              <strong>Name the player you want.</strong>
              <p>GafferTalk checks every same-position player in your squad and finds the lowest-sacrifice plausible route. This first check is free.</p>
            </div>
          ) : (
            <>
              {confirmingSuggestedRoute ? <p className={styles.confirmBadge}>Confirm this route before using a question</p> : null}
              <label htmlFor="outgoing">Player to replace</label>
              <select
                id="outgoing"
                value={outgoingId}
                onChange={(event) => {
                  const id = Number(event.target.value);
                  const player = players.find((item) => item.id === id);
                  setOutgoingId(id);
                  if (player) setSellingPrice(player.current_price.tenths);
                  setConfirmingSuggestedRoute(false);
                  setResult(null);
                  setAssistantMessage("");
                  setOutcome(null);
                  if (player) setQuestion(starterQuestions[0].question(player.web_name));
                  setNotice("");
                }}
              >
                {players.map((player) => (
                  <option value={player.id} key={player.id}>
                    {player.web_name} · {player.position} · {player.club.short_name} · {money(player.current_price.tenths)}
                  </option>
                ))}
              </select>
              <label htmlFor="selling-price">Your actual FPL selling price</label>
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
            </>
          )}
        </section>

        <fieldset className={styles.actionPanel} disabled={quota?.remaining === 0}>
          <legend><span>02</span><div><small>Your question</small><strong>What do you want to solve?</strong></div></legend>
          <div className={styles.promptGrid}>
            {selectionMode === "selected" ? starterQuestions.map((starter) => (
              <button
                type="button"
                key={starter.number}
                onClick={() => outgoing && setQuestion(starter.question(outgoing.web_name))}
              >
                <span>{starter.number}</span>{starter.title}
              </button>
            )) : null}
          </div>
          <label className={styles.questionLabel} htmlFor="transfer-question">Ask in your own words</label>
          <textarea
            id="transfer-question"
            minLength={3}
            maxLength={500}
            required
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={selectionMode === "auto" ? "What is the best way to get Ødegaard into my squad?" : "Who should replace this player, and why?"}
          />
          <div className={styles.quotaLine}>
            <span>{question.length}/500</span>
            <strong>{quota ? `${quota.remaining} question${quota.remaining === 1 ? "" : "s"} left in ${quota.gameweek_name}` : "Checking allowance…"}</strong>
          </div>
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
          {quota?.remaining === 0 ? (
            <div className={styles.limitReached} role="status">
              <strong>That’s your three for {quota.gameweek_name}.</strong>
              <span>Your allowance resets when FPL moves to the next Gameweek. Pro will include a much larger fair-use limit.</span>
            </div>
          ) : null}
          <button className={styles.primary} disabled={isLoading || !squad || (selectionMode === "selected" && !outgoing) || !quota || quota.remaining === 0 || question.trim().length < 3}>
            {isLoading ? "Doing the homework…" : selectionMode === "auto" ? "Find the best route" : confirmingSuggestedRoute ? "Confirm price & ask GafferTalk" : "Ask GafferTalk"}
          </button>
          <small className={styles.security}>Groq reads the question and explains the result. GafferTalk’s deterministic engine decides legality, numbers and ranking. No FPL password needed.</small>
        </fieldset>
      </form>

      <section className={styles.results} aria-live="polite">
        <div className={styles.panelHeading}>
          <span>03</span><div><small>{outcome && outcome !== "recommendation" ? "Rule check" : "Legal shortlist"}</small><h2>{outcome && outcome !== "recommendation" ? "Here’s what needs fixing" : "Compare the trade-offs"}</h2></div>
          {result ? <b>{result.strategy.replace("_", " ")}</b> : null}
        </div>
        {!result && assistantMessage ? (
          <div className={styles.guidance}>
            <span>No Free question used</span>
            <strong>{assistantMessage}</strong>
            <p>Adjust the selected player or question, then ask again.</p>
          </div>
        ) : !result ? (
          <div className={styles.empty}>
            <strong>One player.<br />One clear question.</strong>
            <p>GafferTalk will return up to three legal options with the evidence and the catch.</p>
          </div>
        ) : result.recommendations.length === 0 ? (
          <div className={styles.empty}>
            <strong>No legal move found.</strong>
            <p>Try another outgoing player. GafferTalk will never pad the list with an illegal or unavailable option.</p>
          </div>
        ) : (
          <>
            <div className={styles.answer}><span>GafferTalk says</span><p>{assistantMessage}</p></div>
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
              <ul>
                <li>FPL data retrieved {retrievedAt(result.data_retrieved_at)}.</li>
                {result.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}
              </ul>
            </details>
            <p className={styles.disclaimer}>Adding a move updates this browser only. GafferTalk never changes your official FPL team.</p>
          </>
        )}
      </section>

      <aside className={styles.proTeaser}>
        <span>Coming later · GafferTalk Pro</span>
        <div><strong>Plan the whole Gameweek.</strong><p>Pro will add multi-transfer routes, three-to-five Gameweek planning, saved conversations and a much larger fair-use question limit.</p></div>
      </aside>

      <footer className={styles.footer}><span>GafferTalk does the homework.</span><b>You make the call.</b></footer>
    </main>
  );
}
