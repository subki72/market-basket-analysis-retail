"""Unit tests for MBAConfig, logging configuration, and Pydantic v2 schemas."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
import pytest

from src.mba_engine.config import MBAConfig, configure_logging
from src.mba_engine.schemas import BasketAnalysisRequest, TransactionLine


def test_config_defaults_and_validate_pass() -> None:
    """Default MBAConfig should pass validation cleanly."""
    # Arrange & Act
    cfg = MBAConfig()
    cfg.validate()

    # Assert
    assert cfg.min_support == 0.02
    assert cfg.min_confidence == 0.30
    assert cfg.min_lift == 1.0
    assert cfg.max_len == 3
    assert cfg.default_rules_path == Path("MBA_Results_TopRules.csv")


def test_config_from_env_parses_custom_values() -> None:
    """from_env should parse numeric thresholds, paths, and CORS origins."""
    # Arrange
    env = {
        "MBA_MIN_SUPPORT": "0.05",
        "MBA_MIN_CONFIDENCE": "0.55",
        "MBA_MIN_LIFT": "1.5",
        "MBA_MAX_LEN": "4",
        "MBA_MAX_ITEMS": "250",
        "MBA_ALLOWED_ORIGINS": "https://app.example.com, http://localhost:5173",
        "MBA_DEFAULT_RULES_PATH": "custom_rules.csv",
        "MBA_LOG_LEVEL": "debug",
        "MBA_RATE_LIMIT_PER_MINUTE": "120",
        "MBA_REQUEST_TIMEOUT_SECONDS": "15.5",
    }

    # Act
    cfg = MBAConfig.from_env(env=env)

    # Assert
    assert cfg.min_support == 0.05
    assert cfg.min_confidence == 0.55
    assert cfg.min_lift == 1.5
    assert cfg.max_len == 4
    assert cfg.max_items == 250
    assert cfg.allowed_origins == ("https://app.example.com", "http://localhost:5173")
    assert cfg.default_rules_path == Path("custom_rules.csv")
    assert cfg.log_level == "DEBUG"
    assert cfg.rate_limit_per_minute == 120
    assert cfg.request_timeout_seconds == 15.5


def test_config_invalid_numeric_raises_value_error() -> None:
    """Non-numeric environment variables should fail fast with ValueError."""
    # Arrange
    env = {"MBA_MIN_SUPPORT": "not-a-number"}

    # Act & Assert
    with pytest.raises(ValueError, match="MBA_MIN_SUPPORT"):
        MBAConfig.from_env(env=env)


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_support": 0.0},
        {"min_support": 1.2},
        {"min_confidence": -0.1},
        {"min_lift": -1.0},
        {"max_len": 1},
        {"max_items": 1},
        {"rate_limit_per_minute": 0},
        {"request_timeout_seconds": 0.0},
        {"log_level": "TRACE"},
    ],
)
def test_config_invalid_bounds_raise_value_error(overrides: dict[str, object]) -> None:
    """Out-of-bounds configuration values must raise ValueError."""
    # Arrange
    cfg = MBAConfig(**overrides)  # type: ignore[arg-type]

    # Act & Assert
    with pytest.raises(ValueError):
        cfg.validate()


def test_configure_logging_sets_requested_level() -> None:
    """configure_logging should apply valid log levels and reject invalid ones."""
    # Arrange & Act
    logger = configure_logging("WARNING")

    # Assert
    assert logger.level == 30
    with pytest.raises(ValueError, match="Unsupported log level"):
        configure_logging("VERBOSE")


def test_basket_analysis_request_requires_non_empty_source() -> None:
    """BasketAnalysisRequest must reject payloads without transactions or baskets."""
    # Arrange & Act & Assert
    with pytest.raises(ValidationError, match="non-empty"):
        BasketAnalysisRequest(transactions=None, baskets=[])


def test_basket_analysis_request_accepts_transactions_or_baskets() -> None:
    """Valid transactions or raw baskets payloads should instantiate cleanly."""
    # Arrange
    tx = TransactionLine(order_id="1001", product_name="  Red Mug ", quantity=2, price=3.5)

    # Act
    req = BasketAnalysisRequest(transactions=[tx], min_support=0.1)

    # Assert
    assert req.transactions is not None
    assert req.transactions[0].product_name == "Red Mug"
    assert req.min_support == 0.1


def test_transaction_line_rejects_non_positive_quantity_or_price() -> None:
    """Zero or negative quantity/price must be rejected by Pydantic schema validation."""
    # Arrange & Act & Assert
    with pytest.raises(ValidationError):
        TransactionLine(order_id="1001", product_name="mug", quantity=0, price=2.0)
    with pytest.raises(ValidationError):
        TransactionLine(order_id="1001", product_name="mug", quantity=1, price=0.0)
