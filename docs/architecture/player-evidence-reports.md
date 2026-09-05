# Player evidence reports

Slice 2 gives the research agent a versioned, deterministic evidence packet for
one or more resolved FPL players. It reports what the available sources say. It
does not predict returns, score players or choose a transfer.

## Data flow

```text
PlayerEvidenceRequest (resolved FPL player IDs)
  -> official FPL bootstrap-static observation
  -> official FPL fixtures observation
  -> official FPL element-summary observation per player
  -> preserve each response's original cache-entry time
  -> group match rows by Gameweek
  -> reconcile upcoming fixtures and expose disagreements
  -> versioned PlayerEvidenceReport
```

`PlayerEvidenceLoader` performs the minimum endpoint calls and
`PlayerEvidenceService` constructs the report. A failed player-summary request
does not erase useful bootstrap and global-fixture evidence; that player's
report is explicitly partial.

## Evidence supplied

- Current price, FPL status, chance-of-playing field, news and the upstream news
  timestamp where FPL supplies one.
- Current-season points, minutes, starts, goals, assists and bonus.
- Current-season and recent historical xG/xA, labelled `model_derived` because
  they originate in an expected-goals model even though they describe completed
  matches.
- Recent match history over an explicit number of Gameweeks.
- Upcoming fixtures with opponent, venue, difficulty, kickoff and provenance.

Recent history is grouped by `round`. Two match rows carrying the same round are
therefore two matches in one Gameweek, not two separate Gameweek samples. The
report exposes both the grouped Gameweeks and the underlying matches.

The recent xG/xA block exposes its included Gameweek IDs, match count and total
minutes denominator. It is an historical evidence summary, never expected
points or a forecast.

## Missing values and observed zero

The FPL adapter records which upstream fields were actually present. The
evidence builder converts an omitted field to `null` and lists its path in
`missing_fields`. An upstream numeric zero remains `0`. These states must not be
collapsed because “the player recorded zero” and “the source did not supply the
metric” are different claims.

If any match row required for an aggregate omits a metric, that aggregate is
`null`; the service does not silently total only the available rows.

## Time and provenance

Every source reference includes:

- provider (`official_fpl`)
- endpoint
- the time the response actually entered GafferTalk's cache
- a publisher timestamp when the field supplies one, currently FPL news

The FPL client caches the response together with its fetch time. Generating a
new report from a cached response does not make old evidence appear new. The
request selects a freshness threshold and the report returns `current` or
`stale` without discarding the evidence.

## Contradictions

Upcoming fixtures are available in both `/fixtures/` and each player's
`/element-summary/{id}/`. When matching fixture IDs disagree on Gameweek,
kickoff, clubs, venue or difficulty, the report retains the global fixture value
and emits a `fixture_source_mismatch` conflict naming both endpoints. A later
agent can explain or request a refresh; it cannot unknowingly reason over the
disagreement.

## Boundaries

This slice deliberately excludes:

- expected points and expected minutes
- predicted lineups, outcomes or price changes
- recommendations and route selection
- external news and press-conference crawling

Slice 1 supplies legal multi-Gameweek routes. Slice 2 supplies inspectable
player evidence. A later decision slice will combine the two while keeping
legality, evidence and opinion separate.

