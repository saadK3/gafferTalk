import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gaffertalk_api.domain.models import Gameweek
from gaffertalk_api.domain.recommendation_requests import FreeQuestionQuota


class FreeQuestionLimitExceededError(Exception):
    def __init__(self, quota: FreeQuestionQuota) -> None:
        super().__init__("The three free transfer questions for this Gameweek have been used.")
        self.quota = quota


def select_quota_gameweek(gameweeks: tuple[Gameweek, ...]) -> Gameweek:
    """Choose the FPL event whose deadline bounds the current planning allowance."""

    if not gameweeks:
        raise ValueError("FPL did not publish any Gameweeks")
    current = next((gameweek for gameweek in gameweeks if gameweek.is_current), None)
    if current is not None:
        return current
    upcoming = next((gameweek for gameweek in gameweeks if gameweek.is_next), None)
    if upcoming is not None:
        return upcoming
    unfinished = [gameweek for gameweek in gameweeks if not gameweek.finished]
    return min(unfinished, key=lambda gameweek: gameweek.id) if unfinished else gameweeks[-1]


@dataclass(frozen=True)
class FreeQuestionUsageStore:
    database_path: Path
    limit: int = 3

    def __post_init__(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS free_question_usage (
                    client_id TEXT NOT NULL,
                    gameweek_id INTEGER NOT NULL,
                    used INTEGER NOT NULL CHECK (used >= 0),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (client_id, gameweek_id)
                )
                """
            )

    def status(self, client_id: str, gameweek: Gameweek) -> FreeQuestionQuota:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT used FROM free_question_usage WHERE client_id = ? AND gameweek_id = ?",
                (client_id, gameweek.id),
            ).fetchone()
        return self._quota(gameweek, int(row[0]) if row else 0)

    def reserve(self, client_id: str, gameweek: Gameweek) -> FreeQuestionQuota:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT used FROM free_question_usage WHERE client_id = ? AND gameweek_id = ?",
                (client_id, gameweek.id),
            ).fetchone()
            used = int(row[0]) if row else 0
            if used >= self.limit:
                connection.rollback()
                raise FreeQuestionLimitExceededError(self._quota(gameweek, used))
            next_used = used + 1
            connection.execute(
                """
                INSERT INTO free_question_usage (client_id, gameweek_id, used, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(client_id, gameweek_id) DO UPDATE SET
                    used = excluded.used,
                    updated_at = excluded.updated_at
                """,
                (client_id, gameweek.id, next_used, now),
            )
            connection.commit()
        return self._quota(gameweek, next_used)

    def release(self, client_id: str, gameweek: Gameweek) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE free_question_usage
                SET used = MAX(used - 1, 0), updated_at = ?
                WHERE client_id = ? AND gameweek_id = ?
                """,
                (datetime.now(UTC).isoformat(), client_id, gameweek.id),
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path, timeout=5)

    def _quota(self, gameweek: Gameweek, used: int) -> FreeQuestionQuota:
        bounded_used = min(max(used, 0), self.limit)
        return FreeQuestionQuota(
            gameweek_id=gameweek.id,
            gameweek_name=gameweek.name,
            deadline_time=gameweek.deadline_time,
            limit=self.limit,
            used=bounded_used,
            remaining=max(self.limit - bounded_used, 0),
        )
