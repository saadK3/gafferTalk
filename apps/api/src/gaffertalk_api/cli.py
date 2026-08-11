import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from gaffertalk_api.config import get_settings
from gaffertalk_api.domain.errors import GafferTalkError, InvalidTeamIdError
from gaffertalk_api.domain.models import Money, SquadLookupResult
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.services.team_loader import TeamLoader

PAKISTAN_TIME = ZoneInfo("Asia/Karachi")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gaffertalk", description="GafferTalk developer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    team_parser = subparsers.add_parser("team", help="Load a public FPL team snapshot")
    team_parser.add_argument("team_id", type=int, help="Public FPL Team ID")
    team_parser.add_argument("--json", action="store_true", help="Print canonical JSON")
    return parser


async def lookup_team(team_id: int) -> SquadLookupResult:
    settings = get_settings()
    async with FplClient(
        base_url=settings.fpl_base_url,
        timeout_seconds=settings.fpl_timeout_seconds,
        max_attempts=settings.fpl_max_attempts,
    ) as client:
        return await TeamLoader(client).load(team_id)


def format_money(money: Money | None) -> str:
    if money is None:
        return "Unavailable"
    return f"£{money.tenths / 10:.1f}m"


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "Unavailable"
    return value.astimezone(PAKISTAN_TIME).strftime("%d %B %Y, %H:%M PKT")


def human_output(result: SquadLookupResult) -> str:
    entry = result.entry
    manager_name = " ".join(
        name for name in (entry.manager_first_name, entry.manager_last_name) if name
    )
    lines = [
        "GafferTalk FPL lookup",
        "",
        f"Team ID: {entry.id}",
        f"Team: {entry.team_name}",
        f"Manager: {manager_name or 'Unavailable'}",
        f"Squad status: {result.availability.status.value.upper()}",
        f"Reason: {result.availability.reason}",
    ]

    if result.snapshot is None:
        lines.append(f"Next deadline: {format_datetime(result.availability.next_deadline)}")
        return "\n".join(lines)

    snapshot = result.snapshot
    lines.extend(
        [
            f"Snapshot: {snapshot.gameweek.name}",
            f"Bank at deadline: {format_money(snapshot.bank)}",
            f"Squad value at deadline: {format_money(snapshot.squad_value)}",
            "",
            "STARTING XI",
        ]
    )
    for pick in snapshot.picks[:11]:
        player = pick.player
        captain = " (C)" if pick.is_captain else " (VC)" if pick.is_vice_captain else ""
        lines.append(
            f"{player.position.value:<3}  {player.web_name:<22} "
            f"{player.club.short_name:<3}  {format_money(player.current_price)}{captain}"
        )

    lines.extend(["", "BENCH"])
    for bench_order, pick in enumerate(snapshot.picks[11:], start=1):
        lines.append(f"{bench_order}. {pick.player.web_name} ({pick.player.position.value})")
    lines.extend(["", "Source: Public FPL deadline snapshot"])
    return "\n".join(lines)


def run(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(arguments)

    try:
        result = asyncio.run(lookup_team(parsed.team_id))
    except InvalidTeamIdError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except GafferTalkError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 3

    if parsed.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        print(human_output(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
