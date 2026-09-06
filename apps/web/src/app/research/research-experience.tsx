"use client";

import Link from "next/link";
import { type FormEvent, useMemo, useState, useSyncExternalStore } from "react";
import {
  CurrentTeamApiError,
  researchConversation,
  type ResearchAlternative,
  type ResearchConversationResponse,
  type ResearchFact,
  type ResearchReport,
  type ResearchSellingPriceRequest,
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
import styles from "./research.module.css";

const RESEARCH_SESSION_KEY = "gaffertalk.researchConversation.v1";

const questionTemplates = [
  {
    label: "Get a target player",
    text: "How can I get [player name] into my team within two Gameweeks with a maximum hit of minus eight?",
    hint: "Shows a legal route, including whether rolling first helps.",
  },
  {
    label: "Compare alternatives",
    text: "What are reasonable alternatives to [player name] if I care about historical output and consistent minutes?",
    hint: "Compares factual evidence without pretending to predict points.",
  },
  {
    label: "Transfer or roll",
    text: "Should I roll my free transfer or make a transfer this week?",
    hint: "Checks the strongest squad concern against keeping the transfer.",
  },
  {
    label: "Squad concerns",
    text: "What are the biggest concerns in my current squad right now?",
    hint: "Surfaces availability, minutes and upgrade issues in priority order.",
  },
  {
    label: "Release budget",
    text: "How can I free enough budget for [player name] while keeping [player name]?",
    hint: "Finds bounded budget-release routes and explains the trade-off.",
  },
] as const;

type ResearchMessage = {
  id: string;
  question: string;
  response: ResearchConversationResponse;
};

function subscribeToBrowserReady() {
  return () => undefined;
}

function money(tenths: number) {
  return `£${(tenths / 10).toFixed(1)}m`;
}

function titleCase(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function natureLabel(value: ResearchFact["nature"]) {
  if (value === "observed") return "Observed fact";
  if (value === "calculated") return "Calculation";
  return "Derived from the evidence";
}

function sessionSquadKey(saved: SavedRecommendationSquad) {
  return [...saved.squad.player_ids].sort((left, right) => left - right).join("-");
}

function readConversationId(saved: SavedRecommendationSquad) {
  try {
    const raw = window.sessionStorage.getItem(RESEARCH_SESSION_KEY);
    if (!raw) return "";
    const value = JSON.parse(raw) as { squad_key?: string; conversation_id?: string };
    return value.squad_key === sessionSquadKey(saved) ? value.conversation_id ?? "" : "";
  } catch {
    return "";
  }
}

function storeConversationId(saved: SavedRecommendationSquad, conversationId: string) {
  window.sessionStorage.setItem(
    RESEARCH_SESSION_KEY,
    JSON.stringify({ squad_key: sessionSquadKey(saved), conversation_id: conversationId }),
  );
}

function readInitialSavedSquad() {
  if (typeof window === "undefined") return null;
  return parseSavedRecommendationSquad(window.localStorage.getItem(RECOMMENDATION_STORAGE_KEY));
}

function readInitialPrices() {
  const initialSquad = readInitialSavedSquad();
  if (typeof window === "undefined" || !initialSquad) return {};
  return parseSellingPriceSession(
    window.sessionStorage.getItem(PRO_SELLING_PRICE_SESSION_KEY),
    initialSquad.squad.player_ids,
  );
}

function FactList({ facts }: { facts: ResearchFact[] }) {
  if (!facts.length) return null;
  return (
    <div className={styles.factList}>
      {facts.map((fact, index) => (
        <article key={`${fact.subject}-${fact.label}-${index}`}>
          <div className={styles.factHeading}>
            <span>{natureLabel(fact.nature)}</span>
            <small>{fact.source}</small>
          </div>
          <strong>{fact.label}</strong>
          <p>{fact.value}</p>
          <small className={styles.factSubject}>{fact.subject}</small>
        </article>
      ))}
    </div>
  );
}

function AlternativeList({ alternatives }: { alternatives: ResearchAlternative[] }) {
  if (!alternatives.length) return null;
  return (
    <section className={styles.sectionBlock} aria-labelledby="alternatives-title">
      <div className={styles.sectionHeading}>
        <span>Other defensible paths</span>
        <h3 id="alternatives-title">Two alternatives</h3>
      </div>
      <div className={styles.alternativeList}>
        {alternatives.map((alternative) => (
          <article key={`${alternative.rank}-${alternative.action}`}>
            <span className={styles.rank}>0{alternative.rank}</span>
            <div>
              <strong>{alternative.player?.web_name ?? titleCase(alternative.action)}</strong>
              <p>{alternative.reason}</p>
              <FactList facts={alternative.facts} />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ReportCard({ response }: { response: ResearchConversationResponse }) {
  const report: ResearchReport | null = response.research?.report ?? null;
  if (!report) {
    return (
      <div className={styles.clarification}>
        <span>{response.status === "unsupported" ? "Outside the research scope" : "One detail first"}</span>
        <p>{response.assistant_message}</p>
        <small>Supported questions cover transfers, alternatives, budget release, hold-versus-transfer decisions and squad concerns.</small>
      </div>
    );
  }

  if (response.status === "needs_clarification" || report.status === "needs_clarification") {
    return (
      <div className={styles.clarification}>
        <span>One detail first · {titleCase(report.capability)}</span>
        <p>{response.assistant_message}</p>
        <small>Once that detail is clear, I’ll run the relevant facts-first research route.</small>
      </div>
    );
  }

  return (
    <div className={styles.reportCard}>
      <header className={styles.reportHeader}>
        <div>
          <span>{titleCase(report.status)} · {titleCase(report.capability)}</span>
          <h2>{report.subject?.web_name ?? "Your squad"}</h2>
        </div>
        <span className={styles.provider}>{response.provider} · {response.model}</span>
      </header>

      <section className={styles.answer}>
        <span>GafferTalk’s answer</span>
        <p>{response.assistant_message}</p>
      </section>

      <section className={styles.recommendation} aria-labelledby="recommendation-title">
        <div className={styles.sectionHeading}>
          <span>One recommended plan</span>
          <h3 id="recommendation-title">The call</h3>
        </div>
        <p>{report.recommended_action}</p>
        <div className={styles.reasonStrip}>
          <div><span>Why this plan</span><p>{report.opinion}</p></div>
          <div><span>Strongest objection</span><p>{report.strongest_objection}</p></div>
        </div>
      </section>

      <AlternativeList alternatives={report.alternatives} />

      <section className={styles.sectionBlock} aria-labelledby="facts-title">
        <div className={styles.sectionHeading}>
          <span>Evidence before opinion</span>
          <h3 id="facts-title">What we know</h3>
        </div>
        <FactList facts={report.facts} />
        {report.calculations.length ? (
          <div className={styles.calculations}>
            {report.calculations.map((calculation) => (
              <article key={`${calculation.label}-${calculation.value}`}>
                <span>{calculation.label}</span>
                <strong>{calculation.value}</strong>
                <small>{calculation.formula}</small>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className={styles.detailGrid}>
        <details open>
          <summary>Grounded reasons</summary>
          <ul>{report.grounded_reasons.map((reason) => <li key={reason.id}>{reason.text}</li>)}</ul>
        </details>
        <details>
          <summary>What would change this</summary>
          <ul>{report.change_conditions.map((condition) => <li key={condition}>{condition}</li>)}</ul>
        </details>
        <details>
          <summary>Assumptions and limits</summary>
          <ul>{report.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
        </details>
      </section>

      <p className={styles.transparencyNote}>This is a facts-first research answer. Derived figures are labelled, and the recommendation is not a promise of future points.</p>
    </div>
  );
}

function PricePrompt({
  requests,
  values,
  onChange,
  onConfirm,
  loading,
}: {
  requests: ResearchSellingPriceRequest[];
  values: Record<number, string>;
  onChange: (playerId: number, value: string) => void;
  onConfirm: () => void;
  loading: boolean;
}) {
  return (
    <section className={styles.pricePrompt} aria-labelledby="price-prompt-title">
      <div>
        <span>Exact budget check paused</span>
        <h3 id="price-prompt-title">Confirm the selling price</h3>
        <p>FPL gives us a player’s current price, but only you can see the actual selling price in your transfer screen. Add it below so the same question can be checked again with exact numbers.</p>
      </div>
      <div className={styles.priceRows}>
        {requests.map((request) => (
          <label key={request.player_id} htmlFor={`selling-price-${request.player_id}`}>
            <span>{request.player_name}</span>
            <small>Current price is an upper bound: {money(request.current_fpl_price_tenths)}</small>
            <div><b>£</b><input id={`selling-price-${request.player_id}`} type="number" min="0" max={(request.current_fpl_price_tenths / 10).toFixed(1)} step="0.1" inputMode="decimal" value={values[request.player_id] ?? ""} onChange={(event) => onChange(request.player_id, event.target.value)} placeholder="0.0" /><b>m</b></div>
            <small>{request.reason}</small>
          </label>
        ))}
      </div>
      <button type="button" className={styles.primaryButton} disabled={loading} onClick={onConfirm}>{loading ? "Checking exact route…" : "Confirm and retry"}</button>
    </section>
  );
}

export function ResearchExperience() {
  const browserReady = useSyncExternalStore(subscribeToBrowserReady, () => true, () => false);
  const saved = useMemo<SavedRecommendationSquad | null>(() => {
    if (!browserReady) return null;
    return parseSavedRecommendationSquad(window.localStorage.getItem(RECOMMENDATION_STORAGE_KEY));
  }, [browserReady]);
  const initialSavedSquad = useMemo(() => readInitialSavedSquad(), []);
  const [conversationId, setConversationId] = useState(() => initialSavedSquad ? readConversationId(initialSavedSquad) : "");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ResearchMessage[]>([]);
  const [priceValues, setPriceValues] = useState<Record<number, string>>({});
  const [confirmedPrices, setConfirmedPrices] = useState<Record<number, number>>(readInitialPrices);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const cachedPrices = useMemo(() => {
    if (!browserReady || !saved) return {};
    return parseSellingPriceSession(window.sessionStorage.getItem(PRO_SELLING_PRICE_SESSION_KEY), saved.squad.player_ids);
  }, [browserReady, saved]);
  const effectivePrices = useMemo(() => ({ ...cachedPrices, ...confirmedPrices }), [cachedPrices, confirmedPrices]);

  const submitQuestion = async (nextQuestion: string, prices: Record<number, number>, displayQuestion = nextQuestion) => {
    if (!saved || nextQuestion.trim().length < 3) return;
    setLoading(true);
    setError("");
    try {
      const response = await researchConversation({
        conversation_id: conversationId || undefined,
        question: nextQuestion.trim(),
        squad: saved.squad,
        selling_prices_tenths: prices,
      });
      setConversationId(response.conversation_id);
      storeConversationId(saved, response.conversation_id);
      setMessages((current) => [...current, { id: `${response.conversation_id}-${current.length}`, question: displayQuestion, response }]);
      setQuestion("");
      setPriceValues(Object.fromEntries(response.selling_price_requests.map((request) => [request.player_id, ""])));
    } catch (caught) {
      setError(caught instanceof CurrentTeamApiError ? caught.message : "The research answer could not be completed. Try again shortly.");
    } finally {
      setLoading(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await submitQuestion(question, effectivePrices);
  };

  const confirmPrices = async () => {
    const latest = messages.at(-1)?.response;
    if (!saved || !latest || !latest.selling_price_requests.length) return;
    const nextPrices = { ...effectivePrices };
    for (const request of latest.selling_price_requests) {
      const tenths = Math.round(Number(priceValues[request.player_id]) * 10);
      if (!Number.isInteger(tenths) || tenths < 0 || tenths > request.current_fpl_price_tenths) {
        setError(`Enter ${request.player_name}’s actual selling price, no higher than ${money(request.current_fpl_price_tenths)}.`);
        return;
      }
      nextPrices[request.player_id] = tenths;
    }
    window.sessionStorage.setItem(PRO_SELLING_PRICE_SESSION_KEY, serializeSellingPriceSession(saved.squad.player_ids, nextPrices));
    setConfirmedPrices(nextPrices);
    await submitQuestion(latest.question, nextPrices, `Confirm selling price · ${latest.question}`);
  };

  const startNewConversation = () => {
    setConversationId("");
    setMessages([]);
    setError("");
    if (saved) window.sessionStorage.removeItem(RESEARCH_SESSION_KEY);
  };

  if (!browserReady) return <main className={styles.loading}>Loading your confirmed team…</main>;
  if (!saved) {
    return (
      <main className={styles.emptyState}>
        <Link href="/" className={styles.wordmark}>GafferTalk<span>.</span></Link>
        <p>Research starts with a confirmed planning state.</p>
        <h1>Bring your team<br />into the room.</h1>
        <p>Load the latest public FPL snapshot, record any changes you made, then ask questions in your own words.</p>
        <Link href="/research/team" className={styles.primaryButton}>Load and confirm my team</Link>
      </main>
    );
  }

  const latestResponse = messages.at(-1)?.response ?? null;
  const priceRequests = latestResponse?.selling_price_requests ?? [];

  return (
    <main className={styles.app}>
      <header className={styles.header}>
        <Link href="/" className={styles.wordmark}>GafferTalk<span>.</span></Link>
        <div className={styles.headerState}><span className={styles.statusDot} /> Researching {saved.squad.name}</div>
        <div className={styles.headerActions}><Link href="/research/team">Edit team</Link><button type="button" onClick={startNewConversation}>New conversation</button></div>
      </header>

      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}><span>Personal research assistant</span> Slice 4 · Current Gameweek</p>
          <h1>Ask the<br /><em>right question.</em></h1>
          <p className={styles.lede}>Your team, budget and transfers are already in the room. Ask naturally; GafferTalk gathers the available evidence, checks the FPL rules, and shows why it reached its view.</p>
        </div>
        <aside>
          <span>Confirmed planning state</span>
          <strong>{saved.squad.name}</strong>
          <dl><div><dt>Bank</dt><dd>{money(saved.squad.bank_tenths)}</dd></div><div><dt>Free transfers</dt><dd>{saved.squad.free_transfers}</dd></div><div><dt>Players</dt><dd>{saved.players.length}</dd></div></dl>
        </aside>
      </section>

      <section className={styles.templateSection} aria-labelledby="templates-title">
        <div className={styles.sectionHeading}><span>Start with a template</span><h2 id="templates-title">Or ask it your way.</h2></div>
        <div className={styles.templateGrid}>
          {questionTemplates.map((template) => <button type="button" key={template.label} onClick={() => setQuestion(template.text)}><strong>{template.label}</strong><span>{template.text}</span><small>{template.hint}</small></button>)}
        </div>
      </section>

      <form className={styles.questionForm} onSubmit={submit}>
        <label htmlFor="research-question">Your question</label>
        <textarea id="research-question" value={question} onChange={(event) => { setQuestion(event.target.value); setError(""); }} placeholder="Ask about a transfer, a player alternative, your budget, or your biggest squad concern…" minLength={3} maxLength={500} required />
        <div className={styles.formFooter}><small>Facts first. Any derived figure is labelled, and the final decision stays with you.</small><button type="submit" className={styles.primaryButton} disabled={loading || question.trim().length < 3}>{loading ? "Researching…" : "Ask GafferTalk"}</button></div>
      </form>
      {error ? <p className={styles.error} role="alert">{error}</p> : null}

      <section className={styles.conversation} aria-live="polite">
        {!messages.length ? <div className={styles.emptyConversation}><span>Ready when you are</span><h2>One question.<br />A transparent answer.</h2><p>Try a template above or ask about the decision you are actually facing this Gameweek.</p></div> : messages.map((message) => <article className={styles.message} key={message.id}><div className={styles.userQuestion}><span>You asked</span><p>{message.question}</p></div><ReportCard response={message.response} />{message.response === latestResponse && priceRequests.length ? <PricePrompt requests={priceRequests} values={priceValues} onChange={(playerId, value) => setPriceValues((current) => ({ ...current, [playerId]: value }))} onConfirm={confirmPrices} loading={loading} /> : null}</article>)}
      </section>

      <footer className={styles.footer}><span>GafferTalk does the homework.</span><span>You make the call.</span></footer>
    </main>
  );
}
