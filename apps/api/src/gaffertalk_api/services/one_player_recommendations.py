from collections import defaultdict

from gaffertalk_api.domain.models import Fixture, FplCatalogue, Money, Player, SquadSnapshot
from gaffertalk_api.domain.recommendations import (
    RecommendationResult,
    ScoreBreakdown,
    TransferRecommendation,
)
from gaffertalk_api.domain.transfers import (
    ProposedTransfer,
    TransferLegalityStatus,
    TransferPlanningState,
)
from gaffertalk_api.services.transfer_legality import TransferLegalityService


class OnePlayerRecommendationService:
    """Rank legal same-position replacements with a transparent preseason baseline."""

    def __init__(self, legality: TransferLegalityService | None = None) -> None:
        self._legality = legality or TransferLegalityService()

    def recommend(
        self,
        *,
        squad_name: str,
        snapshot: SquadSnapshot,
        catalogue: FplCatalogue,
        fixtures: tuple[Fixture, ...],
        state: TransferPlanningState,
        outgoing_player_id: int,
        limit: int = 3,
        fixture_horizon: int = 5,
    ) -> RecommendationResult:
        squad_ids = {pick.player.id for pick in snapshot.picks}
        if outgoing_player_id not in squad_ids:
            raise ValueError("the outgoing player must be in the synthetic squad")
        outgoing = catalogue.players[outgoing_player_id]

        fixture_difficulties = self._fixture_difficulties(fixtures, fixture_horizon)
        legal_candidates: list[tuple[Player, Money, float | None, int]] = []
        for candidate in catalogue.players.values():
            if (
                candidate.id in squad_ids
                or candidate.position is not outgoing.position
                or candidate.status != "a"
            ):
                continue
            legality = self._legality.validate(
                snapshot=snapshot,
                catalogue=catalogue,
                state=state,
                transfers=(
                    ProposedTransfer(
                        outgoing_player_id=outgoing_player_id,
                        incoming_player_id=candidate.id,
                    ),
                ),
            )
            if legality.status is not TransferLegalityStatus.LEGAL:
                continue
            assert legality.remaining_bank is not None
            difficulties = fixture_difficulties.get(candidate.club.id, ())
            average = sum(difficulties) / len(difficulties) if difficulties else None
            legal_candidates.append(
                (candidate, legality.remaining_bank, average, len(difficulties))
            )

        if not legal_candidates:
            return RecommendationResult(
                squad_name=squad_name,
                outgoing=outgoing,
                recommendations=(),
                assumptions=self._assumptions(fixture_horizon),
            )

        max_points = max(candidate.total_points for candidate, *_ in legal_candidates) or 1
        max_value = (
            max(
                candidate.total_points / max(candidate.current_price.tenths, 1)
                for candidate, *_ in legal_candidates
            )
            or 1
        )
        ranked: list[tuple[float, Player, Money, float | None, int, ScoreBreakdown]] = []
        for candidate, remaining_bank, average, fixture_count in legal_candidates:
            historical = 100 * candidate.total_points / max_points
            fixture_score = 50.0 if average is None else 100 * (6 - average) / 5
            value_ratio = candidate.total_points / max(candidate.current_price.tenths, 1)
            value = 100 * value_ratio / max_value
            breakdown = ScoreBreakdown(
                historical_output=round(historical, 1),
                upcoming_fixtures=round(fixture_score, 1),
                value=round(value, 1),
            )
            score = 0.45 * historical + 0.35 * fixture_score + 0.20 * value
            ranked.append((score, candidate, remaining_bank, average, fixture_count, breakdown))

        ranked.sort(key=lambda item: (-item[0], item[1].current_price.tenths, item[1].id))
        recommendations = tuple(
            self._build_recommendation(
                rank=index,
                outgoing=outgoing,
                candidate=candidate,
                score=score,
                breakdown=breakdown,
                remaining_bank=remaining_bank,
                average=average,
                fixture_count=fixture_count,
            )
            for index, (
                score,
                candidate,
                remaining_bank,
                average,
                fixture_count,
                breakdown,
            ) in enumerate(ranked[:limit], start=1)
        )
        return RecommendationResult(
            squad_name=squad_name,
            outgoing=outgoing,
            recommendations=recommendations,
            assumptions=self._assumptions(fixture_horizon),
        )

    @staticmethod
    def _fixture_difficulties(
        fixtures: tuple[Fixture, ...], horizon: int
    ) -> dict[int, tuple[int, ...]]:
        by_club: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for fixture in fixtures:
            if fixture.finished or fixture.gameweek_id is None:
                continue
            by_club[fixture.home_club_id].append((fixture.gameweek_id, fixture.home_difficulty))
            by_club[fixture.away_club_id].append((fixture.gameweek_id, fixture.away_difficulty))
        return {
            club_id: tuple(difficulty for _, difficulty in sorted(items)[:horizon])
            for club_id, items in by_club.items()
        }

    @staticmethod
    def _build_recommendation(
        *,
        rank: int,
        outgoing: Player,
        candidate: Player,
        score: float,
        breakdown: ScoreBreakdown,
        remaining_bank: Money,
        average: float | None,
        fixture_count: int,
    ) -> TransferRecommendation:
        fixture_reason = (
            f"Average fixture difficulty {average:.2f} across the next {fixture_count} fixtures."
            if average is not None
            else "No scheduled fixtures were available; a neutral fixture score was used."
        )
        if average is not None and average >= 3.4:
            trade_off = "The upcoming fixture run is relatively difficult."
        elif remaining_bank.tenths <= 5:
            trade_off = "This option leaves very little flexibility in the bank."
        elif candidate.total_points < outgoing.total_points:
            trade_off = "Previous-season output is lower than the outgoing player's baseline."
        else:
            trade_off = "Preseason scoring cannot yet reflect current-season form or minutes."
        return TransferRecommendation(
            rank=rank,
            outgoing=outgoing,
            incoming=candidate,
            score=round(score, 1),
            score_breakdown=breakdown,
            average_fixture_difficulty=round(average, 2) if average is not None else None,
            fixtures_considered=fixture_count,
            remaining_bank=remaining_bank,
            reasons=(
                "Legal same-position transfer under budget and the three-per-club limit.",
                fixture_reason,
                f"Official FPL baseline: {candidate.total_points} points at "
                f"£{candidate.current_price.tenths / 10:.1f}m.",
            ),
            trade_off=trade_off,
        )

    @staticmethod
    def _assumptions(fixture_horizon: int) -> tuple[str, ...]:
        return (
            "Players, prices, availability and fixtures were loaded live from FPL.",
            "The squad, bank, free transfer and selling price are confirmed planning inputs.",
            "Before Gameweek 1, official performance totals are a previous-season "
            "baseline, not current form.",
            f"Score weights: historical output 45%, next {fixture_horizon} fixture "
            "difficulty 35%, value 20%.",
            "This first version does not model expected minutes, rotation, tactical "
            "role or projected points.",
        )
