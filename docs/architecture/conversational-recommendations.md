# Conversational recommendations

The conversational layer is deliberately separated from football facts and
transfer legality.

```text
manager question
  -> deterministic preflight resolves explicit target names against live FPL data
  -> optional route discovery checks every same-position squad player
     -> asks for the suggested player's private selling price; no quota or Groq use
  -> ownership, position, availability, budget and club-limit checks
     -> invalid: actionable rule response, no quota use and no Groq call
     -> valid:
  -> Groq interprets the selected player's context and the manager's priorities
  -> deterministic GafferTalk engine loads live FPL data and ranks legal options
  -> Groq explains only the structured engine result
```

The browser never receives the Groq API key. `GAFFERTALK_GROQ_API_KEY` is a
server-only backend setting. The provider client lives behind an integration
boundary so a different model provider can replace Groq without changing the
recommendation domain.

The UI supports both an explicit outgoing player and “Find who to sell”. Route
discovery requires an explicit incoming target, checks only one-transfer routes,
and ranks plausible outgoing players deterministically by the lowest observed
performance sacrifice. Public current price is used only as an affordability
ceiling. The user must confirm the suggested player's private selling price
before the final legality check and Groq calls. Multi-transfer routes remain out
of Free scope.

Groq must echo the confirmed outgoing player ID, and the backend rejects any
response that changes it. Groq maps the question to one of the three versioned
recommendation strategies; the deterministic engine owns the weights and
ranking for that strategy.

Explicit target forms such as “get Haaland into my team”, “replace Bruno with
Saka”, “swap X for Y”, and “is Saka a good replacement?” are parsed before
Groq. The backend resolves exact or conservatively fuzzy-matched names against
the current catalogue. It never accepts a model-invented player ID. Ambiguous
or unknown names ask the manager to correct the question rather than silently
falling back to a generic shortlist.

The Free beta allows three successfully completed questions per official FPL
Gameweek. The API reserves allowance before the Groq calls and releases it when
interpretation, live-data loading, recommendation, or explanation fails. A
fourth question returns HTTP 429. Browser state only supplies an anonymous ID;
the usage count is enforced in the backend SQLite store.

If Groq is unconfigured or unavailable, `/recommend` shows a recoverable error
and does not consume a question. Groq errors never authorize invented
recommendations.
