"""CLI entrypoint for offline Market Basket Analysis and health diagnostics."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import logging
from pathlib import Path
import sys

import pandas as pd

from src.mba_engine.config import MBAConfig, configure_logging
from src.mba_engine.loader import (
    extract_baskets,
    generate_sample_baskets,
    load_cached_rules,
    load_retail_csv,
)
from src.mba_engine.miner import (
    mine_association_rules,
    recommend_for_items,
    save_rules_scatter_plot,
)
from src.mba_engine.schemas import AssociationRuleItem

logger = logging.getLogger("mba_engine.cli")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the Market Basket Analysis CLI."""
    parser = argparse.ArgumentParser(description="Run Market Basket Analysis (Apriori) or inspect cached retail rules.")
    parser.add_argument("--input", type=str, default=None, help="Path to raw retail CSV dataset.")
    parser.add_argument(
        "--rules-csv",
        type=str,
        default=None,
        help="Path to precomputed rules CSV or export destination.",
    )
    parser.add_argument("--min-support", type=float, default=None, help="Minimum support in (0, 1].")
    parser.add_argument("--min-confidence", type=float, default=None, help="Minimum confidence in [0, 1].")
    parser.add_argument("--min-lift", type=float, default=None, help="Minimum lift (>= 0).")
    parser.add_argument("--max-len", type=int, default=None, help="Maximum itemset size.")
    parser.add_argument("--top-n", type=int, default=10, help="Maximum rules to display.")
    parser.add_argument(
        "--recommend",
        type=str,
        default="",
        help="Comma-separated basket items for cross-sell recommendations.",
    )
    parser.add_argument("--plot-output", type=str, default=None, help="Optional PNG scatter plot path.")
    parser.add_argument("--sample-baskets", type=int, default=120, help="Synthetic sample basket count.")
    parser.add_argument("--seed", type=int, default=42, help="Seed for synthetic sample generator.")
    parser.add_argument("--health", action="store_true", help="Run config and cached rules check.")
    return parser.parse_args(argv)


def _export_rules_csv(rules: Sequence[AssociationRuleItem], destination: Path) -> None:
    """Persist mined rules to CSV in a clean tabular layout."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "antecedents": str(frozenset(rule.antecedents)),
            "consequents": str(frozenset(rule.consequents)),
            "antecedent support": rule.antecedent_support,
            "consequent support": rule.consequent_support,
            "support": rule.support,
            "confidence": rule.confidence,
            "lift": rule.lift,
            "leverage": rule.leverage,
            "conviction": rule.conviction,
        }
        for rule in rules
    ]
    pd.DataFrame(rows).to_csv(destination, index=False)
    logger.info("Exported %d association rules to '%s'", len(rows), destination)


def _run_health_check(config: MBAConfig, rules_override: str | None) -> int:
    """Verify validated configuration and cached rules availability."""
    rules_path = Path(rules_override) if rules_override else config.default_rules_path
    cached_count = 0
    cached_available = False
    if rules_path.is_file():
        cached_rules = load_cached_rules(rules_path, max_rules=200)
        cached_count = len(cached_rules)
        cached_available = True

    payload = {
        "status": "ok",
        "rules_path": str(rules_path),
        "cached_rules_available": cached_available,
        "cached_rules_count": cached_count,
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


def _emit_cached_rules(rules_csv: str, top_n: int, recommend_raw: str) -> int:
    """Load cached rules CSV, evaluate optional recommendations, and write JSON."""
    cached_rules = load_cached_rules(rules_csv, max_rules=top_n)
    query_items = [item.strip() for item in recommend_raw.split(",") if item.strip()]
    recs = recommend_for_items(query_items, cached_rules) if query_items else []
    payload = {
        "source": rules_csv,
        "rules_count": len(cached_rules),
        "rules": [rule.model_dump() for rule in cached_rules],
        "recommendations": [rec.model_dump() for rec in recs],
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


def run_cli(args: argparse.Namespace, config: MBAConfig | None = None) -> int:
    """Execute the Market Basket Analysis CLI pipeline and emit JSON output."""
    cfg = config or MBAConfig.from_env()
    configure_logging(cfg.log_level)

    if args.health:
        return _run_health_check(cfg, args.rules_csv)

    if not args.input and args.rules_csv and Path(args.rules_csv).is_file():
        return _emit_cached_rules(args.rules_csv, args.top_n, args.recommend)

    if args.input:
        baskets = extract_baskets(load_retail_csv(args.input), min_basket_items=1)
        source_label = args.input
    else:
        baskets = generate_sample_baskets(num_baskets=args.sample_baskets, seed=args.seed)
        source_label = "synthetic_sample"

    all_rules = mine_association_rules(
        baskets,
        min_support=cfg.min_support if args.min_support is None else args.min_support,
        min_confidence=cfg.min_confidence if args.min_confidence is None else args.min_confidence,
        min_lift=cfg.min_lift if args.min_lift is None else args.min_lift,
        max_len=cfg.max_len if args.max_len is None else args.max_len,
        max_items=cfg.max_items,
        top_n=None,
    )
    rules = all_rules[: args.top_n]
    if args.rules_csv and rules:
        _export_rules_csv(rules, Path(args.rules_csv))
    if args.plot_output and rules:
        save_rules_scatter_plot(rules, Path(args.plot_output))

    query_items = [item.strip() for item in args.recommend.split(",") if item.strip()]
    recommendations = recommend_for_items(query_items, all_rules) if query_items and all_rules else []
    output = {
        "source": source_label,
        "total_baskets": len(baskets),
        "rules_count": len(rules),
        "rules": [rule.model_dump() for rule in rules],
        "recommendations": [rec.model_dump() for rec in recommendations],
    }
    sys.stdout.write(json.dumps(output, indent=2) + "\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint returning process exit code."""
    args = parse_args(argv)
    try:
        return run_cli(args)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("CLI execution failed: %s", exc)
        sys.stderr.write(json.dumps({"error": str(exc)}) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
