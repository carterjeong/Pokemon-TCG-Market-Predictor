"""Cards & price-history REST endpoints.

Owner: Carter (SWE) — feature/api-routes.

Mounted under ``settings.api_v1_prefix`` (/api/v1) in app/main.py:

    GET /api/v1/cards                 — paginated list (filters: set_id, rarity)
    GET /api/v1/cards/{card_id}       — single card (404 if unknown)
    GET /api/v1/cards/{card_id}/prices — time series, snapshot_date ASC

All queries are strict SQLAlchemy 2.0 (``select()``/``where()``) through
the shared async session dependency. Responses expose only column
attributes, so no relationship lazy-loads (and no N+1) can trigger.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.db.models import Card, PriceHistory
from app.db.session import SessionDep
from app.schemas.card import (
    CardResponse,
    PaginatedCardResponse,
    PriceHistoryResponse,
)

router = APIRouter(prefix="/cards", tags=["Cards"])

PageParam = Annotated[int, Query(ge=1, description="1-based page number")]
SizeParam = Annotated[int, Query(ge=1, le=100, description="Rows per page (max 100)")]


@router.get("", response_model=PaginatedCardResponse)
async def list_cards(
    session: SessionDep,
    page: PageParam = 1,
    size: SizeParam = 50,
    set_id: Annotated[str | None, Query(description="Filter by set, e.g. sv1")] = None,
    rarity: Annotated[str | None, Query(description="Filter by exact rarity")] = None,
) -> PaginatedCardResponse:
    """Paginated card listing with optional set/rarity filters."""
    filters = []
    if set_id is not None:
        filters.append(Card.set_id == set_id)
    if rarity is not None:
        filters.append(Card.rarity == rarity)

    total = (
        await session.execute(select(func.count()).select_from(Card).where(*filters))
    ).scalar_one()

    cards = (
        (
            await session.execute(
                select(Card)
                .where(*filters)
                .order_by(Card.set_id, Card.id)
                .offset((page - 1) * size)
                .limit(size)
            )
        )
        .scalars()
        .all()
    )

    return PaginatedCardResponse(
        items=[CardResponse.model_validate(c) for c in cards],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{card_id}", response_model=CardResponse)
async def get_card(card_id: str, session: SessionDep) -> CardResponse:
    """Single card by its natural string ID (e.g. ``sv1-25``)."""
    card = await session.get(Card, card_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Card {card_id!r} not found",
        )
    return CardResponse.model_validate(card)


@router.get("/{card_id}/prices", response_model=list[PriceHistoryResponse])
async def get_card_prices(
    card_id: str,
    session: SessionDep,
    variant: Annotated[
        str | None,
        Query(description="Filter by finish variant, e.g. holofoil / normal"),
    ] = None,
) -> list[PriceHistoryResponse]:
    """Chronological price history for one card (chart-ready, ASC)."""
    exists = (
        await session.execute(select(Card.id).where(Card.id == card_id))
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Card {card_id!r} not found",
        )

    filters = [PriceHistory.card_id == card_id]
    if variant is not None:
        filters.append(PriceHistory.variant == variant)

    rows = (
        (
            await session.execute(
                select(PriceHistory)
                .where(*filters)
                .order_by(
                    PriceHistory.snapshot_date.asc(),
                    PriceHistory.variant.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return [PriceHistoryResponse.model_validate(r) for r in rows]
