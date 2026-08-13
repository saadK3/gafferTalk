"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import {
  askGafferTalk,
  CurrentTeamApiError,
  loadDemoSquad,
  recommendTransfer,
  type ApiPlayer,
  type CurrentSquadRequest,
  type RecommendationResult,
} from "@/lib/current-team-api";
import styles from "./recommendation.module.css";

type Source = "engine" | "groq";

function money(tenths: number) { return `£${(tenths / 10).toFixed(1)}m`; }

function savedSquad(): { squad: CurrentSquadRequest; players: ApiPlayer[] } | null {
  const raw = window.localStorage.getItem("gaffertalk.recommendationSquad.v1");
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as { squad?: CurrentSquadRequest; players?: ApiPlayer[] };
    if (value.squad?.player_ids.length !== 15 || value.players?.length !== 15) return null;
    return { squad: value.squad, players: value.players };
  } catch {
    return null;
  }
}

export function RecommendationExperience() {
  const [squad, setSquad] = useState<CurrentSquadRequest | null>(null);
  const [players, setPlayers] = useState<ApiPlayer[]>([]);
  const [outgoingId, setOutgoingId] = useState(0);
  const [sellingPrice, setSellingPrice] = useState(0);
  const [question, setQuestion] = useState("Who is the best replacement? Prioritise fixtures, but explain the trade-off.");
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [answer, setAnswer] = useState("");
  const [source, setSource] = useState<Source>("engine");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const confirmed = savedSquad();
    if (confirmed) {
      Promise.resolve().then(() => {
        setSquad(confirmed.squad);
        setPlayers(confirmed.players);
        const defaultPlayer = confirmed.players.find((player) => player.position === "MID") ?? confirmed.players[0];
        setOutgoingId(defaultPlayer.id);
        setSellingPrice(defaultPlayer.current_price.tenths);
        setIsLoading(false);
      });
      return () => controller.abort();
    }
    loadDemoSquad(controller.signal).then((demo) => {
      setSquad(demo.squad);
      setPlayers(demo.players);
      const defaultPlayer = demo.players.find((player) => player.web_name === "Yates") ?? demo.players[0];
      setOutgoingId(defaultPlayer.id);
      setSellingPrice(defaultPlayer.current_price.tenths);
    }).catch(() => setError("The live demo squad could not be loaded.")).finally(() => setIsLoading(false));
    return () => controller.abort();
  }, []);

  const outgoing = useMemo(() => players.find((player) => player.id === outgoingId), [outgoingId, players]);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!squad || !outgoing) return;
    setIsLoading(true);
    setError("");
    setResult(null);
    try {
      const input = { squad, outgoing_player_id: outgoing.id, outgoing_selling_price_tenths: sellingPrice };
      try {
        const conversational = await askGafferTalk({ ...input, question });
        setResult(conversational.result);
        setAnswer(conversational.assistant_message);
        setSource("groq");
      } catch (caught) {
        if (!(caught instanceof CurrentTeamApiError) || caught.code !== "conversation_unconfigured") throw caught;
        const deterministic = await recommendTransfer(input);
        setResult(deterministic);
        setAnswer("Groq is not configured locally, so these are the engine’s ranked facts without an AI-written explanation.");
        setSource("engine");
      }
    } catch (caught) {
      setError(caught instanceof CurrentTeamApiError ? caught.message : "GafferTalk could not complete that recommendation.");
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading && !squad) return <main className={styles.loading}>Loading today’s FPL data…</main>;

  return (
    <main className={styles.app}>
      <header className={styles.header}><Link href="/" className={styles.wordmark}>GafferTalk<span>.</span></Link><div><span>Live FPL data</span><i /> <b>{squad?.name === "GafferTalk Synthetic XI" ? "Synthetic squad" : "Confirmed squad"}</b></div><Link href="/team">Use my Team ID</Link></header>
      <section className={styles.hero}>
        <div><p className={styles.eyebrow}>The decision room · preseason baseline</p><h1>Ask the question.<br /><em>See the trade-off.</em></h1><p>Choose one player, ask naturally, and GafferTalk does the fixture, value and legality homework.</p></div>
        <aside><span>Current test state</span><strong>{squad?.name ?? "Unavailable"}</strong><dl><div><dt>Bank</dt><dd>{money(squad?.bank_tenths ?? 0)}</dd></div><div><dt>Free transfers</dt><dd>{squad?.free_transfers ?? 0}</dd></div><div><dt>Players</dt><dd>{players.length}</dd></div></dl></aside>
      </section>
      <div className={styles.workspace}>
        <form className={styles.askPanel} onSubmit={submit}>
          <div className={styles.panelHeading}><span>01</span><div><small>Your question</small><h2>Make the call</h2></div></div>
          <label htmlFor="outgoing">Player to replace</label>
          <select id="outgoing" value={outgoingId} onChange={(event) => { const id = Number(event.target.value); setOutgoingId(id); const player = players.find((item) => item.id === id); if (player) setSellingPrice(player.current_price.tenths); }}>
            {players.map((player) => <option value={player.id} key={player.id}>{player.web_name} · {player.position} · {player.club.short_name} · {money(player.current_price.tenths)}</option>)}
          </select>
          <label htmlFor="selling-price">Confirmed selling price</label>
          <div className={styles.priceInput}><span>£</span><input id="selling-price" type="number" min="3.5" max="30" step="0.1" value={(sellingPrice / 10).toFixed(1)} onChange={(event) => setSellingPrice(Math.round(Number(event.target.value) * 10))} /><span>m</span></div>
          <label htmlFor="question">What matters to you?</label>
          <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)} rows={5} maxLength={500} />
          <div className={styles.prompts}><button type="button" onClick={() => setQuestion("Who is the safest replacement based on fixtures?")}>Safer fixtures</button><button type="button" onClick={() => setQuestion("Give me the best value replacement and explain what I give up.")}>Best value</button></div>
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
          <button className={styles.primary} disabled={isLoading || !squad}>{isLoading ? "Doing the homework…" : "Ask GafferTalk"}</button>
          <small className={styles.security}>Groq interprets and explains. Our engine controls facts and legality.</small>
        </form>
        <section className={styles.results} aria-live="polite">
          <div className={styles.panelHeading}><span>02</span><div><small>Decision support</small><h2>Options, ranked</h2></div>{result ? <b>{source === "groq" ? "Explained by Groq" : "Engine preview"}</b> : null}</div>
          {!result ? <div className={styles.empty}><strong>Pick a player.<br />Ask the question.</strong><p>Your three legal options will land here with the numbers and the catch.</p></div> : <>
            <article className={styles.answer}><span>GafferTalk’s read</span><p>{answer}</p></article>
            <div className={styles.cards}>{result.recommendations.map((item) => <article className={styles.card} key={item.incoming.id}><header><span>#{item.rank}</span><div><strong>{item.incoming.web_name}</strong><small>{item.incoming.club.short_name} · {item.incoming.position}</small></div><b>{item.score.toFixed(1)}</b></header><div className={styles.metrics}><div><span>Price</span><strong>{money(item.incoming.current_price.tenths)}</strong></div><div><span>Bank after</span><strong>{money(item.remaining_bank.tenths)}</strong></div><div><span>Fixture avg.</span><strong>{item.average_fixture_difficulty?.toFixed(2) ?? "—"}</strong></div></div><p>{item.reasons[1]}</p><footer><span>The catch</span>{item.trade_off}</footer></article>)}</div>
            <p className={styles.disclaimer}>Preseason baseline: previous-season points + next-five fixture difficulty + value. This is decision support, not certainty.</p>
          </>}
        </section>
      </div>
      <footer className={styles.footer}><span>GafferTalk does the homework.</span><b>You make the call.</b></footer>
    </main>
  );
}
