"""Pydantic V2 schemas for the Cards API.

Owner: Carter (SWE) — feature/api-routes.

`from_attributes=True` lets response models validate directly from
SQLAlchemy ORM instances, so route handlers stay thin.
"""

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SetRead(_ORMModel):
    id: str
    name: str
    series: str
    printed_total: int | None = None
    total: int | None = None
    release_date: datetime.date | None = None
    symbol_url: str | None = None
    logo_url: str | None = None


class CardResponse(_ORMModel):
    """Single card, mapped 1:1 from ``app.db.models.Card`` columns."""

    id: str
    set_id: str
    name: str
    supertype: str | None = None
    subtypes: list[str] | None = None
    rarity: str | None = None
    number: str | None = None
    artist: str | None = None
    image_small_url: str | None = None
    image_large_url: str | None = None
    tcgplayer_url: str | None = None


class PriceHistoryResponse(_ORMModel):
    """One time-series snapshot row; ordered ASC for chart rendering."""

    snapshot_date: datetime.date
    source: str
    variant: str
    currency: str
    price_low: Decimal | None = None
    price_mid: Decimal | None = None
    price_high: Decimal | None = None
    price_market: Decimal | None = None


class PaginatedCardResponse(BaseModel):
    """Pagination envelope for card listings."""

    items: list[CardResponse]
    total: int = Field(ge=0, description="Total rows matching the filters")
    page: int = Field(ge=1)
    size: int = Field(ge=1, le=100)
