import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from gaffertalk_api.domain.errors import (
    InvalidUpstreamFplResponseError,
    UpstreamFplNotFoundError,
    UpstreamFplTimeoutError,
    UpstreamFplUnavailableError,
)
from gaffertalk_api.integrations.fpl.cache import AsyncTtlCache
from gaffertalk_api.integrations.fpl.schemas import (
    FplBootstrap,
    FplElementSummary,
    FplEntry,
    FplEntryHistory,
    FplFixture,
    FplPicks,
    FplTransfer,
)

SchemaT = TypeVar("SchemaT", bound=BaseModel)
ResultT = TypeVar("ResultT")


class FplClient:
    """Validated asynchronous client for FPL's public JSON endpoints."""

    def __init__(
        self,
        *,
        base_url: str = "https://fantasy.premierleague.com/api/",
        timeout_seconds: float = 8.0,
        max_attempts: int = 3,
        cache: AsyncTtlCache | None = None,
        client: httpx.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "GafferTalk/0.1"},
            follow_redirects=True,
        )
        self._cache = cache or AsyncTtlCache()
        self._max_attempts = max(1, max_attempts)
        self._sleeper = sleeper

    async def __aenter__(self) -> "FplClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_bootstrap(self) -> FplBootstrap:
        return await self._cached_model(
            key="bootstrap",
            path="bootstrap-static/",
            schema=FplBootstrap,
            ttl_seconds=300,
        )

    async def get_fixtures(self) -> tuple[FplFixture, ...]:
        adapter = TypeAdapter(list[FplFixture])
        fixtures = await self._cache.get_or_load(
            "fixtures",
            300,
            lambda: self._get_and_validate("fixtures/", adapter.validate_python),
        )
        return tuple(fixtures)

    async def get_element_summary(self, player_id: int) -> FplElementSummary:
        return await self._cached_model(
            key=f"element-summary:{player_id}",
            path=f"element-summary/{player_id}/",
            schema=FplElementSummary,
            ttl_seconds=3600,
        )

    async def get_entry(self, team_id: int) -> FplEntry:
        return await self._cached_model(
            key=f"entry:{team_id}",
            path=f"entry/{team_id}/",
            schema=FplEntry,
            ttl_seconds=30,
        )

    async def get_entry_history(self, team_id: int) -> FplEntryHistory:
        return await self._cached_model(
            key=f"entry-history:{team_id}",
            path=f"entry/{team_id}/history/",
            schema=FplEntryHistory,
            ttl_seconds=60,
        )

    async def get_entry_transfers(self, team_id: int) -> tuple[FplTransfer, ...]:
        adapter = TypeAdapter(list[FplTransfer])
        transfers = await self._cache.get_or_load(
            f"entry-transfers:{team_id}",
            30,
            lambda: self._get_and_validate(f"entry/{team_id}/transfers/", adapter.validate_python),
        )
        return tuple(transfers)

    async def get_picks(self, team_id: int, gameweek_id: int) -> FplPicks:
        return await self._cached_model(
            key=f"picks:{team_id}:{gameweek_id}",
            path=f"entry/{team_id}/event/{gameweek_id}/picks/",
            schema=FplPicks,
            ttl_seconds=30,
        )

    async def _cached_model(
        self,
        *,
        key: str,
        path: str,
        schema: type[SchemaT],
        ttl_seconds: float,
    ) -> SchemaT:
        return await self._cache.get_or_load(
            key,
            ttl_seconds,
            lambda: self._get_and_validate(path, schema.model_validate),
        )

    async def _get_and_validate(
        self,
        path: str,
        validator: Callable[[object], ResultT],
    ) -> ResultT:
        payload = await self._get_json(path)
        try:
            return validator(payload)
        except ValidationError as error:
            raise InvalidUpstreamFplResponseError(
                f"FPL returned an invalid response for {path}"
            ) from error

    async def _get_json(self, path: str) -> object:
        for attempt in range(self._max_attempts):
            try:
                response = await self._client.get(path)
            except httpx.TimeoutException as error:
                if attempt + 1 == self._max_attempts:
                    raise UpstreamFplTimeoutError("FPL request timed out") from error
                await self._sleeper(0.2 * (2**attempt))
                continue
            except httpx.TransportError as error:
                if attempt + 1 == self._max_attempts:
                    raise UpstreamFplUnavailableError(None, "FPL request failed") from error
                await self._sleeper(0.2 * (2**attempt))
                continue

            if response.status_code == 404:
                detail = self._error_detail(response, "FPL resource was not found")
                raise UpstreamFplNotFoundError(path, detail)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 < self._max_attempts:
                    await self._sleeper(self._retry_delay(response, attempt))
                    continue
                raise UpstreamFplUnavailableError(
                    response.status_code,
                    self._error_detail(response, "FPL service is unavailable"),
                )
            if response.is_error:
                raise UpstreamFplUnavailableError(
                    response.status_code,
                    self._error_detail(response, "FPL request was rejected"),
                )

            try:
                return response.json()
            except ValueError as error:
                raise InvalidUpstreamFplResponseError(
                    f"FPL returned non-JSON content for {path}"
                ) from error

        raise AssertionError("retry loop exited unexpectedly")

    @staticmethod
    def _error_detail(response: httpx.Response, fallback: str) -> str:
        try:
            payload = response.json()
        except ValueError:
            return fallback
        if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
            return payload["detail"]
        return fallback

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), 10.0)
            except ValueError:
                pass
        return 0.2 * (2**attempt)
