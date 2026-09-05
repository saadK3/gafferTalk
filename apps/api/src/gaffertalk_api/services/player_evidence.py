from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from gaffertalk_api.domain.models import Money, Player
from gaffertalk_api.domain.player_evidence import (
    CurrentFplEvidence,
    EvidenceAvailability,
    EvidenceConflict,
    EvidenceFreshness,
    EvidenceSource,
    GameweekHistoryEvidence,
    HistoricalExpectedInvolvement,
    MatchEvidence,
    PlayerEvidence,
    PlayerEvidenceReport,
    PlayerEvidenceRequest,
    RecentHistoryEvidence,
    ScheduledFixtureEvidence,
    SeasonTotalsEvidence,
)
from gaffertalk_api.integrations.fpl.client import FplObservation
from gaffertalk_api.integrations.fpl.mapper import map_catalogue
from gaffertalk_api.integrations.fpl.schemas import (
    FplBootstrap,
    FplElement,
    FplElementFixture,
    FplElementHistory,
    FplElementSummary,
    FplFixture,
)


class PlayerEvidenceService:
    """Build inspectable facts for players without scoring or forecasting them."""

    def build(
        self,
        *,
        request: PlayerEvidenceRequest,
        bootstrap: FplObservation[FplBootstrap],
        fixtures: FplObservation[tuple[FplFixture, ...]],
        summaries: dict[int, FplObservation[FplElementSummary] | None],
        generated_at: datetime,
    ) -> PlayerEvidenceReport:
        catalogue = map_catalogue(bootstrap.value, bootstrap.fetched_at)
        raw_players = {player.id: player for player in bootstrap.value.elements}
        unknown = set(request.player_ids) - set(catalogue.players)
        if unknown:
            raise ValueError(f"players are not in the current FPL catalogue: {sorted(unknown)}")

        reports = tuple(
            self._player_report(
                request=request,
                raw_player=raw_players[player_id],
                player=catalogue.players[player_id],
                bootstrap=bootstrap,
                fixtures=fixtures,
                summary=summaries.get(player_id),
            )
            for player_id in request.player_ids
        )
        sources = self._unique_sources(
            [
                self._source(bootstrap),
                self._source(fixtures),
                *(
                    self._source(summary)
                    for player_id in request.player_ids
                    if (summary := summaries.get(player_id)) is not None
                ),
            ]
        )
        stale_after = timedelta(minutes=request.stale_after_minutes)
        freshness = (
            EvidenceFreshness.CURRENT
            if all(
                timedelta(0) <= generated_at - source.fetched_at <= stale_after
                for source in sources
            )
            else EvidenceFreshness.STALE
        )
        return PlayerEvidenceReport(
            generated_at=generated_at,
            freshness=freshness,
            players=reports,
            sources=sources,
            assumptions=(
                "FPL status and news are publisher observations, not guarantees of selection.",
                "Expected goals and expected assists describe historical model output; they "
                "are not forecasts of future returns.",
                "Upcoming fixtures may change and should be refreshed before a decision.",
            ),
        )

    def _player_report(
        self,
        *,
        request: PlayerEvidenceRequest,
        raw_player: FplElement,
        player: Player,
        bootstrap: FplObservation[FplBootstrap],
        fixtures: FplObservation[tuple[FplFixture, ...]],
        summary: FplObservation[FplElementSummary] | None,
    ) -> PlayerEvidence:
        missing: list[str] = []
        bootstrap_source = self._source(bootstrap, published_at=raw_player.news_added)

        def observed(field: str, path: str) -> Any | None:
            if field not in raw_player.model_fields_set:
                missing.append(path)
                return None
            return getattr(raw_player, field)

        current = CurrentFplEvidence(
            price=(
                Money(tenths=raw_player.now_cost)
                if "now_cost" in raw_player.model_fields_set
                else None
            ),
            status=observed("status", "current.status"),
            chance_of_playing_next_round=observed(
                "chance_of_playing_next_round",
                "current.chance_of_playing_next_round",
            ),
            news=observed("news", "current.news"),
            news_published_at=observed("news_added", "current.news_published_at"),
            source=bootstrap_source,
        )
        if "now_cost" not in raw_player.model_fields_set:
            missing.append("current.price")

        season_totals = SeasonTotalsEvidence(
            points=observed("total_points", "season_totals.points"),
            minutes=observed("minutes", "season_totals.minutes"),
            starts=observed("starts", "season_totals.starts"),
            goals=observed("goals_scored", "season_totals.goals"),
            assists=observed("assists", "season_totals.assists"),
            bonus=observed("bonus", "season_totals.bonus"),
            expected_goals=observed(
                "expected_goals", "season_totals.expected_goals"
            ),
            expected_assists=observed(
                "expected_assists", "season_totals.expected_assists"
            ),
            source=bootstrap_source,
        )

        recent = None
        if summary is None:
            missing.append("recent_history")
        else:
            recent, recent_missing = self._recent_history(
                summary, requested_gameweeks=request.recent_gameweeks
            )
            missing.extend(recent_missing)

        upcoming, conflicts = self._upcoming_fixtures(
            club_id=player.club.id,
            global_fixtures=fixtures,
            summary=summary,
        )
        if not upcoming:
            missing.append("upcoming_fixtures")

        unique_missing = tuple(dict.fromkeys(missing))
        availability = (
            EvidenceAvailability.OBSERVED
            if not unique_missing and not conflicts
            else EvidenceAvailability.PARTIAL
        )
        return PlayerEvidence(
            player_id=player.id,
            web_name=player.web_name,
            club=player.club,
            position=player.position,
            availability=availability,
            current=current,
            season_totals=season_totals,
            recent_history=recent,
            upcoming_fixtures=upcoming,
            missing_fields=unique_missing,
            conflicts=conflicts,
        )

    def _recent_history(
        self,
        summary: FplObservation[FplElementSummary],
        *,
        requested_gameweeks: int,
    ) -> tuple[RecentHistoryEvidence, tuple[str, ...]]:
        source = self._source(summary)
        by_gameweek: dict[int, list[FplElementHistory]] = defaultdict(list)
        for row in summary.value.history:
            by_gameweek[row.round].append(row)
        selected_ids = tuple(sorted(by_gameweek)[-requested_gameweeks:])
        missing: list[str] = []
        gameweeks: list[GameweekHistoryEvidence] = []
        selected_rows: list[FplElementHistory] = []
        for gameweek_id in selected_ids:
            rows = sorted(
                by_gameweek[gameweek_id],
                key=lambda row: (
                    row.kickoff_time
                    or datetime.min.replace(tzinfo=source.fetched_at.tzinfo),
                    row.fixture or 0,
                ),
            )
            selected_rows.extend(rows)
            matches = tuple(self._match(row, source, missing) for row in rows)
            gameweeks.append(
                GameweekHistoryEvidence(
                    gameweek_id=gameweek_id,
                    matches=matches,
                    total_points=self._complete_sum(rows, "total_points"),
                    total_minutes=self._complete_sum(rows, "minutes"),
                    total_starts=self._complete_sum(rows, "starts"),
                )
            )

        expected_goals = self._complete_float_sum(selected_rows, "expected_goals")
        expected_assists = self._complete_float_sum(selected_rows, "expected_assists")
        minutes = self._complete_sum(selected_rows, "minutes")
        if selected_rows:
            for field in ("minutes", "expected_goals", "expected_assists"):
                if any(field not in row.model_fields_set for row in selected_rows):
                    missing.append(f"recent_history.expected_involvement.{field}")
        return (
            RecentHistoryEvidence(
                requested_gameweeks=requested_gameweeks,
                included_gameweek_ids=selected_ids,
                match_count=len(selected_rows),
                gameweeks=tuple(gameweeks),
                expected_involvement=HistoricalExpectedInvolvement(
                    expected_goals=expected_goals,
                    expected_assists=expected_assists,
                    minutes_denominator=minutes,
                    gameweek_ids=selected_ids,
                    match_count=len(selected_rows),
                    source=source,
                ),
                source=source,
            ),
            tuple(dict.fromkeys(missing)),
        )

    @staticmethod
    def _match(
        row: FplElementHistory,
        source: EvidenceSource,
        missing: list[str],
    ) -> MatchEvidence:
        def value(field: str) -> Any | None:
            if field not in row.model_fields_set:
                missing.append(f"recent_history.matches.{field}")
                return None
            return getattr(row, field)

        return MatchEvidence(
            fixture_id=value("fixture"),
            opponent_club_id=value("opponent_team"),
            was_home=value("was_home"),
            kickoff_time=value("kickoff_time"),
            points=value("total_points"),
            minutes=value("minutes"),
            starts=value("starts"),
            expected_goals=value("expected_goals"),
            expected_assists=value("expected_assists"),
            source=source,
        )

    def _upcoming_fixtures(
        self,
        *,
        club_id: int,
        global_fixtures: FplObservation[tuple[FplFixture, ...]],
        summary: FplObservation[FplElementSummary] | None,
    ) -> tuple[tuple[ScheduledFixtureEvidence, ...], tuple[EvidenceConflict, ...]]:
        global_rows = {
            fixture.id: fixture
            for fixture in global_fixtures.value
            if not fixture.finished and club_id in {fixture.team_h, fixture.team_a}
        }
        element_rows = {
            fixture.id: fixture
            for fixture in (summary.value.fixtures if summary is not None else [])
            if not fixture.finished
        }
        fixture_ids = sorted(set(global_rows) | set(element_rows))
        output: list[ScheduledFixtureEvidence] = []
        conflicts: list[EvidenceConflict] = []
        for fixture_id in fixture_ids:
            global_row = global_rows.get(fixture_id)
            element_row = element_rows.get(fixture_id)
            if global_row is not None:
                is_home = global_row.team_h == club_id
                opponent = global_row.team_a if is_home else global_row.team_h
                difficulty = (
                    global_row.team_h_difficulty
                    if is_home
                    else global_row.team_a_difficulty
                )
                gameweek_id = global_row.event
                kickoff_time = global_row.kickoff_time
            elif element_row is not None:
                is_home = element_row.is_home
                opponent = element_row.team_a if is_home else element_row.team_h
                difficulty = element_row.difficulty
                gameweek_id = element_row.event
                kickoff_time = element_row.kickoff_time
            else:
                continue

            sources = [self._source(global_fixtures)]
            if summary is not None and element_row is not None:
                sources.append(self._source(summary))
            if global_row is None:
                sources = [self._source(summary)] if summary is not None else []
            if global_row is not None and element_row is not None:
                assert summary is not None
                contradiction = self._fixture_contradiction(
                    club_id=club_id,
                    global_row=global_row,
                    element_row=element_row,
                )
                if contradiction:
                    conflicts.append(
                        EvidenceConflict(
                            code="fixture_source_mismatch",
                            message=f"Fixture {fixture_id} differs between FPL endpoints: "
                            + ", ".join(contradiction),
                            source_endpoints=(global_fixtures.endpoint, summary.endpoint),
                        )
                    )
            output.append(
                ScheduledFixtureEvidence(
                    fixture_id=fixture_id,
                    gameweek_id=gameweek_id,
                    kickoff_time=kickoff_time,
                    opponent_club_id=opponent,
                    is_home=is_home,
                    difficulty=difficulty,
                    sources=tuple(sources),
                )
            )
        output.sort(key=lambda row: (row.kickoff_time is None, row.kickoff_time, row.fixture_id))
        return tuple(output), tuple(conflicts)

    @staticmethod
    def _fixture_contradiction(
        *,
        club_id: int,
        global_row: FplFixture,
        element_row: FplElementFixture,
    ) -> tuple[str, ...]:
        is_home = global_row.team_h == club_id
        difficulty = (
            global_row.team_h_difficulty if is_home else global_row.team_a_difficulty
        )
        mismatches = []
        if global_row.event != element_row.event:
            mismatches.append("Gameweek")
        if global_row.kickoff_time != element_row.kickoff_time:
            mismatches.append("kickoff")
        if (global_row.team_h, global_row.team_a) != (
            element_row.team_h,
            element_row.team_a,
        ):
            mismatches.append("clubs")
        if is_home != element_row.is_home:
            mismatches.append("home/away")
        if difficulty != element_row.difficulty:
            mismatches.append("difficulty")
        return tuple(mismatches)

    @staticmethod
    def _complete_sum(rows: list[FplElementHistory], field: str) -> int | None:
        if not rows or any(field not in row.model_fields_set for row in rows):
            return None
        return sum(int(getattr(row, field)) for row in rows)

    @staticmethod
    def _complete_float_sum(
        rows: list[FplElementHistory], field: str
    ) -> float | None:
        if not rows or any(field not in row.model_fields_set for row in rows):
            return None
        return round(sum(float(getattr(row, field)) for row in rows), 3)

    @staticmethod
    def _source(
        observation: FplObservation[Any],
        *,
        published_at: datetime | None = None,
    ) -> EvidenceSource:
        return EvidenceSource(
            endpoint=observation.endpoint,
            fetched_at=observation.fetched_at,
            published_at=published_at,
        )

    @staticmethod
    def _unique_sources(sources: list[EvidenceSource]) -> tuple[EvidenceSource, ...]:
        unique: dict[tuple[str, datetime, datetime | None], EvidenceSource] = {}
        for source in sources:
            unique.setdefault(
                (source.endpoint, source.fetched_at, source.published_at), source
            )
        return tuple(unique.values())
