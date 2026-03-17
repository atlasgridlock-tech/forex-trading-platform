"""
Portfolio Exposure Agent
========================
Prevents hidden concentration risk by analyzing exposure at the CURRENCY level,
not just the pair level.

From 06_RISK_FRAMEWORK.txt:
KEY INSIGHT: If you are long EURUSD, long EURJPY, and long EURGBP, you have
MASSIVE EUR exposure even though they are "different pairs."
"""
import structlog
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict

from app.agents.base_agent import BaseAgent, AgentMessage, AgentHealthStatus

logger = structlog.get_logger()


# Currency pair decomposition
PAIR_CURRENCIES = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "USDJPY": ("USD", "JPY"),
    "GBPJPY": ("GBP", "JPY"),
    "USDCHF": ("USD", "CHF"),
    "USDCAD": ("USD", "CAD"),
    "EURAUD": ("EUR", "AUD"),
    "AUDNZD": ("AUD", "NZD"),
    "AUDUSD": ("AUD", "USD"),
    "EURGBP": ("EUR", "GBP"),
    "EURJPY": ("EUR", "JPY"),
    "EURCHF": ("EUR", "CHF"),
    "GBPCHF": ("GBP", "CHF"),
    "NZDUSD": ("NZD", "USD"),
    "CADJPY": ("CAD", "JPY"),
    "CHFJPY": ("CHF", "JPY"),
}

# Correlation groups (pairs that tend to move together)
CORRELATION_GROUPS = {
    "usd_majors": ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"],
    "jpy_crosses": ["USDJPY", "GBPJPY", "EURJPY", "CADJPY", "CHFJPY"],
    "eur_crosses": ["EURUSD", "EURJPY", "EURGBP", "EURCHF", "EURAUD"],
    "gbp_pairs": ["GBPUSD", "GBPJPY", "EURGBP", "GBPCHF"],
    "commodity_currencies": ["AUDUSD", "AUDNZD", "USDCAD", "NZDUSD"],
}


@dataclass
class CurrencyExposure:
    """Exposure for a single currency."""
    currency: str
    net_lots_long: float = 0.0
    net_lots_short: float = 0.0
    position_count: int = 0
    risk_at_stake_pct: float = 0.0
    
    @property
    def net_exposure(self) -> float:
        """Net exposure (positive = long, negative = short)."""
        return self.net_lots_long - self.net_lots_short
    
    @property
    def exposure_direction(self) -> str:
        if self.net_exposure > 0.01:
            return "net_long"
        elif self.net_exposure < -0.01:
            return "net_short"
        return "neutral"


@dataclass
class CorrelatedCluster:
    """A cluster of correlated positions."""
    cluster_name: str
    symbols: list = field(default_factory=list)
    total_lots: float = 0.0
    total_risk_pct: float = 0.0
    direction_bias: str = "mixed"  # bullish, bearish, mixed


@dataclass
class PortfolioExposureCheck:
    """Result of portfolio exposure check for a proposed trade."""
    symbol: str
    proposed_direction: str
    is_acceptable: bool
    
    # Current state
    current_currency_exposures: dict = field(default_factory=dict)
    current_correlated_clusters: list = field(default_factory=list)
    
    # After trade state
    after_exposure_base: float = 0.0
    after_exposure_quote: float = 0.0
    
    # Analysis
    concentration_score: float = 0.0  # 0.0 = diversified, 1.0 = concentrated
    recommendation: str = "approve"  # approve, reduce_size, deny
    reasoning: str = ""
    warnings: list = field(default_factory=list)


