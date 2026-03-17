"""
Adaptive Learning System with Governance
Controlled adaptation with strict rules
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from datetime import datetime, timedelta
import json


class AdaptationType(str, Enum):
    """Types of adaptive changes."""
    CONFIDENCE_THRESHOLD = "confidence_threshold"
    STRATEGY_RANKING = "strategy_ranking"
    WEIGHT_ADJUSTMENT = "weight_adjustment"
    PARAMETER_SUGGESTION = "parameter_suggestion"
    STRATEGY_RETIREMENT = "strategy_retirement"


class AdaptationStatus(str, Enum):
    """Status of an adaptation proposal."""
    PROPOSED = "proposed"
    TESTING = "testing"
    VALIDATED = "validated"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYED = "deployed"
    ROLLED_BACK = "rolled_back"


class RiskLevel(str, Enum):
    """Risk level of adaptation."""
    LOW = "low"           # Minor threshold adjustment
    MEDIUM = "medium"     # Strategy ranking change
    HIGH = "high"         # Parameter change
    CRITICAL = "critical" # Entry/exit logic change


@dataclass
class AdaptationProposal:
    """A proposed adaptive change."""
    proposal_id: str
    adaptation_type: AdaptationType
    description: str
    
    # What's changing
    target: str  # Strategy name, parameter name, etc.
    current_value: Any
    proposed_value: Any
    
    # Justification
    reason: str
    supporting_data: dict = field(default_factory=dict)
    evidence_trades: int = 0
    
    # Risk assessment
    risk_level: RiskLevel = RiskLevel.MEDIUM
    
    # Status tracking
    status: AdaptationStatus = AdaptationStatus.PROPOSED
    proposed_at: datetime = field(default_factory=datetime.utcnow)
    proposed_by: str = "system"
    
    # Testing
    test_results: Optional[dict] = None
    validation_report: Optional[str] = None
    
    # Approval
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    
    # Deployment
    deployed_at: Optional[datetime] = None
    version_tag: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "adaptation_type": self.adaptation_type.value,
            "description": self.description,
            "target": self.target,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "reason": self.reason,
            "risk_level": self.risk_level.value,
            "status": self.status.value,
            "proposed_at": self.proposed_at.isoformat(),
            "proposed_by": self.proposed_by,
            "test_results": self.test_results,
            "approved_by": self.approved_by,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "version_tag": self.version_tag,
        }


@dataclass
class ForbiddenAction:
    """Record of a forbidden action attempt."""
    timestamp: datetime
    action_type: str
    description: str
    blocked_reason: str
    attempted_by: str


class AdaptiveLearningSystem:
    """
    Adaptive Learning System with Strict Governance
    
    ALLOWED adaptive behaviors:
    - Recalibrate confidence thresholds
    - Re-rank strategy families by regime
    - Refine weightings gradually
    - Suggest parameter changes
    - Identify dead strategies
    
    FORBIDDEN adaptive behaviors:
    - Silently changing live risk rules
    - Self-promoting untested models to live
    - Drastically altering entry/exit logic without testing
    - Using future information leakage
    
    ALL proposals must go through:
    1. Offline testing
    2. Validation report
    3. Governance approval
    4. Version tagging
    """
    
    # Limits for gradual changes
    MAX_CONFIDENCE_ADJUSTMENT = 5  # Max 5% change per adaptation
    MAX_WEIGHT_ADJUSTMENT = 0.05   # Max 5% weight change
    MIN_EVIDENCE_TRADES = 50       # Minimum trades to support change
    
    # Forbidden patterns
    FORBIDDEN_PATTERNS = [
        "risk_rule",
        "stop_loss_override",
        "live_promotion_without_test",
        "entry_logic_drastic",
        "exit_logic_drastic",
        "future_data",
    ]
    
    def __init__(self, governance_agent=None):
        self.governance = governance_agent
        
        self.proposals: Dict[str, AdaptationProposal] = {}
        self.deployed_adaptations: List[AdaptationProposal] = []
        self.forbidden_attempts: List[ForbiddenAction] = []
        
        # Current state
        self.confidence_thresholds: Dict[str, float] = {}
        self.strategy_rankings: Dict[str, Dict[str, int]] = {}  # regime -> {strategy: rank}
        self.weights: Dict[str, float] = {}
        
        self.adaptation_log: List[dict] = []
    
    def log_event(self, event_type: str, data: dict):
        """Log an adaptation event."""
        self.adaptation_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event": event_type,
            "data": data,
        })
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FORBIDDEN ACTION DETECTION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def check_forbidden_action(self, action_type: str, description: str) -> Tuple[bool, str]:
        """
        Check if an action is forbidden.
        
        Returns: (is_forbidden, reason)
        """
        # Pattern matching for forbidden actions
        lower_desc = description.lower()
        
        if "risk" in lower_desc and ("change" in lower_desc or "modify" in lower_desc):
            if "live" in lower_desc:
                return True, "Cannot silently change live risk rules"
        
        if "stop_loss" in lower_desc and "disable" in lower_desc:
            return True, "Cannot disable stop loss protection"
        
        if "promote" in lower_desc and "live" in lower_desc:
            if "without" in lower_desc and "test" in lower_desc:
                return True, "Cannot promote to live without testing"
        
        if ("entry" in lower_desc or "exit" in lower_desc) and "drastic" in lower_desc:
            return True, "Cannot drastically alter entry/exit logic without testing"
        
        if "future" in lower_desc and "data" in lower_desc:
            return True, "Future information leakage is forbidden"
        
        if "bypass" in lower_desc and "governance" in lower_desc:
            return True, "Cannot bypass governance"
        
        return False, ""
    
    def record_forbidden_attempt(self, action_type: str, description: str, attempted_by: str):
        """Record a forbidden action attempt."""
        is_forbidden, reason = self.check_forbidden_action(action_type, description)
        
        if is_forbidden:
            self.forbidden_attempts.append(ForbiddenAction(
                timestamp=datetime.utcnow(),
                action_type=action_type,
                description=description,
                blocked_reason=reason,
                attempted_by=attempted_by,
            ))
            
            self.log_event("forbidden_attempt_blocked", {
                "action_type": action_type,
                "description": description,
                "reason": reason,
            })
        
        return is_forbidden, reason
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ALLOWED ADAPTATIONS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def propose_confidence_adjustment(
        self,
        strategy: str,
        current_threshold: float,
        proposed_threshold: float,
        reason: str,
        supporting_trades: int
    ) -> Optional[AdaptationProposal]:
        """
        Propose a confidence threshold adjustment.
        
        Limited to MAX_CONFIDENCE_ADJUSTMENT per change.
        """
        # Check bounds
        adjustment = abs(proposed_threshold - current_threshold)
        if adjustment > self.MAX_CONFIDENCE_ADJUSTMENT:
            self.log_event("proposal_rejected", {
                "reason": f"Adjustment too large ({adjustment}% > {self.MAX_CONFIDENCE_ADJUSTMENT}%)"
            })
            return None
        
        # Check evidence
        if supporting_trades < self.MIN_EVIDENCE_TRADES:
            self.log_event("proposal_rejected", {
                "reason": f"Insufficient evidence ({supporting_trades} < {self.MIN_EVIDENCE_TRADES} trades)"
            })
            return None
        
        proposal_id = f"CONF-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        proposal = AdaptationProposal(
            proposal_id=proposal_id,
            adaptation_type=AdaptationType.CONFIDENCE_THRESHOLD,
            description=f"Adjust {strategy} confidence threshold from {current_threshold}% to {proposed_threshold}%",
            target=strategy,
            current_value=current_threshold,
            proposed_value=proposed_threshold,
            reason=reason,
            evidence_trades=supporting_trades,
            risk_level=RiskLevel.LOW,
        )
        
        self.proposals[proposal_id] = proposal
        self.log_event("proposal_created", proposal.to_dict())
        
        return proposal
    
    def propose_strategy_reranking(
        self,
        regime: str,
        current_ranking: Dict[str, int],
        proposed_ranking: Dict[str, int],
        reason: str,
        performance_data: dict
    ) -> Optional[AdaptationProposal]:
        """
        Propose re-ranking of strategies for a regime.
        """
        proposal_id = f"RANK-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        proposal = AdaptationProposal(
            proposal_id=proposal_id,
            adaptation_type=AdaptationType.STRATEGY_RANKING,
            description=f"Re-rank strategies for {regime} regime",
            target=regime,
            current_value=current_ranking,
            proposed_value=proposed_ranking,
            reason=reason,
            supporting_data=performance_data,
            risk_level=RiskLevel.MEDIUM,
        )
        
        self.proposals[proposal_id] = proposal
        self.log_event("proposal_created", proposal.to_dict())
        
        return proposal
    
    def propose_weight_adjustment(
        self,
        category: str,
        current_weight: float,
        proposed_weight: float,
        reason: str,
        evidence_data: dict
    ) -> Optional[AdaptationProposal]:
        """
        Propose a weighting adjustment.
        
        Limited to MAX_WEIGHT_ADJUSTMENT per change.
        """
        adjustment = abs(proposed_weight - current_weight)
        if adjustment > self.MAX_WEIGHT_ADJUSTMENT:
            self.log_event("proposal_rejected", {
                "reason": f"Weight adjustment too large ({adjustment} > {self.MAX_WEIGHT_ADJUSTMENT})"
            })
            return None
        
        proposal_id = f"WGHT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        proposal = AdaptationProposal(
            proposal_id=proposal_id,
            adaptation_type=AdaptationType.WEIGHT_ADJUSTMENT,
            description=f"Adjust {category} weight from {current_weight} to {proposed_weight}",
            target=category,
            current_value=current_weight,
            proposed_value=proposed_weight,
            reason=reason,
            supporting_data=evidence_data,
            risk_level=RiskLevel.MEDIUM,
        )
        
        self.proposals[proposal_id] = proposal
        self.log_event("proposal_created", proposal.to_dict())
        
        return proposal
    
    def propose_parameter_change(
        self,
        strategy: str,
        parameter: str,
        current_value: Any,
        proposed_value: Any,
        reason: str,
        backtest_results: dict
    ) -> Optional[AdaptationProposal]:
        """
        Propose a parameter change.
        
        HIGH risk - requires full testing.
        """
        proposal_id = f"PARAM-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        proposal = AdaptationProposal(
            proposal_id=proposal_id,
            adaptation_type=AdaptationType.PARAMETER_SUGGESTION,
            description=f"Change {strategy}.{parameter} from {current_value} to {proposed_value}",
            target=f"{strategy}.{parameter}",
            current_value=current_value,
            proposed_value=proposed_value,
            reason=reason,
            supporting_data=backtest_results,
            risk_level=RiskLevel.HIGH,
        )
        
        self.proposals[proposal_id] = proposal
        self.log_event("proposal_created", proposal.to_dict())
        
        return proposal
    
    def propose_strategy_retirement(
        self,
        strategy: str,
        reason: str,
        performance_data: dict
    ) -> Optional[AdaptationProposal]:
        """
        Propose retiring a dead strategy.
        """
        proposal_id = f"RETIRE-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        proposal = AdaptationProposal(
            proposal_id=proposal_id,
            adaptation_type=AdaptationType.STRATEGY_RETIREMENT,
            description=f"Retire strategy {strategy}",
            target=strategy,
            current_value="active",
            proposed_value="retired",
            reason=reason,
            supporting_data=performance_data,
            risk_level=RiskLevel.HIGH,
        )
        
        self.proposals[proposal_id] = proposal
        self.log_event("proposal_created", proposal.to_dict())
        
        return proposal
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TESTING PIPELINE
    # ═══════════════════════════════════════════════════════════════════════════
    
    def submit_for_testing(self, proposal_id: str) -> bool:
        """Submit a proposal for offline testing."""
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        proposal.status = AdaptationStatus.TESTING
        
        self.log_event("testing_started", {"proposal_id": proposal_id})
        
        return True
    
    def record_test_results(
        self,
        proposal_id: str,
        test_results: dict,
        passed: bool
    ):
        """Record test results for a proposal."""
        if proposal_id not in self.proposals:
            return
        
        proposal = self.proposals[proposal_id]
        proposal.test_results = test_results
        
        if passed:
            proposal.status = AdaptationStatus.VALIDATED
        else:
            proposal.status = AdaptationStatus.REJECTED
            proposal.rejection_reason = "Failed testing"
        
        self.log_event("testing_completed", {
            "proposal_id": proposal_id,
            "passed": passed,
            "results": test_results,
        })
    
    def generate_validation_report(self, proposal_id: str) -> str:
        """Generate a validation report for a proposal."""
        if proposal_id not in self.proposals:
            return "Proposal not found"
        
        proposal = self.proposals[proposal_id]
        
        report = f"""
