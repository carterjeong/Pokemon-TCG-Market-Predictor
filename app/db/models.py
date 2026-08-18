"""SQLAlchemy 2.0 ORM models: Set, Card, PriceHistory.

Owner: Carter (SWE).

Design notes
------------
* `Set.id` and `Card.id` use the natural string IDs from pokemontcg.io
  (e.g. set "sv1", card "sv1-25") so ingestion is a natural upsert.
* `PriceHistory` is append-only: one row per (card, source, variant, day).
  The ML model trains on this table, so it is indexed for time-range scans.
* Monetary values use Numeric(12, 4) — never floats.
* Naming convention is fixed so Alembic autogenerate emits stable
  constraint names.
"""

import datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Set(TimestampMixin, Base):
    """A Pokemon TCG expansion set (pokemontcg.io `/sets`)."""

    __tablename__ = "sets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. "sv1"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    series: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    printed_total: Mapped[int | None]
    total: Mapped[int | None]
    ptcgo_code: Mapped[str | None] = mapped_column(String(16))
    release_date: Mapped[datetime.date | None] = mapped_column(Date, index=True)
    symbol_url: Mapped[str | None] = mapped_column(String(512))
    logo_url: Mapped[str | None] = mapped_column(String(512))

    cards: Mapped[list["Card"]] = relationship(
        back_populates="set", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Set id={self.id!r} name={self.name!r}>"


class Card(TimestampMixin, Base):
    """A single card printing (pokemontcg.io `/cards`)."""

    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. "sv1-25"
    set_id: Mapped[str] = mapped_column(
        ForeignKey("sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    supertype: Mapped[str | None] = mapped_column(String(32))  # Pokemon/Trainer/Energy
    subtypes: Mapped[list[str] | None] = mapped_column(JSONB)
    rarity: Mapped[str | None] = mapped_column(String(64), index=True)
    number: Mapped[str | None] = mapped_column(String(32))  # "25", "TG12", …
    artist: Mapped[str | None] = mapped_column(String(255))
    national_pokedex_numbers: Mapped[list[int] | None] = mapped_column(JSONB)
    image_small_url: Mapped[str | None] = mapped_column(String(512))
    image_large_url: Mapped[str | None] = mapped_column(String(512))
    tcgplayer_url: Mapped[str | None] = mapped_column(String(512))

    set: Mapped[Set] = relationship(back_populates="cards")
    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="card", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Card id={self.id!r} name={self.name!r}>"


class PriceHistory(TimestampMixin, Base):
    """Append-only daily price snapshot per card/source/variant.

    ML training data: the ingestion pipeline writes one row per card,
    price source (tcgplayer/cardmarket), finish variant, and snapshot day.
    """

    __tablename__ = "price_history"
    __table_args__ = (
        UniqueConstraint(
            "card_id",
            "source",
            "variant",
            "snapshot_date",
            name="uq_price_snapshot",
        ),
        Index("ix_price_history_card_date", "card_id", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    card_id: Mapped[str] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # "tcgplayer"
    variant: Mapped[str] = mapped_column(
        String(32), nullable=False, default="normal"
    )  # normal / holofoil / reverseHolofoil / 1stEdition…
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    price_low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    price_mid: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    price_high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    price_market: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))

    snapshot_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)

    card: Mapped[Card] = relationship(back_populates="price_history")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PriceHistory card={self.card_id!r} {self.source}/{self.variant} "
            f"{self.snapshot_date} market={self.price_market}>"
        )
