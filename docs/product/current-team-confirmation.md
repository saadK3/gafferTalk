# Current-team confirmation

Issue: #15

## Decision

GafferTalk uses the latest public, deadline-finalized FPL squad as an observed
snapshot. It never describes that snapshot as private live state.

The manager confirms current planning state through this flow:

1. Enter a public Team ID and load the latest published squad.
2. Review the Gameweek and deadline attached to that snapshot.
3. Continue with no squad changes, or record transfers already made by selecting
   an outgoing player and searching current FPL players in the same position.
4. Confirm captain and vice-captain from the current Starting XI.
5. Confirm current bank and free-transfer count.
6. Save a versioned current-team state locally on the device.

An exact outgoing selling price is deliberately deferred until transfer
legality depends on it. GafferTalk does not request an FPL password, session
cookie, or account access.

## Provenance

The confirmed state keeps these sources explicit:

| Field | Source |
| --- | --- |
| Deadline squad, positions and public prices | Observed FPL data |
| Recorded changes since the deadline | User supplied |
| Captain and vice-captain | User supplied confirmation |
| Current bank | User supplied |
| Free transfers | User supplied |
| Selling price | Requested later only when required |

## Validation

- Team IDs are positive integers.
- Published snapshots must contain 15 unique players, one captain and one
  vice-captain.
- Recorded replacements preserve position and cannot duplicate a current
  player.
- Captain and vice-captain must be different Starting XI players.
- Bank accepts £0.0m–£20.0m in £0.1m increments.
- Free transfers accept 0–5, matching the current FPL rules contract.
- Invalid IDs, unavailable upstream data, malformed responses and unpublished
  squads produce explicit non-success states.

The browser stores the confirmed state under the versioned local key
`gaffertalk.currentTeam.v1`. This is device-local planning state, not
authentication.
