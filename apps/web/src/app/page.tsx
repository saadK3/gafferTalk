import { WaitlistForm } from "./waitlist-form";

const questions = [
  {
    number: "01",
    question: "How do I get Palmer without selling Bruno Fernandes?",
    answer: "See the legal routes, not just the obvious swap.",
    tone: "teal",
  },
  {
    number: "02",
    question: "Who replaces my injured midfielder?",
    answer: "Compare budget, fixtures and the trade-offs that matter.",
    tone: "raspberry",
  },
  {
    number: "03",
    question: "Can I make this move without taking a hit?",
    answer: "Know the cost before you confirm the transfer.",
    tone: "green",
  },
];

const steps = [
  {
    number: "01",
    title: "Load the squad",
    copy: "Enter a public FPL Team ID. No password, no account access.",
  },
  {
    number: "02",
    title: "Ask the real question",
    copy: "Talk through transfers, constraints and the players you want to keep.",
  },
  {
    number: "03",
    title: "Make the call",
    copy: "Get legal options with the cost, assumptions and reasoning made clear.",
  },
];

function Shirt({ color, number }: { color: string; number: string }) {
  return (
    <span className="shirt" style={{ "--shirt-color": color } as React.CSSProperties}>
      <span>{number}</span>
    </span>
  );
}

function TransferPanel() {
  return (
    <div className="transfer-stage" aria-label="Example legal transfer recommendation">
      <div className="pitch-sheet" aria-hidden="true">
        <span className="pitch-player pitch-player-one">13</span>
        <span className="pitch-player pitch-player-two">19</span>
        <span className="pitch-player pitch-player-three">17</span>
        <span className="pitch-arrow">↑</span>
      </div>

      <article className="transfer-card">
        <div className="transfer-card-header">
          <span>Transfer check</span>
          <span className="gw-label">GW02</span>
        </div>

        <div className="transfer-player">
          <Shirt color="#168594" number="10" />
          <div>
            <span className="utility-label">Out · MID</span>
            <strong>Palmer</strong>
          </div>
          <span className="transfer-direction" aria-hidden="true">→</span>
        </div>

        <div className="transfer-player">
          <Shirt color="#d8296a" number="7" />
          <div>
            <span className="utility-label">In · MID</span>
            <strong>Saka</strong>
          </div>
          <span className="color-disc raspberry" aria-hidden="true" />
        </div>

        <dl className="transfer-stats">
          <div>
            <dt>Bank remaining</dt>
            <dd>£1.4m</dd>
          </div>
          <div>
            <dt>Free transfers</dt>
            <dd>1</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd><span className="legal-pill">Legal</span></dd>
          </div>
        </dl>

        <div className="why-it-works">
          <span className="utility-label">Why it works</span>
          <p>Same position. Within budget. Club limit respected.</p>
        </div>
      </article>
    </div>
  );
}

export default function Home() {
  return (
    <main>
      <header className="site-header page-shell">
        <a className="wordmark" href="#top" aria-label="GafferTalk home">
          GafferTalk<span>.</span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <a href="#why-gaffertalk">Why GafferTalk</a>
          <a className="nav-cta" href="#early-access">Early access</a>
        </nav>
      </header>

      <section className="hero page-shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow"><span>26/27</span> Fantasy football, made clearer</p>
          <h1>Make the call.<br />Know the trade-off.</h1>
          <p className="hero-lede">
            <strong>Your team. Your call.</strong> GafferTalk does the homework—checking
            the data, budget and FPL rules before laying out your options.
          </p>
          <div className="hero-actions">
            <a className="primary-button" href="#early-access">Join early access</a>
            <span>Launching after Gameweek 1 · No FPL password needed</span>
          </div>
        </div>
        <TransferPanel />
      </section>

      <section className="questions-section page-shell" id="why-gaffertalk">
        <div className="section-kicker"><span>Matchday questions</span><span>01—03</span></div>
        <h2>Built for the questions<br />you actually ask.</h2>
        <div className="question-grid">
          {questions.map((item) => (
            <article className={`question-card ${item.tone}`} key={item.number}>
              <div className="question-number">{item.number}</div>
              <h3>{item.question}</h3>
              <p>{item.answer}</p>
              <div className="question-route" aria-hidden="true">
                <Shirt color={item.tone === "raspberry" ? "#d8296a" : "#168594"} number={item.number.slice(1)} />
                <span>→</span><i>?</i><span>→</span><i className="result">✓</i>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="how-section" id="how-it-works">
        <div className="page-shell">
          <div className="section-kicker light"><span>How it works</span><span>Three touches</span></div>
          <div className="how-heading">
            <h2>From squad to<br />sound decision.</h2>
            <p>
              The conversation stays simple. Underneath it, GafferTalk checks the
              numbers and FPL rules before presenting an option.
            </p>
          </div>
          <div className="steps-grid">
            {steps.map((step) => (
              <article className="step-card" key={step.number}>
                <span>{step.number}</span>
                <h3>{step.title}</h3>
                <p>{step.copy}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="principles-section page-shell">
        <p className="eyebrow"><span>Rules first</span> You stay in control</p>
        <div className="principles-copy">
          <h2>No black box.<br />No blind punts.</h2>
          <div>
            <p>
              GafferTalk separates the conversation from the calculation. It can
              explain the options, but legality, prices and budget come from
              deterministic checks.
            </p>
            <ul>
              <li><span>01</span> No FPL password</li>
              <li><span>02</span> No automatic transfers</li>
              <li><span>03</span> No invented budget or squad rules</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="early-access-section" id="early-access">
        <div className="page-shell early-access-inner">
          <div>
            <p className="eyebrow inverted"><span>Early access</span> After Gameweek 1</p>
            <h2>Be there<br />for kick-off.</h2>
          </div>
          <div className="signup-block">
            <p>
              Get the launch update and be among the first managers to put
              GafferTalk through a real transfer decision.
            </p>
            <WaitlistForm />
            <small>
              We’ll only use your email for GafferTalk launch updates. We will
              never ask for your FPL password.
            </small>
          </div>
        </div>
      </section>

      <footer className="site-footer page-shell">
        <a className="wordmark" href="#top">GafferTalk<span>.</span></a>
        <p>Fantasy football, made clearer.</p>
        <p>© 2026 GafferTalk</p>
      </footer>
    </main>
  );
}
