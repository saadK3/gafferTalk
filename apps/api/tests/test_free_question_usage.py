from datetime import UTC, datetime

import pytest

from gaffertalk_api.domain.models import Gameweek
from gaffertalk_api.services.free_question_usage import (
    FreeQuestionLimitExceededError,
    FreeQuestionUsageStore,
    select_quota_gameweek,
)


def gameweek(gameweek_id: int, *, current: bool = False, next_: bool = False) -> Gameweek:
    return Gameweek(
        id=gameweek_id,
        name=f"Gameweek {gameweek_id}",
        deadline_time=datetime(2026, 8, gameweek_id, 12, tzinfo=UTC),
        finished=False,
        data_checked=False,
        is_previous=False,
        is_current=current,
        is_next=next_,
    )


def test_usage_is_isolated_by_browser_and_gameweek(tmp_path) -> None:
    store = FreeQuestionUsageStore(tmp_path / "usage.sqlite3", limit=3)
    first = gameweek(1, current=True)
    second = gameweek(2, next_=True)

    assert store.status("browser-a", first).remaining == 3
    assert store.reserve("browser-a", first).remaining == 2
    assert store.status("browser-b", first).remaining == 3
    assert store.status("browser-a", second).remaining == 3


def test_fourth_question_is_rejected_and_failed_reservation_can_be_released(tmp_path) -> None:
    store = FreeQuestionUsageStore(tmp_path / "usage.sqlite3", limit=3)
    active = gameweek(1, current=True)

    assert [store.reserve("browser-a", active).remaining for _ in range(3)] == [2, 1, 0]
    with pytest.raises(FreeQuestionLimitExceededError) as caught:
        store.reserve("browser-a", active)
    assert caught.value.quota.remaining == 0

    store.release("browser-a", active)
    assert store.reserve("browser-a", active).remaining == 0


def test_current_then_next_gameweek_defines_the_reset_boundary() -> None:
    current = gameweek(1, current=True)
    next_gameweek = gameweek(2, next_=True)

    assert select_quota_gameweek((current, next_gameweek)) == current
    assert select_quota_gameweek((gameweek(1), next_gameweek)) == next_gameweek
    with pytest.raises(ValueError, match="any Gameweeks"):
        select_quota_gameweek(())