VALIDATION REPORT
═════════════════════════════════════════════════════════

Proposal ID: {proposal.proposal_id}
Type: {proposal.adaptation_type.value}
Risk Level: {proposal.risk_level.value}

CHANGE DESCRIPTION:
{proposal.description}

TARGET: {proposal.target}
Current Value: {proposal.current_value}
Proposed Value: {proposal.proposed_value}

REASON:
{proposal.reason}

SUPPORTING DATA:
{json.dumps(proposal.supporting_data, indent=2)}

TEST RESULTS:
{json.dumps(proposal.test_results, indent=2) if proposal.test_results else "Not tested"}

STATUS: {proposal.status.value}
{"PASSED - Ready for governance approval" if proposal.status == AdaptationStatus.VALIDATED else ""}
{"FAILED - " + (proposal.rejection_reason or "See test results") if proposal.status == AdaptationStatus.REJECTED else ""}

═════════════════════════════════════════════════════════
"""
        proposal.validation_report = report
        return report
    
    # ═══════════════════════════════════════════════════════════════════════════
    # GOVERNANCE APPROVAL
    # ═══════════════════════════════════════════════════════════════════════════
    
    def request_governance_approval(self, proposal_id: str) -> bool:
        """Request governance approval for a validated proposal."""
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        
        if proposal.status != AdaptationStatus.VALIDATED:
            self.log_event("approval_request_rejected", {
                "proposal_id": proposal_id,
                "reason": f"Proposal not validated (status: {proposal.status.value})"
            })
            return False
        
        self.log_event("approval_requested", {"proposal_id": proposal_id})
        
        # Would integrate with Arbiter here
        return True
    
    def approve_proposal(
        self,
        proposal_id: str,
        approver: str,
        version_tag: str
    ) -> bool:
        """Governance approval of a proposal."""
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        
        if proposal.status != AdaptationStatus.VALIDATED:
            return False
        
        proposal.status = AdaptationStatus.APPROVED
        proposal.approved_by = approver
        proposal.approved_at = datetime.utcnow()
        proposal.version_tag = version_tag
        
        self.log_event("proposal_approved", {
            "proposal_id": proposal_id,
            "approver": approver,
            "version_tag": version_tag,
        })
        
        return True
    
    def reject_proposal(
        self,
        proposal_id: str,
        rejector: str,
        reason: str
    ) -> bool:
        """Governance rejection of a proposal."""
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        proposal.status = AdaptationStatus.REJECTED
        proposal.rejection_reason = reason
        
        self.log_event("proposal_rejected", {
            "proposal_id": proposal_id,
            "rejector": rejector,
            "reason": reason,
        })
        
        return True
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DEPLOYMENT
    # ═══════════════════════════════════════════════════════════════════════════
    
    def deploy_adaptation(self, proposal_id: str) -> bool:
        """Deploy an approved adaptation."""
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        
        if proposal.status != AdaptationStatus.APPROVED:
            self.log_event("deployment_rejected", {
                "proposal_id": proposal_id,
                "reason": f"Not approved (status: {proposal.status.value})"
            })
            return False
        
        # Apply the change based on type
        if proposal.adaptation_type == AdaptationType.CONFIDENCE_THRESHOLD:
            self.confidence_thresholds[proposal.target] = proposal.proposed_value
        
        elif proposal.adaptation_type == AdaptationType.STRATEGY_RANKING:
            self.strategy_rankings[proposal.target] = proposal.proposed_value
        
        elif proposal.adaptation_type == AdaptationType.WEIGHT_ADJUSTMENT:
            self.weights[proposal.target] = proposal.proposed_value
        
        proposal.status = AdaptationStatus.DEPLOYED
        proposal.deployed_at = datetime.utcnow()
        
        self.deployed_adaptations.append(proposal)
        
        self.log_event("adaptation_deployed", {
            "proposal_id": proposal_id,
            "version_tag": proposal.version_tag,
        })
        
        return True
    
    def rollback_adaptation(self, proposal_id: str, reason: str) -> bool:
        """Rollback a deployed adaptation."""
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        
        if proposal.status != AdaptationStatus.DEPLOYED:
            return False
        
        # Restore previous value
        if proposal.adaptation_type == AdaptationType.CONFIDENCE_THRESHOLD:
            self.confidence_thresholds[proposal.target] = proposal.current_value
        
        elif proposal.adaptation_type == AdaptationType.STRATEGY_RANKING:
            self.strategy_rankings[proposal.target] = proposal.current_value
        
        elif proposal.adaptation_type == AdaptationType.WEIGHT_ADJUSTMENT:
            self.weights[proposal.target] = proposal.current_value
        
        proposal.status = AdaptationStatus.ROLLED_BACK
        
        self.log_event("adaptation_rolled_back", {
            "proposal_id": proposal_id,
            "reason": reason,
        })
        
        return True
    
    # ═══════════════════════════════════════════════════════════════════════════
    # AUTOMATIC ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def analyze_for_adaptations(
        self,
        performance_data: Dict[str, dict],
        min_trades: int = 50
    ) -> List[AdaptationProposal]:
        """
        Analyze performance data and generate adaptation proposals.
        
        Does NOT auto-deploy - all proposals go through governance.
        """
        proposals = []
        
        for strategy, data in performance_data.items():
            trades = data.get("total_trades", 0)
            win_rate = data.get("win_rate", 0)
            profit_factor = data.get("profit_factor", 1.0)
            current_threshold = data.get("confidence_threshold", 70)
            
            if trades < min_trades:
                continue
            
            # Check for dead strategy
            if profit_factor < 0.8 and trades >= 100:
                proposal = self.propose_strategy_retirement(
                    strategy=strategy,
                    reason=f"Profit factor {profit_factor:.2f} below 0.8 over {trades} trades",
                    performance_data=data,
                )
                if proposal:
                    proposals.append(proposal)
            
            # Check for confidence threshold adjustment
            elif profit_factor > 1.5 and win_rate > 55:
                # Strategy performing well - could lower threshold slightly
                new_threshold = max(current_threshold - 3, 60)
                if new_threshold != current_threshold:
                    proposal = self.propose_confidence_adjustment(
                        strategy=strategy,
                        current_threshold=current_threshold,
                        proposed_threshold=new_threshold,
                        reason=f"Strong performance (PF {profit_factor:.2f}, WR {win_rate:.0f}%)",
                        supporting_trades=trades,
                    )
                    if proposal:
                        proposals.append(proposal)
            
            elif profit_factor < 1.2 and win_rate < 50:
                # Strategy struggling - could raise threshold
                new_threshold = min(current_threshold + 3, 85)
                if new_threshold != current_threshold:
                    proposal = self.propose_confidence_adjustment(
                        strategy=strategy,
                        current_threshold=current_threshold,
                        proposed_threshold=new_threshold,
                        reason=f"Weak performance (PF {profit_factor:.2f}, WR {win_rate:.0f}%)",
                        supporting_trades=trades,
                    )
                    if proposal:
                        proposals.append(proposal)
        
        return proposals
    
    def get_status(self) -> dict:
        """Get adaptive learning system status."""
        return {
            "total_proposals": len(self.proposals),
            "proposals_by_status": {
                status.value: len([p for p in self.proposals.values() if p.status == status])
                for status in AdaptationStatus
            },
            "deployed_adaptations": len(self.deployed_adaptations),
            "forbidden_attempts_blocked": len(self.forbidden_attempts),
            "current_thresholds": self.confidence_thresholds,
            "current_weights": self.weights,
            "pending_approval": [
                p.to_dict() for p in self.proposals.values() 
                if p.status == AdaptationStatus.VALIDATED
            ],
        }
