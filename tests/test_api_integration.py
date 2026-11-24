"""Integration tests for FastAPI Market Basket Analysis microservice endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from src.mba_engine.api import create_app
from src.mba_engine.config import MBAConfig


def _build_test_client(
    tmp_rules_path: Path | None = None,
    rate_limit: int = 60,
    raise_server_exceptions: bool = True,
) -> TestClient:
    """Create an isolated FastAPI TestClient using injected MBAConfig."""
    rules_path = tmp_rules_path if tmp_rules_path is not None else Path("MBA_Results_TopRules.csv")
    cfg = MBAConfig(
        default_rules_path=rules_path,
        allowed_origins=("http://localhost:3000",),
        rate_limit_per_minute=rate_limit,
        log_level="WARNING",
    )
    app = create_app(cfg)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_api_health_endpoint_returns_ok_and_security_headers() -> None:
    """GET /health should return readiness payload and defensive HTTP headers."""
    # Arrange
    client = _build_test_client()

    # Act
    response = client.get("/health")
    body = response.json()

    # Assert
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["cached_rules_available"] is True
    assert body["cached_rules_count"] > 0
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_api_top_cached_rules_endpoint_returns_rules_and_handles_missing_file(
    tmp_path: Path,
) -> None:
    """GET /rules/top should return cached rules or 404 if artifact is absent."""
    # Arrange
    client = _build_test_client()
    missing_client = _build_test_client(tmp_rules_path=tmp_path / "absent.csv")

    # Act
    ok_resp = client.get("/rules/top?limit=5")
    missing_resp = missing_client.get("/rules/top?limit=5")

    # Assert
    assert ok_resp.status_code == 200
    assert len(ok_resp.json()) == 5
    assert missing_resp.status_code == 404


def test_api_analyze_endpoint_with_transactions_and_recommendations() -> None:
    """POST /analyze should mine rules from TransactionLine items and rank recommendations."""
    # Arrange
    client = _build_test_client()
    transactions = []
    for idx in range(1, 16):
        transactions.append({"order_id": f"O{idx}", "product_name": "Sweetheart Box"})
        transactions.append({"order_id": f"O{idx}", "product_name": "Strawberry Box"})
    transactions.append({"order_id": "O16", "product_name": "Ceramic Plate"})

    payload = {
        "transactions": transactions,
        "min_support": 0.2,
        "min_confidence": 0.5,
        "min_lift": 1.0,
        "recommend_for": ["sweetheart box"],
    }

    # Act
    response = client.post("/analyze", json=payload)
    body = response.json()

    # Assert
    assert response.status_code == 200
    assert body["total_baskets"] == 16
    assert body["unique_items"] == 3
    assert body["rules_count"] >= 2
    assert body["top_lift"] is not None
    assert body["recommendations"][0]["item"] == "strawberry box"


def test_api_analyze_endpoint_with_baskets_sparse_threshold_returns_empty_rules() -> None:
    """POST /analyze should return 200 with zero rules when support threshold excludes items."""
    # Arrange
    client = _build_test_client()
    payload = {
        "baskets": [["tea", "biscuit"], ["coffee", "cake"], ["juice", "muffin"]],
        "min_support": 0.90,
        "min_confidence": 0.80,
        "min_lift": 1.0,
    }

    # Act
    response = client.post("/analyze", json=payload)
    body = response.json()

    # Assert
    assert response.status_code == 200
    assert body["total_baskets"] == 3
    assert body["rules_count"] == 0
    assert body["rules"] == []
    assert body["top_lift"] is None


def test_api_analyze_rejects_empty_or_invalid_payload_with_422() -> None:
    """Invalid payloads must be rejected upfront with HTTP 422 validation errors."""
    # Arrange
    client = _build_test_client()

    # Act
    empty_resp = client.post("/analyze", json={"baskets": []})
    bad_support_resp = client.post("/analyze", json={"baskets": [["a", "b"]], "min_support": 0.0})

    # Assert
    assert empty_resp.status_code == 422
    assert bad_support_resp.status_code == 422


def test_api_analyze_enforces_rate_limiter_with_429() -> None:
    """Exceeding rate_limit_per_minute should return HTTP 429 cleanly."""
    # Arrange
    client = _build_test_client(rate_limit=2)
    payload = {"baskets": [["a", "b"], ["a", "b"]], "min_support": 0.5}

    # Act
    first = client.post("/analyze", json=payload)
    second = client.post("/analyze", json=payload)
    third = client.post("/analyze", json=payload)

    # Assert
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


def test_api_global_exception_handler_returns_safe_500_without_leaking_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unhandled exceptions must trigger global 500 JSON boundary without trace leaks."""

    # Arrange
    def _boom(*args: object, **kwargs: object) -> list[object]:
        raise RuntimeError("unexpected-backend-database-crash")

    monkeypatch.setattr("src.mba_engine.api.mine_association_rules", _boom)
    client = _build_test_client(raise_server_exceptions=False)

    # Act
    response = client.post("/analyze", json={"baskets": [["cup", "saucer"]], "min_support": 0.5})
    body = response.json()

    # Assert
    assert response.status_code == 500
    assert body == {"detail": "Internal server error while processing market basket analysis."}
    assert "unexpected-backend-database-crash" not in response.text
    assert "Traceback" not in response.text
