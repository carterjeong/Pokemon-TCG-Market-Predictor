"""Price-prediction model interface — scaffold.

Owner: Carter (SWE). Starting point for feature/ml-integration.

Keep the interface stable so API routes can depend on `PricePredictor`
while the underlying model evolves (baseline moving average → gradient
boosting → whatever wins). Model artifacts should be loaded once at
startup, never per-request.

TODO(carter):
  * feature engineering from price_history (lags, rolling stats, rarity)
  * training entrypoint + artifact persistence (e.g. S3)
  * add `predict.router` exposing POST /api/v1/predict/{card_id}
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PricePrediction:
    card_id: str
    variant: str
    horizon_days: int
    predicted_market: Decimal
    as_of: datetime.date


class PricePredictor(Protocol):
    """Interface the API layer codes against."""

    def predict(
        self, card_id: str, variant: str = "normal", horizon_days: int = 30
    ) -> PricePrediction: ...


class NaiveLastPricePredictor:
    """Baseline: predicts the last observed market price (walk-forward).

    Replace with a real model; useful as an evaluation floor.
    """

    def predict(
        self, card_id: str, variant: str = "normal", horizon_days: int = 30
    ) -> PricePrediction:
        raise NotImplementedError("Wire to price_history in feature/ml-integration")
