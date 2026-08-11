# Transfer legality

`TransferLegalityService` validates normal FPL transfers deterministically. It
does not call a language model and does not infer a manager's private in-progress
state from a public Team ID snapshot.

## Inputs

The service receives:

- A finalized public `SquadSnapshot`
- The current public `FplCatalogue`, including FPL-provided squad composition,
  per-club limit, and player prices
- Manager-confirmed planning state: current bank, free-transfer count, and the
  selling price for each outgoing player
- One or more proposed outgoing/incoming player pairs

Money is always represented as integer tenths of a million pounds.

## Normal-transfer validation

The resulting squad must retain FPL's configured squad size and position
composition, must not exceed the club limit, and must not contain duplicate or
unknown players. The service calculates remaining bank from confirmed selling
prices, rather than guessing that a player's selling price equals their current
market price.

When there are more requested transfers than confirmed free transfers, each
extra normal transfer incurs a four-point hit. The result exposes free transfers
used, paid transfers, points hit, remaining bank, assumptions, and structured
rejection reasons.

## Missing and unsupported state

`missing_state` is returned when exact legality needs bank, free-transfer, or
selling-price information that is not available. `unsupported` is returned when
the manager is using a chip such as Wildcard or Free Hit; GafferTalk does not
silently apply normal-transfer rules to a chip scenario.

The reusable scenarios in
`tests/fixtures/transfer-legality.scenarios.json` cover exact budget,
insufficient funds, club and position violations, missing selling price,
free-transfer hits, and unsupported chips. Additional reference validation tests
cover duplicate and unknown players plus missing bank/free-transfer state.