class PortfolioExposureAgent(BaseAgent):
    """
    Portfolio Exposure Agent.
    
    Tracks currency-level exposure and detects hidden concentration risk.
    
    Prevents scenarios like:
    - Long EURUSD, long EURJPY, long EURGBP = massive EUR exposure
    - Long USDJPY, short EURJPY = hidden USD/EUR/JPY exposure
    """
    
    def __init__(
        self,
        name: str = "portfolio_exposure_agent",
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(name, config)
        
        self.max_currency_positions = config.get("max_currency_positions", 3) if config else 3
        self.max_correlated_exposure = config.get("max_correlated_exposure", 2) if config else 2
        self.concentration_threshold = config.get("concentration_threshold", 0.7) if config else 0.7
        
        # Current open positions (synced with risk manager)
        self._open_positions: list[dict] = []
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.is_initialized = True
        self.is_running = True
        self.started_at = datetime.now(timezone.utc)
        self._logger.info("Portfolio Exposure Agent initialized")
    
    async def run(self, context: dict[str, Any]) -> AgentMessage:
        """
        Check portfolio exposure for a proposed trade.
        
        Args:
            context: Must contain:
                - symbol: Proposed symbol
                - direction: "long" or "short"
                - lot_size: Proposed lot size
                - risk_pct: Proposed risk percentage
                - open_positions (optional): Current positions if not using internal state
        """
        symbol = context.get("symbol")
        direction = context.get("direction")
        lot_size = float(context.get("lot_size", 0.01))
        risk_pct = float(context.get("risk_pct", 0.35))
        
        if not symbol or not direction:
            return self._create_message(
                message_type="error",
                payload={"error": "Missing symbol or direction"},
                symbol=symbol,
                confidence=0.0,
                errors=["Missing required parameters"],
            )
        
        # Use provided positions or internal state
        positions = context.get("open_positions", self._open_positions)
        
        # Perform check
        check = await self._check_exposure(symbol, direction, lot_size, risk_pct, positions)
        
        return self._create_message(
            message_type="portfolio_exposure_check",
            payload=self._check_to_dict(check),
            symbol=symbol,
            confidence=1.0 if check.is_acceptable else 0.5,
            warnings=check.warnings,
        )
    
    async def _check_exposure(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        risk_pct: float,
        positions: list[dict],
    ) -> PortfolioExposureCheck:
        """Perform exposure analysis."""
        check = PortfolioExposureCheck(
            symbol=symbol,
            proposed_direction=direction,
            is_acceptable=True,
        )
        
        # Get currency pair
        currencies = PAIR_CURRENCIES.get(symbol)
        if not currencies:
            check.warnings.append(f"Unknown pair {symbol}, cannot analyze currency exposure")
            return check
        
        base_currency, quote_currency = currencies
        
        # Calculate current currency exposures
        currency_exposures = self._calculate_currency_exposures(positions)
        check.current_currency_exposures = {
            curr: {
                "currency": exp.currency,
                "net_exposure": exp.net_exposure,
                "direction": exp.exposure_direction,
                "position_count": exp.position_count,
            }
            for curr, exp in currency_exposures.items()
        }
        
        # Calculate correlated clusters
        check.current_correlated_clusters = self._analyze_correlated_clusters(positions)
        
        # Simulate adding the new position
        simulated_positions = positions + [{
            "symbol": symbol,
            "direction": direction,
            "lot_size": lot_size,
            "risk_pct": risk_pct,
        }]
        
        new_exposures = self._calculate_currency_exposures(simulated_positions)
        
        # Get base/quote exposure after trade
        base_exp = new_exposures.get(base_currency, CurrencyExposure(base_currency))
        quote_exp = new_exposures.get(quote_currency, CurrencyExposure(quote_currency))
        
        check.after_exposure_base = base_exp.net_exposure
        check.after_exposure_quote = quote_exp.net_exposure
        
        # CHECK 1: Currency position count
        # Long pair = long base, short quote
        # Short pair = short base, long quote
        if direction == "long":
            base_count = base_exp.position_count
            quote_count = quote_exp.position_count
        else:
            base_count = base_exp.position_count
            quote_count = quote_exp.position_count
        
        if base_count > self.max_currency_positions:
            check.is_acceptable = False
            check.recommendation = "deny"
            check.reasoning = f"Too much {base_currency} exposure: {base_count} positions"
            return check
        
        if quote_count > self.max_currency_positions:
            check.warnings.append(f"High {quote_currency} exposure: {quote_count} positions")
        
        # CHECK 2: Correlated clusters
        new_clusters = self._analyze_correlated_clusters(simulated_positions)
        for cluster in new_clusters:
            if len(cluster.symbols) > self.max_correlated_exposure:
                check.warnings.append(
                    f"High correlation: {len(cluster.symbols)} positions in {cluster.cluster_name}"
                )
                if len(cluster.symbols) > self.max_correlated_exposure + 1:
                    check.recommendation = "reduce_size"
        
        # CHECK 3: Concentration score
        check.concentration_score = self._calculate_concentration_score(new_exposures)
        
        if check.concentration_score > self.concentration_threshold:
            check.warnings.append(
                f"High concentration: {check.concentration_score:.0%}"
            )
            if check.concentration_score > 0.85:
                check.recommendation = "deny"
                check.is_acceptable = False
                check.reasoning = "Portfolio too concentrated"
                return check
        
        # Set reasoning for approved trades
        if check.is_acceptable:
            if check.warnings:
                check.recommendation = "approve"
                check.reasoning = "Acceptable with warnings"
            else:
                check.recommendation = "approve"
                check.reasoning = "Good diversification"
        
        return check
    
    def _calculate_currency_exposures(
        self,
        positions: list[dict],
    ) -> dict[str, CurrencyExposure]:
        """Calculate exposure for each currency."""
        exposures: dict[str, CurrencyExposure] = defaultdict(
            lambda: CurrencyExposure("")
        )
        
        for pos in positions:
            symbol = pos.get("symbol", "")
            direction = pos.get("direction", "")
            lot_size = float(pos.get("lot_size", 0))
            risk_pct = float(pos.get("risk_pct", 0))
            
            currencies = PAIR_CURRENCIES.get(symbol)
            if not currencies:
                continue
            
            base, quote = currencies
            
            # Initialize if needed
            if exposures[base].currency == "":
                exposures[base] = CurrencyExposure(base)
            if exposures[quote].currency == "":
                exposures[quote] = CurrencyExposure(quote)
            
            # Long pair = long base, short quote
            # Short pair = short base, long quote
            if direction == "long":
                exposures[base].net_lots_long += lot_size
                exposures[base].position_count += 1
                exposures[quote].net_lots_short += lot_size
                exposures[quote].position_count += 1
            else:
                exposures[base].net_lots_short += lot_size
                exposures[base].position_count += 1
                exposures[quote].net_lots_long += lot_size
                exposures[quote].position_count += 1
            
            exposures[base].risk_at_stake_pct += risk_pct / 2
            exposures[quote].risk_at_stake_pct += risk_pct / 2
        
        return dict(exposures)
    
    def _analyze_correlated_clusters(
        self,
        positions: list[dict],
    ) -> list[CorrelatedCluster]:
        """Analyze correlated position clusters."""
        clusters = []
        position_symbols = [p.get("symbol") for p in positions]
        
        for group_name, group_symbols in CORRELATION_GROUPS.items():
            matching = [s for s in position_symbols if s in group_symbols]
            
            if len(matching) > 1:
                # Calculate total exposure
                total_lots = sum(
                    float(p.get("lot_size", 0))
                    for p in positions
                    if p.get("symbol") in matching
                )
                total_risk = sum(
                    float(p.get("risk_pct", 0))
                    for p in positions
                    if p.get("symbol") in matching
                )
                
                # Determine direction bias
                long_count = sum(
                    1 for p in positions
                    if p.get("symbol") in matching and p.get("direction") == "long"
                )
                short_count = len(matching) - long_count
                
                if long_count > short_count:
                    bias = "bullish"
                elif short_count > long_count:
                    bias = "bearish"
                else:
                    bias = "mixed"
                
                clusters.append(CorrelatedCluster(
                    cluster_name=group_name,
                    symbols=matching,
                    total_lots=total_lots,
                    total_risk_pct=total_risk,
                    direction_bias=bias,
                ))
        
        return clusters
    
    def _calculate_concentration_score(
        self,
        exposures: dict[str, CurrencyExposure],
    ) -> float:
        """
        Calculate portfolio concentration score.
        
        0.0 = perfectly diversified
        1.0 = completely concentrated in one currency
        """
        if not exposures:
            return 0.0
        
        # Get absolute net exposures
        abs_exposures = [abs(e.net_exposure) for e in exposures.values()]
        total = sum(abs_exposures)
        
        if total == 0:
            return 0.0
        
        # Calculate Herfindahl-Hirschman Index
        shares = [e / total for e in abs_exposures]
        hhi = sum(s ** 2 for s in shares)
        
        # Normalize: 1/n (perfect diversification) to 1 (single currency)
        n = len(exposures)
        if n == 1:
            return 1.0
        
        normalized = (hhi - 1/n) / (1 - 1/n)
        return max(0.0, min(1.0, normalized))
    
    def _check_to_dict(self, check: PortfolioExposureCheck) -> dict:
        """Convert check to serializable dict."""
        return {
            "symbol": check.symbol,
            "proposed_direction": check.proposed_direction,
            "is_acceptable": check.is_acceptable,
            "current_currency_exposures": check.current_currency_exposures,
            "current_correlated_clusters": [
                {
                    "cluster_name": c.cluster_name,
                    "symbols": c.symbols,
                    "total_lots": c.total_lots,
                    "total_risk_pct": c.total_risk_pct,
                    "direction_bias": c.direction_bias,
                }
                for c in check.current_correlated_clusters
            ],
            "after_exposure_base": check.after_exposure_base,
            "after_exposure_quote": check.after_exposure_quote,
            "concentration_score": check.concentration_score,
            "recommendation": check.recommendation,
            "reasoning": check.reasoning,
            "warnings": check.warnings,
        }
    
    def sync_positions(self, positions: list[dict]) -> None:
        """Sync open positions from external source."""
        self._open_positions = positions
    
    async def health_check(self) -> AgentHealthStatus:
        return AgentHealthStatus(
            agent_name=self.name,
            is_healthy=self.is_initialized,
            last_run=self.last_run,
            last_success=self.last_success,
            last_error=self.last_error,
            consecutive_failures=self.consecutive_failures,
            uptime_seconds=self._get_uptime_seconds(),
        )
    
    def get_dependencies(self) -> list[str]:
        return []
