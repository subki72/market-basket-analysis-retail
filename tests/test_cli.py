"""Unit and functional tests for the Market Basket Analysis CLI entrypoint."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from main import main


def test_cli_health_check_reports_cached_rules(capsys: pytest.CaptureFixture[str]) -> None:
    """--health flag should verify configuration and cached rules availability."""
    # Arrange & Act
    exit_code = main(["--health"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    # Assert
    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["cached_rules_available"] is True
    assert payload["cached_rules_count"] > 0


def test_cli_sample_mode_exports_rules_and_plot(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI synthetic sample mode should mine rules, write CSV/PNG, and emit recommendations."""
    # Arrange
    export_csv = tmp_path / "mined_rules.csv"
    export_png = tmp_path / "scatter.png"

    # Act
    exit_code = main(
        [
            "--sample-baskets",
            "80",
            "--min-support",
            "0.05",
            "--min-confidence",
            "0.40",
            "--top-n",
            "8",
            "--recommend",
            "sweetheart ceramic trinket box",
            "--rules-csv",
            str(export_csv),
            "--plot-output",
            str(export_png),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    # Assert
    assert exit_code == 0
    assert payload["source"] == "synthetic_sample"
    assert payload["total_baskets"] == 80
    assert payload["rules_count"] > 0
    assert len(payload["recommendations"]) >= 1
    assert export_csv.is_file()
    assert export_png.is_file()


def test_cli_reads_cached_rules_csv_without_reminting(capsys: pytest.CaptureFixture[str]) -> None:
    """Passing an existing rules CSV without --input should inspect cached rules directly."""
    # Arrange & Act
    exit_code = main(
        [
            "--rules-csv",
            "MBA_Results_TopRules.csv",
            "--top-n",
            "5",
            "--recommend",
            "sweetheart ceramic trinket box",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    # Assert
    assert exit_code == 0
    assert payload["rules_count"] == 5
    assert payload["recommendations"][0]["item"] == "strawberry ceramic trinket box"


def test_cli_input_csv_runs_full_pipeline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI --input should load, clean, group, and mine rules from a retail CSV file."""
    # Arrange
    rows = []
    for idx in range(1, 21):
        rows.append({"order_id": f"ORD-{idx}", "product_name": "Ceramic Cup", "quantity": 1, "price": 4.5})
        rows.append({"order_id": f"ORD-{idx}", "product_name": "Ceramic Plate", "quantity": 1, "price": 6.5})
    rows.append({"order_id": "ORD-21", "product_name": "Wooden Spoon", "quantity": 1, "price": 2.0})
    csv_path = tmp_path / "retail_input.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    # Act
    exit_code = main(["--input", str(csv_path), "--min-support", "0.2", "--min-confidence", "0.5"])
    payload = json.loads(capsys.readouterr().out)

    # Assert
    assert exit_code == 0
    assert payload["total_baskets"] == 21
    assert payload["rules_count"] >= 2


def test_cli_missing_input_file_returns_nonzero_exit_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-existent --input file should exit cleanly with code 1 and JSON error."""
    # Arrange
    missing = tmp_path / "missing.csv"

    # Act
    exit_code = main(["--input", str(missing)])
    err_payload = json.loads(capsys.readouterr().err)

    # Assert
    assert exit_code == 1
    assert "not found" in err_payload["error"].lower()
