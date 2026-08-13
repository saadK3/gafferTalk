# Conversational recommendations

The conversational layer is deliberately separated from football facts and
transfer legality.

```text
manager question
  -> Groq interprets the selected player's context and the manager's priorities
  -> deterministic GafferTalk engine loads live FPL data and ranks legal options
  -> Groq explains only the structured engine result
```

The browser never receives the Groq API key. `GAFFERTALK_GROQ_API_KEY` is a
server-only backend setting. The provider client lives behind an integration
boundary so a different model provider can replace Groq without changing the
recommendation domain.

The UI keeps the outgoing-player selection explicit for this first slice. This
makes the user's intent unambiguous and prevents an LLM from silently choosing
the wrong squad player. Groq must echo that selected player ID, and the backend
rejects any response that changes it.

If Groq is unconfigured locally, `/recommend` falls back to the deterministic
transfer endpoint and clearly labels the output as an engine preview. Groq
errors never authorize invented recommendations.
