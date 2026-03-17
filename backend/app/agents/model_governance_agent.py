"""
Model Governance Agent

Tracks and manages model/strategy performance:
- Model version tracking
- Performance degradation detection
- Automatic model disabling
- A/B testing support
- Drift detection
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import statistics
import json

from app.agents.base_agent import BaseAgent, AgentOutput


class ModelStatus(Enum):
    """Model operational status."""
    ACTIVE = "active"  # Model is live and trading
    SHADOW = "shadow"  # Model runs but doesn't execute
    PROBATION = "probation"  # Reduced allocation due to poor performance
    DISABLED = "disabled"  # Model is disabled
    TESTING = "testing"  # A/B testing mode


class DriftType(Enum):
    """Types of model drift."""
    NONE = "none"
    CONCEPT_DRIFT = "concept_drift"  # Market regime changed
    DATA_DRIFT = "data_drift"  # Input distributions changed
    PERFORMANCE_DRIFT = "performance_drift"  # Metrics degrading


@dataclass
class ModelVersion:
    """Tracked model version."""
    model_id: str
    strategy_name: str
    version: str
    created_at: datetime
    status: ModelStatus
    parameters: Dict[str, Any]
    
    # Performance tracking
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    
    # Recent performance (rolling 30 trades)
    recent_win_rate: float = 0.0
    recent_expectancy: float = 0.0
    recent_profit_factor: float = 0.0
    
    # Drift tracking
    drift_detected: DriftType = DriftType.NONE
    drift_score: float = 0.0
    
    # Metadata
    last_trade_at: Optional[datetime] = None
    last_review_at: Optional[datetime] = None
    notes: str = ""


@dataclass
class PerformanceThresholds:
    """Thresholds for model governance decisions."""
    # Minimum thresholds to stay active
    min_win_rate: float = 0.35
    min_profit_factor: float = 1.0
    min_expectancy: float = 0.0
    max_drawdown_pct: float = 8.0
    
    # Warning thresholds (triggers probation)
    warn_win_rate: float = 0.40
    warn_profit_factor: float = 1.2
    warn_expectancy: float = 0.1
    warn_drawdown_pct: float = 5.0
    
    # Trades needed for evaluation
    min_trades_for_eval: int = 20
    rolling_window_size: int = 30
    
    # Drift detection
    drift_threshold: float = 0.3
    min_trades_for_drift: int = 50


@dataclass
class GovernanceDecision:
    """Model governance decision."""
    model_id: str
    decision: str  # "maintain", "probation", "disable", "restore"
    reason: str
    previous_status: ModelStatus
    new_status: ModelStatus
    metrics_snapshot: Dict[str, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ModelGovernanceAgent(BaseAgent):
    """Manages model lifecycle and performance governance."""
    
    def __init__(self, db_session=None, redis_client=None):
        super().__init__(
            name="ModelGovernanceAgent",
            description="Tracks model performance and manages model lifecycle",
            dependencies=["PerformanceAnalyticsAgent"]
        )
        self.db = db_session
        self.redis = redis_client
        
        self.thresholds = PerformanceThresholds()
        self.models: Dict[str, ModelVersion] = {}
        self.decisions: List[GovernanceDecision] = []
    
    async def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        """Analyze all models and make governance decisions."""
        try:
            # Load registered models
            await self._load_models()
            
            decisions = []
            model_statuses = []
            drift_alerts = []
            
            for model_id, model in self.models.items():
                # Update model metrics from recent trades
                await self._update_model_metrics(model)
                
                # Check for drift
                drift = await self._detect_drift(model)
                if drift != DriftType.NONE:
                    drift_alerts.append({
                        "model_id": model_id,
                        "drift_type": drift.value,
                        "drift_score": model.drift_score,
                    })
                
                # Make governance decision
                decision = self._evaluate_model(model)
                if decision:
                    decisions.append(decision)
                    await self._apply_decision(decision)
                
                model_statuses.append({
                    "model_id": model.model_id,
                    "strategy": model.strategy_name,
                    "version": model.version,
                    "status": model.status.value,
                    "total_trades": model.total_trades,
                    "win_rate": round(model.win_rate, 3),
                    "profit_factor": round(model.profit_factor, 2),
                    "expectancy": round(model.expectancy, 3),
                    "max_drawdown": round(model.max_drawdown_pct, 2),
                    "recent_win_rate": round(model.recent_win_rate, 3),
                    "drift": model.drift_detected.value,
                })
            
            return AgentOutput(
                agent_name=self.name,
                timestamp=datetime.utcnow(),
                data={
                    "models": model_statuses,
                    "decisions": [d.__dict__ for d in decisions],
                    "drift_alerts": drift_alerts,
                    "active_models": sum(1 for m in self.models.values() if m.status == ModelStatus.ACTIVE),
                    "disabled_models": sum(1 for m in self.models.values() if m.status == ModelStatus.DISABLED),
                    "models_on_probation": sum(1 for m in self.models.values() if m.status == ModelStatus.PROBATION),
                },
                confidence=1.0,
                metadata={
                    "total_models": len(self.models),
                    "decisions_made": len(decisions),
                }
            )
            
        except Exception as e:
            self.logger.error(f"Model governance analysis failed: {e}")
            return AgentOutput(
                agent_name=self.name,
                timestamp=datetime.utcnow(),
                data={},
                confidence=0.0,
                errors=[str(e)]
            )
    
    async def register_model(
        self,
        strategy_name: str,
        version: str,
        parameters: Dict[str, Any],
        initial_status: ModelStatus = ModelStatus.SHADOW
    ) -> ModelVersion:
        """Register a new model for governance tracking."""
        
        model_id = f"{strategy_name}_{version}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        model = ModelVersion(
            model_id=model_id,
            strategy_name=strategy_name,
            version=version,
            created_at=datetime.utcnow(),
            status=initial_status,
            parameters=parameters,
        )
        
        self.models[model_id] = model
        
        # Persist to database
        await self._save_model(model)
        
        self.logger.info(f"Registered model: {model_id} (status: {initial_status.value})")
        
        return model
    
    async def record_trade(self, model_id: str, trade_result: Dict[str, Any]):
        """Record a trade result for a model."""
        
        if model_id not in self.models:
            self.logger.warning(f"Unknown model: {model_id}")
            return
        
        model = self.models[model_id]
        
        # Update metrics incrementally
        pnl = trade_result.get("pnl", 0)
        r_multiple = trade_result.get("r_multiple", 0)
        
        model.total_trades += 1
        model.last_trade_at = datetime.utcnow()
        
        # Store trade for rolling calculations
        trade_key = f"model_trades:{model_id}"
        trade_data = json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "pnl": pnl,
            "r_multiple": r_multiple,
            "is_win": pnl > 0,
        })
        
        if self.redis:
            # Use Redis list with max length
            await self.redis.lpush(trade_key, trade_data)
            await self.redis.ltrim(trade_key, 0, 99)  # Keep last 100 trades
    
    async def _load_models(self):
        """Load models from database."""
        # TODO: Implement database loading
        pass
    
    async def _save_model(self, model: ModelVersion):
        """Save model to database."""
        # TODO: Implement database saving
        pass
    
    async def _update_model_metrics(self, model: ModelVersion):
        """Update model metrics from recent trades."""
        
        if not self.redis:
            return
        
        trade_key = f"model_trades:{model.model_id}"
        trades_raw = await self.redis.lrange(trade_key, 0, -1)
        
        if not trades_raw:
            return
        
        trades = [json.loads(t) for t in trades_raw]
        
        # Calculate overall metrics
        wins = sum(1 for t in trades if t["is_win"])
        if trades:
            model.win_rate = wins / len(trades)
        
        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
        
        if gross_loss > 0:
            model.profit_factor = gross_profit / gross_loss
        
        r_values = [t["r_multiple"] for t in trades]
        if r_values:
            model.expectancy = statistics.mean(r_values)
        
        # Calculate recent metrics (last 30 trades)
        recent = trades[:self.thresholds.rolling_window_size]
        if recent:
            recent_wins = sum(1 for t in recent if t["is_win"])
            model.recent_win_rate = recent_wins / len(recent)
            
            recent_r = [t["r_multiple"] for t in recent]
            model.recent_expectancy = statistics.mean(recent_r) if recent_r else 0
            
            recent_profit = sum(t["pnl"] for t in recent if t["pnl"] > 0)
            recent_loss = abs(sum(t["pnl"] for t in recent if t["pnl"] < 0))
            if recent_loss > 0:
                model.recent_profit_factor = recent_profit / recent_loss
        
        # Calculate max drawdown
        cumulative = 0
        peak = 0
        max_dd = 0
        
        for t in reversed(trades):  # Chronological order
            cumulative += t["pnl"]
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        model.max_drawdown_pct = max_dd
    
    async def _detect_drift(self, model: ModelVersion) -> DriftType:
        """Detect if model is experiencing drift."""
        
        if model.total_trades < self.thresholds.min_trades_for_drift:
            return DriftType.NONE
        
        # Compare recent performance to historical
        historical_win_rate = model.win_rate
        recent_win_rate = model.recent_win_rate
        
        historical_expectancy = model.expectancy
        recent_expectancy = model.recent_expectancy
        
        # Calculate drift score
        win_rate_drift = abs(historical_win_rate - recent_win_rate) / max(historical_win_rate, 0.001)
        expectancy_drift = abs(historical_expectancy - recent_expectancy) / max(abs(historical_expectancy), 0.001)
        
        model.drift_score = (win_rate_drift + expectancy_drift) / 2
        
        if model.drift_score > self.thresholds.drift_threshold:
            # Determine drift type based on direction
            if recent_expectancy < historical_expectancy:
                model.drift_detected = DriftType.PERFORMANCE_DRIFT
            else:
                model.drift_detected = DriftType.CONCEPT_DRIFT
            
            return model.drift_detected
        
        model.drift_detected = DriftType.NONE
        return DriftType.NONE
    
    def _evaluate_model(self, model: ModelVersion) -> Optional[GovernanceDecision]:
        """Evaluate model and make governance decision."""
        
        # Skip if not enough trades
        if model.total_trades < self.thresholds.min_trades_for_eval:
            return None
        
        previous_status = model.status
        new_status = model.status
        decision = "maintain"
        reason = ""
        
        # Check hard limits (immediate disable)
        if model.win_rate < self.thresholds.min_win_rate:
            new_status = ModelStatus.DISABLED
            decision = "disable"
            reason = f"Win rate {model.win_rate:.1%} below minimum {self.thresholds.min_win_rate:.1%}"
        
        elif model.profit_factor < self.thresholds.min_profit_factor:
            new_status = ModelStatus.DISABLED
            decision = "disable"
            reason = f"Profit factor {model.profit_factor:.2f} below minimum {self.thresholds.min_profit_factor:.2f}"
        
        elif model.max_drawdown_pct > self.thresholds.max_drawdown_pct:
            new_status = ModelStatus.DISABLED
            decision = "disable"
            reason = f"Drawdown {model.max_drawdown_pct:.1f}% exceeds maximum {self.thresholds.max_drawdown_pct:.1f}%"
        
        # Check warning thresholds (probation)
        elif model.status == ModelStatus.ACTIVE:
            if model.recent_win_rate < self.thresholds.warn_win_rate:
                new_status = ModelStatus.PROBATION
                decision = "probation"
                reason = f"Recent win rate {model.recent_win_rate:.1%} below warning threshold"
            
            elif model.recent_profit_factor < self.thresholds.warn_profit_factor:
                new_status = ModelStatus.PROBATION
                decision = "probation"
                reason = f"Recent profit factor {model.recent_profit_factor:.2f} below warning threshold"
            
            elif model.drift_detected != DriftType.NONE:
                new_status = ModelStatus.PROBATION
                decision = "probation"
                reason = f"Drift detected: {model.drift_detected.value} (score: {model.drift_score:.2f})"
        
        # Check for recovery (restore from probation)
        elif model.status == ModelStatus.PROBATION:
            if (model.recent_win_rate >= self.thresholds.warn_win_rate and
                model.recent_profit_factor >= self.thresholds.warn_profit_factor and
                model.drift_detected == DriftType.NONE):
                new_status = ModelStatus.ACTIVE
                decision = "restore"
                reason = "Performance recovered to acceptable levels"
        
        if new_status != previous_status:
            return GovernanceDecision(
                model_id=model.model_id,
                decision=decision,
                reason=reason,
                previous_status=previous_status,
                new_status=new_status,
                metrics_snapshot={
                    "win_rate": model.win_rate,
                    "profit_factor": model.profit_factor,
                    "expectancy": model.expectancy,
                    "max_drawdown": model.max_drawdown_pct,
                    "recent_win_rate": model.recent_win_rate,
                    "drift_score": model.drift_score,
                },
            )
        
        return None
    
    async def _apply_decision(self, decision: GovernanceDecision):
        """Apply governance decision to model."""
        
        if decision.model_id not in self.models:
            return
        
        model = self.models[decision.model_id]
        model.status = decision.new_status
        model.last_review_at = datetime.utcnow()
        
        self.decisions.append(decision)
        
        # Log the decision
        self.logger.info(
            f"Model governance: {decision.model_id} - {decision.decision} "
            f"({decision.previous_status.value} → {decision.new_status.value}): {decision.reason}"
        )
        
        # Persist
        await self._save_model(model)
    
    async def get_active_strategies(self) -> List[str]:
        """Get list of currently active strategy names."""
        return [
            m.strategy_name
            for m in self.models.values()
            if m.status in (ModelStatus.ACTIVE, ModelStatus.PROBATION)
        ]
    
    async def get_model_allocation(self, strategy_name: str) -> float:
        """Get allocation multiplier for a strategy."""
        
        models = [m for m in self.models.values() if m.strategy_name == strategy_name]
        if not models:
            return 1.0
        
        # Use most recent model
        model = max(models, key=lambda m: m.created_at)
        
        if model.status == ModelStatus.ACTIVE:
            return 1.0
        elif model.status == ModelStatus.PROBATION:
            return 0.5  # Reduced allocation
        elif model.status == ModelStatus.SHADOW:
            return 0.0  # No real allocation
        else:
            return 0.0
    
    async def compare_models(self, model_ids: List[str]) -> Dict:
        """Compare performance of multiple models."""
        
        comparison = []
        
        for model_id in model_ids:
            if model_id not in self.models:
                continue
            
            model = self.models[model_id]
            comparison.append({
                "model_id": model_id,
                "strategy": model.strategy_name,
                "version": model.version,
                "status": model.status.value,
                "total_trades": model.total_trades,
                "win_rate": model.win_rate,
                "profit_factor": model.profit_factor,
                "expectancy": model.expectancy,
                "sharpe_ratio": model.sharpe_ratio,
                "max_drawdown": model.max_drawdown_pct,
            })
        
        # Rank by expectancy
        comparison.sort(key=lambda x: x["expectancy"], reverse=True)
        
        return {
            "models": comparison,
            "recommendation": comparison[0]["model_id"] if comparison else None,
        }
