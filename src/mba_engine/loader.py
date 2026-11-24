"""Retail transaction loading, cleaning, basket transformation, and cached rule parsing."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Sequence
from functools import lru_cache
import logging
from pathlib import Path
import random
import re

import pandas as pd

from src.mba_engine.schemas import AssociationRuleItem, TransactionLine

logger = logging.getLogger(__name__)

REQUIRED_RETAIL_COLUMNS: frozenset[str] = frozenset({"order_id", "product_name"})
EXCLUDED_EXACT_PRODUCTS: frozenset[str] = frozenset({"postage", "manual", "discount", "carriage"})
TEST_TOKEN_PATTERN: re.Pattern[str] = re.compile(r"\btest\b")

SAMPLE_PRODUCT_CLUSTERS: tuple[tuple[str, ...], ...] = (
    ("sweetheart ceramic trinket box", "strawberry ceramic trinket box", "ceramic heart plate"),
    ("red hanging heart t-light holder", "white hanging heart t-light holder", "glass tealight cup"),
    ("wooden picture frame white finish", "wooden frame antique white", "vintage photo hook"),
    ("jumbo bag strawberry", "jumbo bag red retrospot", "jumbo bag pink with white spots"),
    ("heart of wicker small", "heart of wicker large", "linen ribbon roll"),
    ("lunch bag woodland", "lunch bag red spotty", "lunch bag spaceboy design"),
    ("pack of 60 pink paisley cake cases", "pack of 72 retro spot cake cases", "60 teatime fairy cake cases"),
    ("love building block word", "home building block word", "wooden star ornament"),
)


def load_retail_csv(file_path: str | Path) -> pd.DataFrame:
    """Load a retail transaction CSV with UTF-8/ISO-8859-1 fallback and empty guards.

    Args:
        file_path: Filesystem path to the CSV file.

    Returns:
        Raw DataFrame loaded from the CSV file.

    Raises:
        FileNotFoundError: If ``file_path`` does not exist.
        ValueError: If the CSV file is empty or cannot be decoded cleanly.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Retail CSV file not found: {path}")

    for encoding in ("utf-8", "ISO-8859-1"):
        try:
            df = pd.read_csv(path, encoding=encoding)
            if df.empty:
                raise ValueError(f"Retail CSV file is empty: {path}")
            logger.info("Loaded retail CSV '%s' (%d rows, encoding=%s)", path.name, len(df), encoding)
            return df
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Unable to decode retail CSV '{path}' with UTF-8 or ISO-8859-1.")


def _is_valid_product(name: str) -> bool:
    """Return True when a normalized product name is a real retail item."""
    if not name or name in EXCLUDED_EXACT_PRODUCTS:
        return False
    return TEST_TOKEN_PATTERN.search(name) is None


