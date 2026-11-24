"""Pydantic v2 request and response schemas for Market Basket Analysis API and CLI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_TRANSACTION_LINES = 10_000
MAX_BASKETS_PER_REQUEST = 5_000


class TransactionLine(BaseModel):
    """Single retail order line item before basket grouping."""

    model_config = ConfigDict(str_strip_whitespace=True)

    order_id: str = Field(..., min_length=1, max_length=64)
    product_name: str = Field(..., min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1)
    price: float = Field(default=1.0, gt=0.0)
    customer_id: str | None = Field(default=None, max_length=64)
    product_code: str | None = Field(default=None, max_length=64)


class BasketAnalysisRequest(BaseModel):
    """Input payload for association rule mining and cross-sell recommendations."""

    model_config = ConfigDict(str_strip_whitespace=True)

    transactions: list[TransactionLine] | None = Field(default=None, max_length=MAX_TRANSACTION_LINES)
    baskets: list[list[str]] | None = Field(default=None, max_length=MAX_BASKETS_PER_REQUEST)
    min_support: float = Field(default=0.02, gt=0.0, le=1.0)
    min_confidence: float = Field(default=0.30, ge=0.0, le=1.0)
    min_lift: float = Field(default=1.0, ge=0.0)
    max_len: int = Field(default=3, ge=2, le=10)
    top_n: int = Field(default=20, ge=1, le=200)
    recommend_for: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_basket_source(self) -> BasketAnalysisRequest:
        """Ensure at least one non-empty transaction or basket collection is supplied."""
        has_transactions = bool(self.transactions)
        has_baskets = bool(self.baskets and any(item.strip() for basket in self.baskets for item in basket))
        if not has_transactions and not has_baskets:
            raise ValueError("Provide a non-empty 'transactions' or 'baskets' payload.")
        return self


class AssociationRuleItem(BaseModel):
    """Single association rule produced by Apriori mining."""

    antecedents: list[str]
    consequents: list[str]
    antecedent_support: float
    consequent_support: float
    support: float
    confidence: float
    lift: float
    leverage: float | None = None
    conviction: float | None = None


class RecommendationItem(BaseModel):
    """Ranked cross-sell recommendation derived from matching association rules."""

    item: str
    score: float
    confidence: float
    lift: float
    support: float
    matched_antecedents: list[str]


class BasketAnalysisResponse(BaseModel):
    """Structured response containing ranked association rules and summary metrics."""

    total_baskets: int
    unique_items: int
    rules_count: int
    rules: list[AssociationRuleItem]
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    top_lift: float | None = None
    top_confidence: float | None = None


class HealthResponse(BaseModel):
    """Liveness and cached rules readiness response."""

    status: Literal["ok"] = "ok"
    service: str = "market-basket-analysis-retail"
    version: str
    cached_rules_available: bool
    cached_rules_count: int
