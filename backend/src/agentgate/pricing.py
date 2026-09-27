"""Configuration-driven token pricing.

Business logic never embeds a vendor price. If the model is absent from the
table, or the provider did not report tokens, cost is unavailable.
"""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)


class PricingTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: Dict[str, ModelPrice] = Field(default_factory=dict)


def estimate_cost(
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    model: Optional[str],
    pricing: PricingTable,
) -> Optional[float]:
    if input_tokens is None or output_tokens is None or not model:
        return None
    price = pricing.models.get(model)
    if price is None:
        return None
    return (
        input_tokens * price.input_per_million + output_tokens * price.output_per_million
    ) / 1_000_000
