"""Externalized configuration and structured logging setup for the MBA engine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

VALID_LOG_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:8000")
DEFAULT_RULES_FILENAME = "MBA_Results_TopRules.csv"


def _parse_float(raw: str, name: str) -> float:
    """Parse a float environment setting with an explicit field error."""
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid float for {name}: {raw!r}") from exc


def _parse_int(raw: str, name: str) -> int:
    """Parse an integer environment setting with an explicit field error."""
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {name}: {raw!r}") from exc


def _parse_origins(raw: str) -> tuple[str, ...]:
    """Split a comma-separated CORS allowlist into non-empty origin strings."""
    origins = tuple(item.strip() for item in raw.split(",") if item.strip())
    return origins or DEFAULT_ALLOWED_ORIGINS


@dataclass(frozen=True)
class MBAConfig:
    """Validated runtime configuration for Market Basket Analysis pipelines and API."""

    min_support: float = 0.02
    min_confidence: float = 0.30
    min_lift: float = 1.0
    max_len: int = 3
    max_items: int = 500
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS
    default_rules_path: Path = Path(DEFAULT_RULES_FILENAME)
    log_level: str = "INFO"
    rate_limit_per_minute: int = 60
    request_timeout_seconds: float = 10.0

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        dotenv_path: str | Path | None = None,
    ) -> MBAConfig:
        """Build and validate MBAConfig from environment variables or a mapping."""
        if env is None:
            load_dotenv(dotenv_path=dotenv_path)
            source: Mapping[str, str] = os.environ
        else:
            source = env

        config = cls(
            min_support=_parse_float(source.get("MBA_MIN_SUPPORT", "0.02"), "MBA_MIN_SUPPORT"),
            min_confidence=_parse_float(source.get("MBA_MIN_CONFIDENCE", "0.30"), "MBA_MIN_CONFIDENCE"),
            min_lift=_parse_float(source.get("MBA_MIN_LIFT", "1.0"), "MBA_MIN_LIFT"),
            max_len=_parse_int(source.get("MBA_MAX_LEN", "3"), "MBA_MAX_LEN"),
            max_items=_parse_int(source.get("MBA_MAX_ITEMS", "500"), "MBA_MAX_ITEMS"),
            allowed_origins=_parse_origins(source.get("MBA_ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS))),
            default_rules_path=Path(source.get("MBA_DEFAULT_RULES_PATH", DEFAULT_RULES_FILENAME)),
            log_level=source.get("MBA_LOG_LEVEL", "INFO").strip().upper(),
            rate_limit_per_minute=_parse_int(
                source.get("MBA_RATE_LIMIT_PER_MINUTE", "60"), "MBA_RATE_LIMIT_PER_MINUTE"
            ),
            request_timeout_seconds=_parse_float(
                source.get("MBA_REQUEST_TIMEOUT_SECONDS", "10.0"), "MBA_REQUEST_TIMEOUT_SECONDS"
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Validate numeric thresholds and logging configuration bounds."""
        if not 0.0 < self.min_support <= 1.0:
            raise ValueError("min_support must be in the interval (0.0, 1.0].")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be in the interval [0.0, 1.0].")
        if self.min_lift < 0.0:
            raise ValueError("min_lift must be non-negative.")
        if not 2 <= self.max_len <= 10:
            raise ValueError("max_len must be between 2 and 10.")
        if self.max_items < 2:
            raise ValueError("max_items must be at least 2.")
        if self.rate_limit_per_minute < 1:
            raise ValueError("rate_limit_per_minute must be at least 1.")
        if self.request_timeout_seconds <= 0.0:
            raise ValueError("request_timeout_seconds must be greater than 0.")
        if self.log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of {sorted(VALID_LOG_LEVELS)}.")


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured leveled logging for the mba_engine package."""
    normalized = level.strip().upper()
    if normalized not in VALID_LOG_LEVELS:
        raise ValueError(f"Unsupported log level: {level!r}")

    package_logger = logging.getLogger("mba_engine")
    if not package_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        handler.setFormatter(formatter)
        package_logger.addHandler(handler)
    package_logger.setLevel(getattr(logging, normalized))
    package_logger.propagate = False
    return package_logger
