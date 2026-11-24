"""Apriori frequent itemset mining, association rule scoring, and scatter visualization."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
import logging
import math
from pathlib import Path

from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder
import pandas as pd

from src.mba_engine.loader import EXCLUDED_EXACT_PRODUCTS
from src.mba_engine.schemas import AssociationRuleItem, RecommendationItem

logger = logging.getLogger(__name__)


def _normalize_baskets(baskets: Sequence[Sequence[str]], max_items: int) -> list[list[str]]:
    """Strip, deduplicate, and cap unique items across baskets to bound memory."""
    cleaned_baskets: list[list[str]] = []
    item_counts: Counter[str] = Counter()

    for basket in baskets:
        unique_items = sorted(
            {item.lower().strip() for item in basket if item and item.lower().strip() not in EXCLUDED_EXACT_PRODUCTS}
        )
        if not unique_items:
            continue
        cleaned_baskets.append(unique_items)
        item_counts.update(unique_items)

    if len(item_counts) <= max_items:
        return cleaned_baskets

    allowed = {item for item, _ in item_counts.most_common(max_items)}
    logger.warning(
        "Basket vocabulary (%d items) exceeded max_items=%d; keeping top frequent items.",
        len(item_counts),
        max_items,
    )
    return [[item for item in basket if item in allowed] for basket in cleaned_baskets]


def encode_baskets(baskets: Sequence[Sequence[str]], max_items: int = 500) -> pd.DataFrame:
    """Encode a collection of retail baskets into a boolean TransactionEncoder matrix.

    Args:
        baskets: Sequence of item sequences per order.
        max_items: Maximum unique products retained before frequency pruning.

    Returns:
        Boolean DataFrame with one column per distinct item.

    Raises:
        ValueError: If no non-empty baskets remain or ``max_items`` is invalid.
    """
    if max_items < 2:
        raise ValueError("max_items must be at least 2.")

    normalized = _normalize_baskets(baskets, max_items=max_items)
    if not normalized:
        raise ValueError("No valid non-empty baskets provided for encoding.")

    encoder = TransactionEncoder()
    encoded_array = encoder.fit(normalized).transform(normalized)
    basket_df = pd.DataFrame(encoded_array, columns=encoder.columns_)
    logger.info("Encoded %d baskets across %d unique products", len(basket_df), basket_df.shape[1])
    return basket_df


def _safe_optional_float(value: object) -> float | None:
    """Return a finite rounded float or None when NaN/Inf."""
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return round(numeric, 6)


def _validate_mining_thresholds(
    min_support: float,
    min_confidence: float,
    min_lift: float,
    max_len: int,
    top_n: int | None,
) -> None:
    """Validate Apriori and rule extraction hyperparameters upfront."""
    if not 0.0 < min_support <= 1.0:
        raise ValueError("min_support must be in (0.0, 1.0].")
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be in [0.0, 1.0].")
    if min_lift < 0.0:
        raise ValueError("min_lift must be non-negative.")
    if max_len < 2:
        raise ValueError("max_len must be at least 2 to form association rules.")
    if top_n is not None and top_n < 1:
        raise ValueError("top_n must be at least 1 when provided.")


def _rows_to_rule_items(rules_df: pd.DataFrame, top_n: int | None) -> list[AssociationRuleItem]:
    """Convert sorted association_rules DataFrame rows into typed Pydantic models."""
    sliced_df = rules_df if top_n is None else rules_df.head(top_n)
    results: list[AssociationRuleItem] = []
    for row in sliced_df.to_dict(orient="records"):
        results.append(
            AssociationRuleItem(
                antecedents=sorted(str(item) for item in row["antecedents"]),
                consequents=sorted(str(item) for item in row["consequents"]),
                antecedent_support=round(float(row["antecedent support"]), 6),
                consequent_support=round(float(row["consequent support"]), 6),
                support=round(float(row["support"]), 6),
                confidence=round(float(row["confidence"]), 6),
                lift=round(float(row["lift"]), 6),
                leverage=_safe_optional_float(row.get("leverage")),
                conviction=_safe_optional_float(row.get("conviction")),
            )
        )
    return results


def _execute_apriori_pipeline(
    basket_df: pd.DataFrame,
    min_support: float,
    min_confidence: float,
    min_lift: float,
    max_len: int,
    top_n: int | None,
) -> list[AssociationRuleItem]:
    """Run Apriori itemset discovery and association rule extraction."""
    frequent_itemsets = apriori(
        basket_df,
        min_support=min_support,
        use_colnames=True,
        max_len=max_len,
    )
    if frequent_itemsets.empty or frequent_itemsets["itemsets"].map(len).max() < 2:
        logger.warning("No multi-item frequent itemsets met min_support=%.4f.", min_support)
        return []

    # mlxtend 0.23.3 requires num_itemsets explicitly, which also matches 0.25.0+ signatures.
    rules_df = association_rules(
        frequent_itemsets,
        num_itemsets=len(basket_df),
        metric="lift",
        min_threshold=min_lift,
    )
    if rules_df.empty:
        return []

    filtered = rules_df[rules_df["confidence"] >= min_confidence]
    if filtered.empty:
        return []

    ranked = filtered.sort_values(["confidence", "lift", "support"], ascending=[False, False, False])
    rule_items = _rows_to_rule_items(ranked, top_n=top_n)
    logger.info("Mined %d association rules (returned %d)", len(ranked), len(rule_items))
    return rule_items


def mine_association_rules(
    baskets: Sequence[Sequence[str]],
    min_support: float = 0.02,
    min_confidence: float = 0.30,
    min_lift: float = 1.0,
    max_len: int = 3,
    max_items: int = 500,
    top_n: int | None = 50,
) -> list[AssociationRuleItem]:
    """Run Apriori and association rule mining with sparse-basket guards.

    Args:
        baskets: Input retail baskets.
        min_support: Minimum support threshold in ``(0, 1]``.
        min_confidence: Minimum rule confidence threshold in ``[0, 1]``.
        min_lift: Minimum rule lift threshold.
        max_len: Maximum itemset length evaluated by Apriori.
        max_items: Maximum unique items retained in the matrix.
        top_n: Maximum ranked rules to return.

    Returns:
        Ranked list of ``AssociationRuleItem`` records, or ``[]`` on sparse data.
    """
    _validate_mining_thresholds(min_support, min_confidence, min_lift, max_len, top_n)
    if not baskets:
        logger.warning("Received empty baskets list; returning zero association rules.")
        return []

    normalized = _normalize_baskets(baskets, max_items=max_items)
    if not normalized:
        logger.warning("All provided baskets were empty after cleaning; returning [].")
        return []

    basket_df = encode_baskets(normalized, max_items=max_items)
    if basket_df.shape[1] < 2:
        logger.warning("Fewer than 2 distinct items found; cannot form association rules.")
        return []

    return _execute_apriori_pipeline(
        basket_df=basket_df,
        min_support=min_support,
        min_confidence=min_confidence,
        min_lift=min_lift,
        max_len=max_len,
        top_n=top_n,
    )


def _collect_rule_candidates(
    rule: AssociationRuleItem,
    normalized_basket: set[str],
    best_by_candidate: dict[str, RecommendationItem],
) -> None:
    """Update best candidate cross-sell items from one matching rule."""
    antecedents = {item.lower().strip() for item in rule.antecedents}
    if not antecedents or not antecedents.issubset(normalized_basket):
        return

    score = round(rule.lift * rule.confidence, 6)
    for candidate in rule.consequents:
        normalized_candidate = candidate.lower().strip()
        if normalized_candidate in normalized_basket:
            continue
        existing = best_by_candidate.get(normalized_candidate)
        if existing is None or (rule.lift, rule.confidence) > (existing.lift, existing.confidence):
            best_by_candidate[normalized_candidate] = RecommendationItem(
                item=normalized_candidate,
                score=score,
                confidence=rule.confidence,
                lift=rule.lift,
                support=rule.support,
                matched_antecedents=sorted(antecedents),
            )


def recommend_for_items(
    basket_items: Sequence[str],
    rules: Sequence[AssociationRuleItem],
    top_k: int = 5,
) -> list[RecommendationItem]:
    """Recommend cross-sell items for a given basket ordered by lift and confidence."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    normalized_basket = {item.lower().strip() for item in basket_items if item.strip()}
    if not normalized_basket or not rules:
        return []

    best_by_candidate: dict[str, RecommendationItem] = {}
    for rule in rules:
        _collect_rule_candidates(rule, normalized_basket, best_by_candidate)

    ranked = sorted(
        best_by_candidate.values(),
        key=lambda rec: (rec.lift, rec.confidence, rec.support),
        reverse=True,
    )
    return ranked[:top_k]


def save_rules_scatter_plot(
    rules: Sequence[AssociationRuleItem],
    output_path: str | Path,
) -> Path:
    """Render a headless Support vs Confidence scatter plot colored by Lift."""
    if not rules:
        raise ValueError("Cannot render scatter plot for an empty rules collection.")

    # Configure headless backend lazily so API imports stay fast and display-free.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    plot_df = pd.DataFrame([{"support": r.support, "confidence": r.confidence, "lift": r.lift} for r in rules])

    fig, ax = plt.subplots(figsize=(10, 6))
    try:
        sns.scatterplot(
            data=plot_df,
            x="support",
            y="confidence",
            hue="lift",
            size="lift",
            sizes=(50, 350),
            palette="viridis",
            ax=ax,
        )
        ax.set_title("Market Basket Analysis: Support vs Confidence (Colored by Lift)")
        ax.set_xlabel("Support")
        ax.set_ylabel("Confidence")
        ax.grid(True, linestyle="--", alpha=0.4)
        fig.tight_layout()
        fig.savefig(target, dpi=150)
    finally:
        plt.close(fig)

    logger.info("Saved association rules scatter plot to '%s'", target)
    return target
