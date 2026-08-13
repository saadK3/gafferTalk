import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gaffertalk_api.config import get_settings
from gaffertalk_api.domain.errors import GafferTalkError, InvalidTeamIdError
from gaffertalk_api.domain.models import Fixture, FplCatalogue, Money, SquadLookupResult
from gaffertalk_api.domain.recommendations import RecommendationResult
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.fpl.mapper import map_catalogue, map_fixtures
from gaffertalk_api.services.one_player_recommendations import OnePlayerRecommendationService
from gaffertalk_api.services.synthetic_squad import load_synthetic_squad
from gaffertalk_api.services.team_loader import TeamLoader

PAKISTAN_TIME = ZoneInfo("Asia/Karachi")
DEFAULT_SYNTHETIC_SQUAD = (
    Path(__file__).parents[4] / "tests/fixtures/recommendations/synthetic-squad.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gaffertalk", description="GafferTalk developer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    team_parser = subparsers.add_parser("team", help="Load a public FPL team snapshot")
    team_parser.add_argument("team_id", type=int, help="Public FPL Team ID")
    team_parser.add_argument("--json", action="store_true", help="Print canonical JSON")
    recommend_parser = subparsers.add_parser(
        "recommend-one", help="Rank legal replacements for the synthetic squad"
    )
    recommend_parser.add_argument(
        "--out", default="Yates", help="Exact web name of the player to transfer out"
    )
    recommend_parser.add_argument("--json", action="store_true", help="Print canonical JSON")
    return parser


async def lookup_team(team_id: int) -> SquadLookupResult:
    settings = get_settings()
    async with FplClient(
        base_url=settings.fpl_base_url,
        timeout_seconds=settings.fpl_timeout_seconds,
        max_attempts=settings.fpl_max_attempts,
    ) as client:
        return await TeamLoader(client).load(team_id)


async def load_live_recommendation_data() -> tuple[FplCatalogue, tuple[Fixture, ...]]:
    settings = get_settings()
    async with FplClient(
        base_url=settings.fpl_base_url,
        timeout_seconds=settings.fpl_timeout_seconds,
        max_attempts=settings.fpl_max_attempts,
    ) as client:
        bootstrap, raw_fixtures = await asyncio.gather(
            client.get_bootstrap(), client.get_fixtures()
        )
    retrieved_at = datetime.now(UTC)
    return map_catalogue(bootstrap, retrieved_at), map_fixtures(raw_fixtures)


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


def recommendation_output(result: RecommendationResult) -> str:
    lines = [
        "GafferTalk one-player recommendations",
        "",
        f"Squad: {result.squad_name}",
        f"Transfer out: {result.outgoing.web_name} "
        f"({result.outgoing.position.value}, {result.outgoing.club.short_name}, "
        f"{format_money(result.outgoing.current_price)})",
        "Data source: LIVE FPL players, prices, availability and fixtures",
        "",
    ]
    if not result.recommendations:
        lines.append("No legal available replacements were found.")
    for item in result.recommendations:
        lines.extend(
            [
                f"#{item.rank} {item.incoming.web_name} — {item.incoming.club.short_name} — "
                f"{format_money(item.incoming.current_price)} — score {item.score:.1f}/100",
                f"   Bank after transfer: {format_money(item.remaining_bank)}",
                "   Score: "
                f"output {item.score_breakdown.historical_output:.1f}, "
                f"fixtures {item.score_breakdown.upcoming_fixtures:.1f}, "
                f"value {item.score_breakdown.value:.1f}",
                *(f"   Why: {reason}" for reason in item.reasons),
                f"   Trade-off: {item.trade_off}",
                "",
            ]
        )
    lines.append("ASSUMPTIONS")
    lines.extend(f"- {assumption}" for assumption in result.assumptions)
    return "\n".join(lines)


async def recommend_one(outgoing_name: str) -> RecommendationResult:
    catalogue, fixtures = await load_live_recommendation_data()
    definition, snapshot, state = load_synthetic_squad(DEFAULT_SYNTHETIC_SQUAD, catalogue)
    matches = [
        pick.player
        for pick in snapshot.picks
        if pick.player.web_name.casefold() == outgoing_name.casefold().strip()
    ]
    if len(matches) != 1:
        available = ", ".join(pick.player.web_name for pick in snapshot.picks)
        raise ValueError(f"choose one squad player exactly; available: {available}")
    return OnePlayerRecommendationService().recommend(
        squad_name=definition.name,
        snapshot=snapshot,
        catalogue=catalogue,
        fixtures=fixtures,
        state=state,
        outgoing_player_id=matches[0].id,
    )


def run(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(arguments)

    try:
        if parsed.command == "recommend-one":
            recommendation = asyncio.run(recommend_one(parsed.out))
            if parsed.json:
                print(json.dumps(recommendation.model_dump(mode="json"), indent=2))
            else:
                print(recommendation_output(recommendation))
            return 0
        result = asyncio.run(lookup_team(parsed.team_id))
    except InvalidTeamIdError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except GafferTalkError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 3
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    if parsed.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        print(human_output(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