def _apply_product_code_mapping(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize product_name by mapping each product_code to its modal name."""
    if "product_code" not in df.columns or df.empty:
        return df

    valid_codes = df.dropna(subset=["product_code"])
    if valid_codes.empty:
        return df

    mode_series = valid_codes.groupby("product_code")["product_name"].agg(
        lambda col: col.mode().iloc[0] if not col.mode().empty else col.iloc[0]
    )
    mapped = df["product_code"].map(mode_series)
    result = df.copy()
    result["product_name"] = mapped.where(mapped.notna(), result["product_name"])
    return result


def clean_retail_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and normalize raw retail transactions for market basket analysis.

    Args:
        df: Raw retail DataFrame containing at least ``order_id`` and ``product_name``.

    Returns:
        Cleaned, deduplicated DataFrame ready for basket grouping.

    Raises:
        ValueError: If required columns are missing or input DataFrame is empty.
    """
    if df.empty:
        raise ValueError("Input retail DataFrame cannot be empty.")

    missing = REQUIRED_RETAIL_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required retail columns: {sorted(missing)}")

    cleaned = df.dropna(subset=["order_id", "product_name"]).copy()
    cleaned["order_id"] = cleaned["order_id"].astype(str).str.strip()
    cleaned["product_name"] = cleaned["product_name"].astype(str).str.lower().str.strip()

    # Retail invoices starting with 'C' represent credit cancellations, not purchases.
    cleaned = cleaned[~cleaned["order_id"].str.upper().str.startswith("C")]
    cleaned = cleaned[cleaned["product_name"].map(_is_valid_product)]

    if "quantity" in cleaned.columns:
        cleaned = cleaned[pd.to_numeric(cleaned["quantity"], errors="coerce").fillna(0) > 0]
    if "price" in cleaned.columns:
        cleaned = cleaned[pd.to_numeric(cleaned["price"], errors="coerce").fillna(0) > 0]

    cleaned = _apply_product_code_mapping(cleaned)
    cleaned = cleaned.drop_duplicates(subset=["order_id", "product_name"]).reset_index(drop=True)
    logger.info("Cleaned retail dataset: %d unique order-item rows", len(cleaned))
    return cleaned


def extract_baskets(df: pd.DataFrame, min_basket_items: int = 1) -> list[list[str]]:
    """Group cleaned order lines into sorted, deduplicated item baskets.

    Args:
        df: Raw or pre-cleaned retail DataFrame.
        min_basket_items: Minimum distinct items required to keep a basket.

    Returns:
        List of item baskets grouped by ``order_id``.
    """
    if min_basket_items < 1:
        raise ValueError("min_basket_items must be at least 1.")

    cleaned = clean_retail_dataframe(df)
    if cleaned.empty:
        return []

    grouped = cleaned.groupby("order_id", sort=True)["product_name"].apply(lambda items: sorted(set(items.tolist())))
    baskets = [items for items in grouped.tolist() if len(items) >= min_basket_items]
    logger.info("Extracted %d baskets (min_basket_items=%d)", len(baskets), min_basket_items)
    return baskets


def transactions_to_baskets(
    transactions: Sequence[TransactionLine],
    min_basket_items: int = 1,
) -> list[list[str]]:
    """Normalize validated API TransactionLine objects into item baskets."""
    if min_basket_items < 1:
        raise ValueError("min_basket_items must be at least 1.")
    if not transactions:
        return []

    grouped: dict[str, set[str]] = defaultdict(set)
    for line in transactions:
        order_id = line.order_id.strip()
        if order_id.upper().startswith("C"):
            continue
        product = line.product_name.lower().strip()
        if _is_valid_product(product):
            grouped[order_id].add(product)

    return [sorted(items) for items in grouped.values() if len(items) >= min_basket_items]


def generate_sample_baskets(num_baskets: int = 120, seed: int = 42) -> list[list[str]]:
    """Generate deterministic offline retail baskets mirroring real co-purchase clusters.

    Args:
        num_baskets: Number of synthetic retail baskets to create.
        seed: Random seed for reproducible outputs.

    Returns:
        List of deterministic retail product baskets.
    """
    if num_baskets < 1:
        raise ValueError("num_baskets must be at least 1.")

    rng = random.Random(seed)
    baskets: list[list[str]] = []
    for index in range(num_baskets):
        primary = SAMPLE_PRODUCT_CLUSTERS[index % len(SAMPLE_PRODUCT_CLUSTERS)]
        basket_items = {primary[0], primary[1]}
        if rng.random() < 0.45:
            basket_items.add(primary[2])
        if rng.random() < 0.25:
            secondary = SAMPLE_PRODUCT_CLUSTERS[(index + 3) % len(SAMPLE_PRODUCT_CLUSTERS)]
            basket_items.add(secondary[0])
        baskets.append(sorted(basket_items))

    logger.info("Generated %d deterministic sample baskets (seed=%d)", len(baskets), seed)
    return baskets


def parse_frozenset_cell(raw_value: str) -> list[str]:
    """Safely parse a stringified frozenset cell into a sorted list of item names."""
    text = str(raw_value).strip()
    if text.startswith("frozenset(") and text.endswith(")"):
        inner = text[len("frozenset(") : -1].strip()
    else:
        inner = text

    try:
        parsed = ast.literal_eval(inner)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"Malformed frozenset cell value: {raw_value!r}") from exc

    if isinstance(parsed, (set, frozenset, list, tuple)):
        return sorted(str(item).strip() for item in parsed if str(item).strip())
    raise ValueError(f"Unexpected parsed type for frozenset cell: {type(parsed).__name__}")


def _safe_float_or_none(value: object) -> float | None:
    """Convert numeric CSV cells to finite floats or None when inf/NaN."""
    num = pd.to_numeric(value, errors="coerce")
    if pd.isna(num) or not float("-inf") < float(num) < float("inf"):
        return None
    return round(float(num), 6)


@lru_cache(maxsize=8)
def _load_cached_rules_memo(
    resolved_path: str,
    mtime_ns: int,
    max_rules: int,
) -> tuple[AssociationRuleItem, ...]:
    """Read and parse association rules CSV with mtime-based cache invalidation."""
    del mtime_ns  # Keyed in cache signature so file updates invalidate stale entries.
    df = pd.read_csv(resolved_path, encoding="utf-8")
    required_cols = {
        "antecedents",
        "consequents",
        "antecedent support",
        "consequent support",
        "support",
        "confidence",
        "lift",
    }
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Rules CSV missing columns: {sorted(missing)}")

    items: list[AssociationRuleItem] = []
    for row in df.head(max_rules).to_dict(orient="records"):
        items.append(
            AssociationRuleItem(
                antecedents=parse_frozenset_cell(str(row["antecedents"])),
                consequents=parse_frozenset_cell(str(row["consequents"])),
                antecedent_support=round(float(row["antecedent support"]), 6),
                consequent_support=round(float(row["consequent support"]), 6),
                support=round(float(row["support"]), 6),
                confidence=round(float(row["confidence"]), 6),
                lift=round(float(row["lift"]), 6),
                leverage=_safe_float_or_none(row.get("leverage")),
                conviction=_safe_float_or_none(row.get("conviction")),
            )
        )
    return tuple(items)


def load_cached_rules(
    csv_path: str | Path,
    max_rules: int = 200,
) -> list[AssociationRuleItem]:
    """Load precomputed association rules from CSV using a bounded mtime-aware cache."""
    if max_rules < 1:
        raise ValueError("max_rules must be at least 1.")
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Cached rules CSV not found: {path}")

    resolved = path.resolve()
    mtime_ns = resolved.stat().st_mtime_ns
    cached = _load_cached_rules_memo(str(resolved), mtime_ns, max_rules)
    logger.info("Loaded %d cached rules from '%s'", len(cached), path.name)
    return list(cached)
