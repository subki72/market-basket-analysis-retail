"""FastAPI microservice exposing market basket health, cached rules, and live mining."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
import logging
import threading
import time

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.mba_engine.config import MBAConfig, configure_logging
from src.mba_engine.loader import load_cached_rules, transactions_to_baskets
from src.mba_engine.miner import mine_association_rules, recommend_for_items
from src.mba_engine.schemas import (
    AssociationRuleItem,
    BasketAnalysisRequest,
    BasketAnalysisResponse,
    HealthResponse,
)

logger = logging.getLogger(__name__)
APP_VERSION = "1.0.0"


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window rate limiter keyed by client IP."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be at least 1.")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client_key: str, now: float | None = None) -> bool:
        """Return True if the caller is within the rate limit window."""
        timestamp = time.monotonic() if now is None else now
        cutoff = timestamp - self.window_seconds

        with self._lock:
            history = self._buckets[client_key]
            while history and history[0] <= cutoff:
                history.popleft()
            if len(history) >= self.max_requests:
                return False
            history.append(timestamp)
            return True


def _resolve_request_baskets(payload: BasketAnalysisRequest) -> list[list[str]]:
    """Extract normalized baskets from either line-item transactions or raw baskets."""
    if payload.transactions:
        return transactions_to_baskets(payload.transactions, min_basket_items=1)
    raw_baskets = payload.baskets or []
    return [
        sorted({item.lower().strip() for item in basket if item.strip()})
        for basket in raw_baskets
        if any(item.strip() for item in basket)
    ]


def _count_unique_items(baskets: list[list[str]]) -> int:
    """Count distinct products across normalized baskets."""
    return len({item for basket in baskets for item in basket})


def _probe_cached_rules(cfg: MBAConfig) -> tuple[bool, int]:
    """Check cached rules CSV readiness without raising during health probes."""
    try:
        rules = load_cached_rules(cfg.default_rules_path, max_rules=200)
        return True, len(rules)
    except (FileNotFoundError, OSError, ValueError) as exc:
        logger.warning("Cached rules unavailable during health check: %s", exc)
        return False, 0


def _register_middlewares_and_handlers(app: FastAPI, cfg: MBAConfig) -> None:
    """Attach CORS, security headers, and global exception handler to FastAPI."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def attach_security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error while processing market basket analysis."},
        )


def _build_analysis_response(
    baskets: list[list[str]],
    payload: BasketAnalysisRequest,
    cfg: MBAConfig,
) -> BasketAnalysisResponse:
    """Execute rule mining and recommendation scoring for an API request."""
    all_rules = mine_association_rules(
        baskets,
        min_support=payload.min_support,
        min_confidence=payload.min_confidence,
        min_lift=payload.min_lift,
        max_len=payload.max_len,
        max_items=cfg.max_items,
        top_n=None,
    )
    recommendations = (
        recommend_for_items(payload.recommend_for, all_rules) if payload.recommend_for and all_rules else []
    )
    rules = all_rules[: payload.top_n]
    top_lift = max((rule.lift for rule in rules), default=None)
    top_confidence = max((rule.confidence for rule in rules), default=None)

    logger.info(
        "Analyzed %d baskets -> %d rules, %d recommendations",
        len(baskets),
        len(rules),
        len(recommendations),
    )
    return BasketAnalysisResponse(
        total_baskets=len(baskets),
        unique_items=_count_unique_items(baskets),
        rules_count=len(rules),
        rules=rules,
        recommendations=recommendations,
        top_lift=top_lift,
        top_confidence=top_confidence,
    )


def _register_routes(
    app: FastAPI,
    cfg: MBAConfig,
    rate_limiter: SlidingWindowRateLimiter,
) -> None:
    """Register health, cached rules, and live basket mining endpoints."""

    @app.get("/health", response_model=HealthResponse, tags=["operations"])
    def health_check() -> HealthResponse:
        """Liveness and cached rule artifact readiness probe."""
        available, count = _probe_cached_rules(cfg)
        return HealthResponse(
            status="ok",
            version=APP_VERSION,
            cached_rules_available=available,
            cached_rules_count=count,
        )

    @app.get("/rules/top", response_model=list[AssociationRuleItem], tags=["analysis"])
    def get_top_cached_rules(limit: int = Query(default=20, ge=1, le=200)) -> list[AssociationRuleItem]:
        """Return precomputed top association rules sorted by confidence and lift."""
        try:
            return load_cached_rules(cfg.default_rules_path, max_rules=limit)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Cached rules file not found.") from exc

    @app.post("/analyze", response_model=BasketAnalysisResponse, tags=["analysis"])
    def analyze_baskets(payload: BasketAnalysisRequest, request: Request) -> BasketAnalysisResponse:
        """Mine association rules and cross-sell recommendations from submitted baskets."""
        client_host = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_host):
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Retry shortly.")

        baskets = _resolve_request_baskets(payload)
        return _build_analysis_response(baskets, payload, cfg)


def create_app(config: MBAConfig | None = None) -> FastAPI:
    """Build and configure the FastAPI Market Basket Analysis application."""
    cfg = config or MBAConfig.from_env()
    cfg.validate()
    configure_logging(cfg.log_level)

    app = FastAPI(
        title="Market Basket Analysis API",
        version=APP_VERSION,
        description="Production Apriori association rule mining and cross-sell API.",
    )
    rate_limiter = SlidingWindowRateLimiter(max_requests=cfg.rate_limit_per_minute)
    _register_middlewares_and_handlers(app, cfg)
    _register_routes(app, cfg, rate_limiter)
    return app


app = create_app()
