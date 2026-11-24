"""Modular Market Basket Analysis (Apriori) package."""

from __future__ import annotations

from src.mba_engine.config import MBAConfig, configure_logging
from src.mba_engine.loader import (
    clean_retail_dataframe,
    extract_baskets,
    generate_sample_baskets,
    load_cached_rules,
    load_retail_csv,
    transactions_to_baskets,
)
from src.mba_engine.miner import (
    encode_baskets,
    mine_association_rules,
    recommend_for_items,
    save_rules_scatter_plot,
)
from src.mba_engine.schemas import (
    AssociationRuleItem,
    BasketAnalysisRequest,
    BasketAnalysisResponse,
    HealthResponse,
    RecommendationItem,
    TransactionLine,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "AssociationRuleItem",
    "BasketAnalysisRequest",
    "BasketAnalysisResponse",
    "HealthResponse",
    "MBAConfig",
    "RecommendationItem",
    "TransactionLine",
    "clean_retail_dataframe",
    "configure_logging",
    "encode_baskets",
    "extract_baskets",
    "generate_sample_baskets",
    "load_cached_rules",
    "load_retail_csv",
    "mine_association_rules",
    "recommend_for_items",
    "save_rules_scatter_plot",
    "transactions_to_baskets",
]
