"""pokemontcg.io ingestion pipeline.

Owner: Carter (SWE) — feature/data-ingestion.

Flow (respects FK constraints):
    1. ``ingest_sets``  — GET /v2/sets      → upsert ``sets``
    2. ``ingest_cards`` — GET /v2/cards     → upsert ``cards`` +
       append-only ``price_history`` snapshots (tcgplayer), one row per
       finish variant per day.

Engineering notes:
    * All DB writes go through ``AsyncSession`` using PostgreSQL dialect
      upserts (``INSERT … ON CONFLICT``); one commit **per page** (250
      records), never per card.
    * ``httpx.AsyncClient`` with a 30s timeout and exponential backoff +
      jitter on 429/5xx/transport errors; honors ``Retry-After``.
    * Structured progress logging per page and per set.

Manual test run inside the Docker container:

    docker compose exec api python -m app.services.ingestion --sets-only
    docker compose exec api python -m app.services.ingestion --set-id sv1
    docker compose exec api python -m app.services.ingestion          # full catalog
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import TracebackType
from typing import Any, Self

import httpx
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Card, PriceHistory, Set

try:  # pragma: no cover - import guard exercised only on misconfigured envs
    from sqlalchemy.dialects.postgresql import insert as pg_insert
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PostgreSQL dialect required for ingestion upserts") from exc

logger = logging.getLogger(__name__)

PAGE_SIZE = 250
PRICE_SOURCE = "tcgplayer"
#: Priority used when a single "primary" market price is needed.
VARIANT_PRIORITY: tuple[str, ...] = ("holofoil", "normal", "reverseHolofoil")
RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class PokemonTCGClient:
    """Async client for pokemontcg.io v2 with retry/backoff built in."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        max_retries: int = 5,
        backoff_base: float = 1.0,
        backoff_cap: float = 60.0,
    ) -> None:
        settings = get_settings()
        headers: dict[str, str] = {}
        if settings.pokemontcg_api_key is not None:
            headers["X-Api-Key"] = settings.pokemontcg_api_key.get_secret_value()
        else:
            logger.warning(
                "POKEMONTCG_API_KEY not set — running at the low anonymous rate limit"
            )
        self._client = httpx.AsyncClient(
            base_url=settings.pokemontcg_base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _backoff_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self._backoff_cap)
            except ValueError:
                pass  # non-numeric Retry-After → fall through to backoff
        delay = self._backoff_base * (2**attempt)
        return min(delay, self._backoff_cap) * (0.5 + random.random() / 2)

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """GET with retries on transport errors and retryable HTTP statuses."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._client.get(path, params=params)
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    break
                delay = self._backoff_delay(attempt, None)
                logger.warning(
                    "transport error on %s (attempt %d/%d), retrying in %.1fs: %s",
                    path, attempt + 1, self._max_retries, delay, exc,
                )
                await asyncio.sleep(delay)
                continue

            if resp.status_code in RETRYABLE_STATUS and attempt < self._max_retries:
                delay = self._backoff_delay(attempt, resp.headers.get("Retry-After"))
                logger.warning(
                    "HTTP %d on %s (attempt %d/%d), retrying in %.1fs",
                    resp.status_code, path, attempt + 1, self._max_retries, delay,
                )
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
            return payload

        raise RuntimeError(
            f"GET {path} failed after {self._max_retries + 1} attempts"
        ) from last_exc

    async def iter_pages(
        self, path: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[tuple[int, list[dict[str, Any]]]]:
        """Yield ``(page_number, records)`` until the API is exhausted."""
        base_params = dict(params or {})
        page = 1
        while True:
            payload = await self._get_json(
                path, {**base_params, "page": page, "pageSize": PAGE_SIZE}
            )
            data: list[dict[str, Any]] = payload.get("data", [])
            if not data:
                return
            yield page, data
            total = int(payload.get("totalCount", 0))
            if page * PAGE_SIZE >= total:
                return
            page += 1


# ---------------------------------------------------------------------------
# API payload → model-row mapping (field names match app/db/models.py exactly)
# ---------------------------------------------------------------------------


def _parse_release_date(raw: str | None) -> datetime.date | None:
    """pokemontcg.io dates look like ``2023/03/31``."""
    if not raw:
        return None
    try:
        return datetime.datetime.strptime(raw, "%Y/%m/%d").date()
    except ValueError:
        logger.warning("unparseable release date %r", raw)
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        logger.warning("unparseable price value %r", value)
        return None


def build_set_row(payload: dict[str, Any]) -> dict[str, Any]:
    images = payload.get("images") or {}
    return {
        "id": payload["id"],
        "name": payload["name"],
        "series": payload.get("series") or "Unknown",
        "printed_total": payload.get("printedTotal"),
        "total": payload.get("total"),
        "ptcgo_code": payload.get("ptcgoCode"),
        "release_date": _parse_release_date(payload.get("releaseDate")),
        "symbol_url": images.get("symbol"),
        "logo_url": images.get("logo"),
    }


def build_card_row(payload: dict[str, Any]) -> dict[str, Any]:
    images = payload.get("images") or {}
    tcgplayer = payload.get("tcgplayer") or {}
    return {
        "id": payload["id"],
        "set_id": (payload.get("set") or {}).get("id")
        or payload["id"].rsplit("-", 1)[0],
        "name": payload["name"],
        "supertype": payload.get("supertype"),
        "subtypes": payload.get("subtypes"),
        "rarity": payload.get("rarity"),
        "number": payload.get("number"),
        "artist": payload.get("artist"),
        "national_pokedex_numbers": payload.get("nationalPokedexNumbers"),
        "image_small_url": images.get("small"),
        "image_large_url": images.get("large"),
        "tcgplayer_url": tcgplayer.get("url"),
    }


def build_price_rows(
    payload: dict[str, Any], snapshot_date: datetime.date
) -> list[dict[str, Any]]:
    """One append-only ``price_history`` row per tcgplayer finish variant."""
    prices: dict[str, Any] = (payload.get("tcgplayer") or {}).get("prices") or {}
    rows: list[dict[str, Any]] = []
    for variant, block in prices.items():
        if not isinstance(block, dict):
            continue
        row = {
            "card_id": payload["id"],
            "source": PRICE_SOURCE,
            "variant": variant,
            "currency": "USD",
            "price_low": _to_decimal(block.get("low")),
            "price_mid": _to_decimal(block.get("mid")),
            "price_high": _to_decimal(block.get("high")),
            "price_market": _to_decimal(block.get("market")),
            "snapshot_date": snapshot_date,
        }
        if any(
            row[k] is not None
            for k in ("price_low", "price_mid", "price_high", "price_market")
        ):
            rows.append(row)
    return rows


def select_primary_market_price(payload: dict[str, Any]) -> Decimal | None:
    """Single representative market price: holofoil > normal > reverseHolofoil,
    falling back to any variant that has a market value."""
    prices: dict[str, Any] = (payload.get("tcgplayer") or {}).get("prices") or {}
    ordered = [*VARIANT_PRIORITY, *sorted(set(prices) - set(VARIANT_PRIORITY))]
    for variant in ordered:
        block = prices.get(variant)
        if isinstance(block, dict):
            market = _to_decimal(block.get("market"))
            if market is not None:
                return market
    return None


# ---------------------------------------------------------------------------
# Upserts (PostgreSQL ON CONFLICT)
# ---------------------------------------------------------------------------


async def upsert_sets(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    stmt = pg_insert(Set).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Set.id],
        set_={
            "name": stmt.excluded.name,
            "series": stmt.excluded.series,
            "printed_total": stmt.excluded.printed_total,
            "total": stmt.excluded.total,
            "ptcgo_code": stmt.excluded.ptcgo_code,
            "release_date": stmt.excluded.release_date,
            "symbol_url": stmt.excluded.symbol_url,
            "logo_url": stmt.excluded.logo_url,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)


async def upsert_cards(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    stmt = pg_insert(Card).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Card.id],
        set_={
            "set_id": stmt.excluded.set_id,
            "name": stmt.excluded.name,
            "supertype": stmt.excluded.supertype,
            "subtypes": stmt.excluded.subtypes,
            "rarity": stmt.excluded.rarity,
            "number": stmt.excluded.number,
            "artist": stmt.excluded.artist,
            "national_pokedex_numbers": stmt.excluded.national_pokedex_numbers,
            "image_small_url": stmt.excluded.image_small_url,
            "image_large_url": stmt.excluded.image_large_url,
            "tcgplayer_url": stmt.excluded.tcgplayer_url,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)


async def insert_price_snapshots(
    session: AsyncSession, rows: list[dict[str, Any]]
) -> None:
    """Append-only inserts; re-running the same day refreshes that day's row
    instead of violating uq_price_snapshot."""
    if not rows:
        return
    stmt = pg_insert(PriceHistory).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_price_snapshot",
        set_={
            "price_low": stmt.excluded.price_low,
            "price_mid": stmt.excluded.price_mid,
            "price_high": stmt.excluded.price_high,
            "price_market": stmt.excluded.price_market,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class IngestionStats:
    sets: int = 0
    cards: int = 0
    price_rows: int = 0
    pages: int = 0
    started_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    def summary(self) -> str:
        elapsed = (
            datetime.datetime.now(datetime.timezone.utc) - self.started_at
        ).total_seconds()
        return (
            f"{self.sets} sets, {self.cards} cards, {self.price_rows} price rows "
            f"across {self.pages} pages in {elapsed:.1f}s"
        )


async def ingest_sets(
    session: AsyncSession, client: PokemonTCGClient, stats: IngestionStats
) -> None:
    """Ingest all expansion sets (must run before cards — FK)."""
    async for page, records in client.iter_pages("/sets"):
        rows = [build_set_row(r) for r in records]
        await upsert_sets(session, rows)
        await session.commit()  # one commit per page
        stats.sets += len(rows)
        stats.pages += 1
        logger.info("sets page %d: upserted %d (total %d)", page, len(rows), stats.sets)


async def ingest_cards(
    session: AsyncSession,
    client: PokemonTCGClient,
    stats: IngestionStats,
    *,
    set_id: str | None = None,
    include_prices: bool = True,
) -> None:
    """Ingest cards (and price snapshots) for one set, or the whole catalog."""
    params: dict[str, Any] = {}
    scope = "catalog"
    if set_id:
        params["q"] = f"set.id:{set_id}"
        scope = f"set {set_id}"

    snapshot_date = datetime.datetime.now(datetime.timezone.utc).date()

    async for page, records in client.iter_pages("/cards", params):
        card_rows = [build_card_row(r) for r in records]
        await upsert_cards(session, card_rows)

        price_rows: list[dict[str, Any]] = []
        if include_prices:
            for record in records:
                price_rows.extend(build_price_rows(record, snapshot_date))
            await insert_price_snapshots(session, price_rows)

        await session.commit()  # one commit per page, not per card
        stats.cards += len(card_rows)
        stats.price_rows += len(price_rows)
        stats.pages += 1
        logger.info(
            "%s page %d: upserted %d cards, %d price rows (totals: %d cards, %d prices)",
            scope, page, len(card_rows), len(price_rows), stats.cards, stats.price_rows,
        )


async def run_ingestion(
    *,
    set_id: str | None = None,
    sets_only: bool = False,
    include_prices: bool = True,
) -> IngestionStats:
    """Standalone async runner — opens its own session; safe outside FastAPI.

    Trigger manually inside the container:
        docker compose exec api python -m app.services.ingestion
    """
    # Imported here so importing this module never requires a configured DB.
    from app.db.session import AsyncSessionFactory

    stats = IngestionStats()
    async with PokemonTCGClient() as client:
        async with AsyncSessionFactory() as session:
            try:
                await ingest_sets(session, client, stats)
                if not sets_only:
                    await ingest_cards(
                        session, client, stats,
                        set_id=set_id, include_prices=include_prices,
                    )
            except Exception:
                await session.rollback()
                logger.exception("ingestion aborted; last page rolled back")
                raise
    logger.info("ingestion complete: %s", stats.summary())
    return stats


# ---------------------------------------------------------------------------
# CLI trigger
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.services.ingestion",
        description="Ingest pokemontcg.io sets/cards/prices into PostgreSQL.",
    )
    parser.add_argument("--set-id", help="only ingest cards for one set, e.g. sv1")
    parser.add_argument(
        "--sets-only", action="store_true", help="ingest expansion sets and stop"
    )
    parser.add_argument(
        "--no-prices", action="store_true", help="skip price_history snapshots"
    )
    parser.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    asyncio.run(
        run_ingestion(
            set_id=args.set_id,
            sets_only=args.sets_only,
            include_prices=not args.no_prices,
        )
    )


if __name__ == "__main__":
    main()
