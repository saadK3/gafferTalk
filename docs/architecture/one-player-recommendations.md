# One-player recommendation baseline

Issue: #28

The first recommendation slice combines live public FPL players, prices,
availability and fixtures with one versioned synthetic squad. A developer
selects one outgoing squad player through the CLI, and the engine returns up to
three legal same-position replacements.

Candidates are rejected when they are already in the squad, unavailable,
unaffordable, the wrong position, or would break FPL's club limit. The existing
`TransferLegalityService` remains the authority for exact legality.

The transparent preseason score is:

```text
45% official historical points
35% average difficulty over the next five scheduled fixtures
20% historical points per price
```

Each component is normalized against the legal candidate set. This is a
development baseline, not an expected-points model. It deliberately does not
claim to know expected minutes, rotation, tactical role or current-season form.
The weights must be versioned and recalibrated after current-season evidence is
available.

Run it with:

```bash
make recommend-one OUT=Yates
```
