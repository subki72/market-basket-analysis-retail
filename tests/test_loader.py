"""Unit tests for retail CSV loading, transaction cleaning, and cached rule parsing."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.mba_engine.loader import (
    clean_retail_dataframe,
    extract_baskets,
    generate_sample_baskets,
    load_cached_rules,
    load_retail_csv,
    parse_frozenset_cell,
    transactions_to_baskets,
)
from src.mba_engine.schemas import TransactionLine


def test_load_retail_csv_handles_iso_8859_1_fallback(tmp_path: Path) -> None:
    """load_retail_csv should fall back to ISO-8859-1 when UTF-8 decoding fails."""
    # Arrange
    csv_path = tmp_path / "latin1_retail.csv"
    csv_path.write_bytes("order_id,product_name\n101,Café Mug\n".encode("ISO-8859-1"))

    # Act
    df = load_retail_csv(csv_path)

    # Assert
    assert len(df) == 1
    assert df.loc[0, "product_name"] == "Café Mug"


def test_load_retail_csv_missing_or_empty_raises(tmp_path: Path) -> None:
    """Missing or header-only CSV files must fail explicitly."""
    # Arrange
    missing_path = tmp_path / "does_not_exist.csv"
    empty_path = tmp_path / "empty.csv"
    empty_path.write_text("order_id,product_name\n", encoding="utf-8")

    # Act & Assert
    with pytest.raises(FileNotFoundError):
        load_retail_csv(missing_path)
    with pytest.raises(ValueError, match="empty"):
        load_retail_csv(empty_path)


def test_clean_retail_dataframe_filters_invalid_rows_and_standardizes_codes() -> None:
    """Cleaning should drop cancellations, non-positive values, noise tokens, and duplicates."""
    # Arrange
    raw_df = pd.DataFrame(
        [
            {"order_id": "1001", "product_name": " Heart Box ", "product_code": "P1", "quantity": 2, "price": 5.0},
            {"order_id": "1001", "product_name": "heart box", "product_code": "P1", "quantity": 1, "price": 5.0},
            {"order_id": "1002", "product_name": "Heart Box V2", "product_code": "P1", "quantity": 1, "price": 5.0},
            {"order_id": "C1003", "product_name": "Heart Box", "product_code": "P1", "quantity": 1, "price": 5.0},
            {"order_id": "1004", "product_name": "POSTAGE", "product_code": "POST", "quantity": 1, "price": 3.0},
            {"order_id": "1005", "product_name": "Test Item", "product_code": "TST", "quantity": 1, "price": 1.0},
            {"order_id": "1006", "product_name": "Broken Vase", "product_code": "P2", "quantity": -1, "price": 4.0},
        ]
    )

    # Act
    cleaned = clean_retail_dataframe(raw_df)

    # Assert
    assert len(cleaned) == 2
    assert set(cleaned["order_id"]) == {"1001", "1002"}
    assert set(cleaned["product_name"]) == {"heart box"}


def test_clean_retail_dataframe_missing_columns_raises() -> None:
    """Missing required schema columns should raise a descriptive ValueError."""
    # Arrange
    bad_df = pd.DataFrame([{"order_id": "1001", "price": 2.0}])

    # Act & Assert
    with pytest.raises(ValueError, match="Missing required retail columns"):
        clean_retail_dataframe(bad_df)


def test_extract_baskets_groups_and_filters_min_items() -> None:
    """extract_baskets should group unique items per order and apply min_basket_items."""
    # Arrange
    df = pd.DataFrame(
        [
            {"order_id": "O1", "product_name": "Tea Cup"},
            {"order_id": "O1", "product_name": "Saucer"},
            {"order_id": "O2", "product_name": "Solo Item"},
        ]
    )

    # Act
    multi_baskets = extract_baskets(df, min_basket_items=2)

    # Assert
    assert multi_baskets == [["saucer", "tea cup"]]


def test_transactions_to_baskets_skips_cancellations_and_deduplicates() -> None:
    """API transaction grouping should filter cancelled orders and non-product tokens."""
    # Arrange
    lines = [
        TransactionLine(order_id="A1", product_name="Red Mug"),
        TransactionLine(order_id="A1", product_name="red mug"),
        TransactionLine(order_id="A1", product_name="Blue Spoon"),
        TransactionLine(order_id="A1", product_name="POSTAGE"),
        TransactionLine(order_id="C99", product_name="Red Mug"),
    ]

    # Act
    baskets = transactions_to_baskets(lines, min_basket_items=2)

    # Assert
    assert baskets == [["blue spoon", "red mug"]]


def test_generate_sample_baskets_is_deterministic() -> None:
    """Same seed and count must yield identical synthetic retail baskets."""
    # Arrange & Act
    first = generate_sample_baskets(num_baskets=30, seed=7)
    second = generate_sample_baskets(num_baskets=30, seed=7)

    # Assert
    assert len(first) == 30
    assert first == second
    assert all(len(basket) >= 2 for basket in first)


def test_parse_frozenset_cell_parses_real_csv_format() -> None:
    """parse_frozenset_cell should extract sorted product names safely without eval."""
    # Arrange
    raw = "frozenset({'strawberry ceramic trinket box', 'sweetheart ceramic trinket box'})"

    # Act
    items = parse_frozenset_cell(raw)

    # Assert
    assert items == ["strawberry ceramic trinket box", "sweetheart ceramic trinket box"]
    with pytest.raises(ValueError, match="Malformed frozenset"):
        parse_frozenset_cell("not-a-valid-set(")


def test_load_cached_rules_reads_committed_top_rules_csv() -> None:
    """Committed MBA_Results_TopRules.csv should parse into ranked AssociationRuleItem objects."""
    # Arrange
    csv_path = Path("MBA_Results_TopRules.csv")

    # Act
    rules = load_cached_rules(csv_path, max_rules=10)

    # Assert
    assert len(rules) == 10
    assert rules[0].antecedents == ["sweetheart ceramic trinket box"]
    assert rules[0].consequents == ["strawberry ceramic trinket box"]
    assert rules[0].lift > 11.0
    assert 0.7 < rules[0].confidence < 0.8
