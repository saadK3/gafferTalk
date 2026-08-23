# Sanitized FPL contract fixtures

Observed before the 2026/27 Gameweek 1 deadline on 2026-08-12 and again after
the deadline on 2026-08-22.

These small samples preserve fields and units needed for adapter contract tests.
Names, entry IDs, player IDs, team IDs and values that could identify a manager
have been replaced. The files are not complete API responses.

`picks-unavailable.json` is the observed pre-deadline response.
`picks.sample.json` and `entry-post-deadline.sample.json` preserve the successful
post-deadline schemas with identifiers, ranks, points and financial values
replaced. Public picks contain player IDs, positions, multipliers and captaincy
but no purchase price or private selling price.
