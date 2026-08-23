import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from gaffertalk_api.domain.errors import InvalidUpstreamFplResponseError
from gaffertalk_api.domain.models import FplCatalogue, Player, Position
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.fpl.mapper import map_catalogue

NAME_TRANSLATIONS: dict[str, str | int | None] = {
    "ø": "o",
    "đ": "d",
    "ð": "d",
    "ł": "l",
    "þ": "th",
}


class PlayerCatalogueLoader:
    """Load the public FPL player catalogue through the canonical mapper."""

    def __init__(
        self,
        client: FplClient,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._clock = clock

    async def load(self) -> FplCatalogue:
        bootstrap = await self._client.get_bootstrap()
        try:
            return map_catalogue(bootstrap, self._clock())
        except ValidationError as error:
            raise InvalidUpstreamFplResponseError(
                "FPL catalogue could not be mapped into the canonical domain"
            ) from error

    async def search(
        self,
        *,
        position: Position,
        query: str,
        limit: int = 30,
    ) -> tuple[Player, ...]:
        catalogue = await self.load()
        normalized_query = self._normalize_name(query)
        players = (
            player
            for player in catalogue.players.values()
            if player.position is position
            and normalized_query in self._normalize_name(player.web_name)
        )
        return tuple(sorted(players, key=lambda player: player.web_name.casefold())[:limit])

    @staticmethod
    def _normalize_name(value: str) -> str:
        folded = value.casefold().translate(str.maketrans(NAME_TRANSLATIONS))
        return "".join(
            character
            for character in unicodedata.normalize("NFKD", folded).strip()
            if not unicodedata.combining(character)
        )
