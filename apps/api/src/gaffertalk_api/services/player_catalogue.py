from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from gaffertalk_api.domain.errors import InvalidUpstreamFplResponseError
from gaffertalk_api.domain.models import FplCatalogue, Player, Position
from gaffertalk_api.integrations.fpl.client import FplClient
from gaffertalk_api.integrations.fpl.mapper import map_catalogue


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
        normalized_query = query.casefold().strip()
        players = (
            player
            for player in catalogue.players.values()
            if player.position is position and normalized_query in player.web_name.casefold()
        )
        return tuple(sorted(players, key=lambda player: player.web_name.casefold())[:limit])
