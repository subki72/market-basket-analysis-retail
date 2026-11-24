"""Unit tests for TransactionEncoder encoding, Apriori mining, and cross-sell ranking."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.mba_engine.loader import generate_sample_baskets
from src.mba_engine.miner import (
    encode_baskets,
    mine_association_rules,
    recommend_for_items,
    save_rules_scatter_plot,
)
from src.mba_engine.schemas import AssociationRuleItem


def test_encode_baskets_produces_boolean_matrix() -> None:
    """encode_baskets should return a deduplicated boolean matrix without postage."""
    # Arrange
    baskets = [["Mug", "Plate", "postage"], ["Mug", "Spoon"]]

    # Act
    matrix = encode_baskets(baskets)

    # Assert
    assert list(matrix.columns) == ["mug", "plate", "spoon"]
    assert matrix.shape == (2, 3)
    assert bool(matrix.loc[0, "mug"]) is True
    assert bool(matrix.loc[1, "plate"]) is False


def test_encode_baskets_caps_max_items_and_rejects_empty() -> None:
    """encode_baskets should respect max_items cap and reject empty inputs."""
    # Arrange
    baskets = [["a", "b", "c"], ["a", "b"], ["a", "d"]]

    # Act
    matrix = encode_baskets(baskets, max_items=2)

    # Assert
    assert matrix.shape[1] == 2
    assert set(matrix.columns) == {"a", "b"}
    with pytest.raises(ValueError, match="No valid non-empty baskets"):
        encode_baskets([[], ["postage"]])


def test_mine_association_rules_ranks_by_confidence_and_lift() -> None:
    """Apriori mining on deterministic baskets should discover high-lift co-purchases."""
    # Arrange
    baskets = generate_sample_baskets(num_baskets=120, seed=42)

    # Act
    rules = mine_association_rules(
        baskets,
        min_support=0.05,
        min_confidence=0.50,
        min_lift=2.0,
        max_len=3,
        top_n=15,
    )

    # Assert
    assert len(rules) > 0
    assert len(rules) <= 15
    assert all(rule.support >= 0.05 for rule in rules)
    assert all(rule.confidence >= 0.50 for rule in rules)
    assert all(rule.lift >= 2.0 for rule in rules)
    assert rules[0].confidence >= rules[-1].confidence


def test_mine_association_rules_handles_empty_or_sparse_baskets_cleanly() -> None:
    """Sparse or empty datasets should return [] cleanly rather than raising exceptions."""
    # Arrange
    sparse_baskets = [["item_a"], ["item_b"], ["item_c", "item_d"]]

    # Act
    empty_rules = mine_association_rules([])
    single_item_rules = mine_association_rules([["solo"], ["solo"]])
    high_threshold_rules = mine_association_rules(sparse_baskets, min_support=0.95)

    # Assert
    assert empty_rules == []
    assert single_item_rules == []
    assert high_threshold_rules == []


def test_mine_association_rules_sanitizes_infinite_conviction() -> None:
    """Perfect confidence rules produce inf conviction in mlxtend and must map to None."""
    # Arrange
    baskets = [["alpha", "beta"], ["alpha", "beta"], ["alpha", "beta"], ["gamma", "delta"]]

    # Act
    rules = mine_association_rules(baskets, min_support=0.5, min_confidence=0.9, min_lift=1.0)

    # Assert
    assert len(rules) >= 1
    assert all(rule.conviction is None for rule in rules if rule.confidence == 1.0)


def test_recommend_for_items_ranks_cross_sell_candidates_excluding_cart_items() -> None:
    """Recommendations should exclude existing cart items and sort by lift then confidence."""
    # Arrange
    rules = [
        AssociationRuleItem(
            antecedents=["tea cup"],
            consequents=["saucer"],
            antecedent_support=0.4,
            consequent_support=0.4,
            support=0.3,
            confidence=0.75,
            lift=2.5,
        ),
        AssociationRuleItem(
            antecedents=["tea cup"],
            consequents=["sugar bowl"],
            antecedent_support=0.4,
            consequent_support=0.5,
            support=0.35,
            confidence=0.88,
            lift=3.2,
        ),
        AssociationRuleItem(
            antecedents=["plate"],
            consequents=["fork"],
            antecedent_support=0.3,
            consequent_support=0.3,
            support=0.2,
            confidence=0.67,
            lift=2.1,
        ),
    ]

    # Act
    recs = recommend_for_items(["Tea Cup"], rules, top_k=3)

    # Assert
    assert [rec.item for rec in recs] == ["sugar bowl", "saucer"]
    assert recs[0].matched_antecedents == ["tea cup"]


def test_save_rules_scatter_plot_writes_png_headless(tmp_path: Path) -> None:
    """Headless Matplotlib scatter exporter should save a non-empty PNG artifact."""
    # Arrange
    baskets = generate_sample_baskets(num_baskets=80, seed=11)
    rules = mine_association_rules(baskets, min_support=0.05, min_confidence=0.4, min_lift=1.5)
    output_file = tmp_path / "charts" / "mba_scatter.png"

    # Act
    saved = save_rules_scatter_plot(rules, output_file)

    # Assert
    assert saved.is_file()
    assert saved.stat().st_size > 1000
    with pytest.raises(ValueError, match="empty rules"):
        save_rules_scatter_plot([], tmp_path / "empty.png")
