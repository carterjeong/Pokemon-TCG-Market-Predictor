"""Pydantic V2 read schemas for API responses.

Owner: Carter (SWE). `from_attributes=True` lets these validate directly
from ORM instances.
"""

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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


class PricePointRead(_ORMModel):
    source: str
    variant: str
    currency: str
    price_low: Decimal | None = None
    price_mid: Decimal | None = None
    price_high: Decimal | None = None
    price_market: Decimal | None = None
    snapshot_date: datetime.date


class CardRead(_ORMModel):
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


class CardWithPrices(CardRead):
    price_history: list[PricePointRead] = []
