# One-player recommendation baseline

Issue: #28

The first recommendation slice combines live public FPL players, prices,
availability and fixtures with one versioned synthetic squad. A developer
selects one outgoing squad player through the CLI, and the engine returns up to
three legal same-position replacements.

Candidates are rejected when they are already in the squad, unavailable,
unaffordable, the wrong position, or would break FPL's club limit. The existing
`TransferLegalityService` remains the authority for exact legality.

The free version exposes three transparent scoring profiles:

```text
Best all-rounder:     45% official historical points, 35% fixtures, 20% value
Attack the fixtures: 25% official historical points, 60% fixtures, 15% value
Stretch the budget:  25% official historical points, 20% fixtures, 55% value
```

Each component is normalized against the legal candidate set. This is a
development baseline, not an expected-points model. It deliberately does not
claim to know expected minutes, rotation, tactical role or current-season form.
The weights must be versioned and recalibrated after current-season evidence is
available.

All profiles share the same candidate gate. A player is excluded when they are
already in the squad, unavailable, unaffordable, in the wrong position, or
would create a fourth player from one club. The response includes the bank,
remaining free transfers and points hit after the proposed move.

The web client may add a recommendation to a device-local plan. It replaces the
outgoing player in the same squad slot and updates the confirmed bank and
free-transfer count. It does not call FPL, execute a transfer, create an account
or store the plan on the server.

Run it with:

```bash
make recommend-one OUT=Yates
```
