"""Fixture world for the customer-support demonstration agent.

This catalog is synthetic. It is not derived from real customers or orders.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    customer_id: str
    status: str
    delivered_days_ago: Optional[int] = None
    amount_usd: float


class Customer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    email: str


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orders: Dict[str, Order]
    customers: Dict[str, Customer]
    description: str = "Synthetic demonstration catalog. Not real customer data."

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def demo_catalog() -> Catalog:
    orders = {
        "1001": Order(id="1001", customer_id="c1", status="delivered", delivered_days_ago=10, amount_usd=49.0),
        "1002": Order(id="1002", customer_id="c2", status="delivered", delivered_days_ago=31, amount_usd=120.0),
        "1003": Order(id="1003", customer_id="c1", status="shipped", delivered_days_ago=None, amount_usd=30.0),
        "1004": Order(id="1004", customer_id="c3", status="delivered", delivered_days_ago=30, amount_usd=15.0),
        "1005": Order(id="1005", customer_id="c4", status="cancelled", delivered_days_ago=None, amount_usd=0.0),
        "1006": Order(id="1006", customer_id="c2", status="delivered", delivered_days_ago=45, amount_usd=80.0),
        "1007": Order(id="1007", customer_id="c5", status="delivered", delivered_days_ago=1, amount_usd=10.0),
        "1008": Order(id="1008", customer_id="c5", status="delivered", delivered_days_ago=29, amount_usd=22.0),
    }
    customers = {
        "c1": Customer(id="c1", name="Avery Chen", email="avery@example.test"),
        "c2": Customer(id="c2", name="Jordan Blake", email="jordan@example.test"),
        "c3": Customer(id="c3", name="Sam Patel", email="sam@example.test"),
        "c4": Customer(id="c4", name="Riley Nguyen", email="riley@example.test"),
        "c5": Customer(id="c5", name="Morgan Diaz", email="morgan@example.test"),
    }
    return Catalog(orders=orders, customers=customers)


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str
    window_days: int
    window_inclusive: bool


def evaluate_return_policy(
    order: Order,
    window_days: int,
    window_inclusive: bool,
) -> PolicyDecision:
    if order.status != "delivered" or order.delivered_days_ago is None:
        return PolicyDecision(
            allowed=False,
            reason="not_delivered",
            window_days=window_days,
            window_inclusive=window_inclusive,
        )
    days = order.delivered_days_ago
    allowed = days <= window_days if window_inclusive else days < window_days
    return PolicyDecision(
        allowed=allowed,
        reason="within_window" if allowed else "outside_window",
        window_days=window_days,
        window_inclusive=window_inclusive,
    )


def canonical_hash(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
