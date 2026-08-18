"""pokemontcg.io ingestion client — async httpx scaffold.

Owner: Carter (SWE). Starting point for the data-ingestion pipeline
(feature/data-ingestion branch).

TODO(carter):
  * paginate /cards per set and upsert into `cards`
  * extract tcgplayer/cardmarket price blocks into `price_history`
  * schedule daily snapshots (e.g. APScheduler or an ECS scheduled task)
  * add retry/backoff (httpx transport retries or tenacity)
"""

from types import TracebackType
from typing import Any, Self

import httpx

from app.core.config import get_settings


class PokemonTCGClient:
    """Thin async wrapper around the pokemontcg.io v2 API."""

    def __init__(self, timeout: float = 30.0) -> None:
        settings = get_settings()
        headers: dict[str, str] = {}
        if settings.pokemontcg_api_key is not None:
            headers["X-Api-Key"] = settings.pokemontcg_api_key.get_secret_value()
        self._client = httpx.AsyncClient(
            base_url=settings.pokemontcg_base_url,
            headers=headers,
            timeout=timeout,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def get_sets(self, page: int = 1, page_size: int = 250) -> dict[str, Any]:
        """Fetch one page of expansion sets."""
        resp = await self._client.get(
            "/sets", params={"page": page, "pageSize": page_size}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_cards(
        self, query: str | None = None, page: int = 1, page_size: int = 250
    ) -> dict[str, Any]:
        """Fetch one page of cards. `query` uses the API's `q` syntax,
        e.g. 'set.id:sv1'."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if query:
            params["q"] = query
        resp = await self._client.get("/cards", params=params)
        resp.raise_for_status()
        return resp.json()
