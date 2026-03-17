#!/usr/bin/env python3
"""
Forex Trading Platform - Agent Documentation Generator
Generates a comprehensive PDF documenting all 15 agents
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, ListFlowable, ListItem, Preformatted
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from datetime import datetime
import json

# ═══════════════════════════════════════════════════════════════
# AGENT DEFINITIONS
# ═══════════════════════════════════════════════════════════════

AGENTS = [
    {
        "name": "Curator",
        "role": "Market Data Agent",
        "port": 3021,
        "emoji": "📡",
        "version": "1.0",
        "description": """The foundational data layer of the trading platform. Curator is responsible for 
ingesting, validating, and distributing all market data from MT5. Every other agent depends on Curator 
for clean, quality-scored data. It acts as the single source of truth for prices, candles, spreads, 
and account information.""",
        "use_cases": [
            "Fetch real-time price data for any symbol",
            "Get historical candles (M1 to D1 timeframes)",
            "Monitor data quality and freshness",
            "Detect trading session (Sydney, Tokyo, London, NY)",
            "Track spread conditions and volatility",
            "Provide account balance and equity information"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health and data quality summary"),
            ("GET /api/quality/{symbol}", "Data quality score for a symbol (0-100)"),
            ("GET /api/candles/{symbol}/{timeframe}", "Historical candle data"),
            ("GET /api/snapshot/price/{symbol}", "Current price snapshot"),
            ("GET /api/snapshot/spread/{symbol}", "Current spread in pips"),
            ("GET /api/account", "Account balance, equity, margin"),
            ("GET /api/positions", "Open positions from MT5"),
            ("POST /api/refresh", "Force data refresh from MT5"),
        ],
        "sample_output": {
            "endpoint": "/api/quality/EURUSD",
            "response": {
                "symbol": "EURUSD",
                "overall": 85,
                "freshness": 95,
                "completeness": 90,
                "spread_quality": 80,
                "volatility_normal": True,
                "tradeable": True,
                "last_update": "2026-03-12T18:00:00Z"
            }
        },
        "orchestrator_integration": """Curator feeds data to ALL agents. The Orchestrator queries Curator 
during the Market Open Prep workflow to refresh data, and during Intraday Scans to check data quality. 
If quality drops below 70%, trading is paused via the Incident Response workflow.""",
        "data_to_orchestrator": {
            "quality_score": "0-100 score indicating data reliability",
            "tradeable": "Boolean - whether symbol has sufficient data quality",
            "session": "Current trading session (sydney/tokyo/london/newyork)",
            "spread_pips": "Current spread for execution feasibility checks"
        }
    },
    {
        "name": "Sentinel",
        "role": "News & Event Risk Agent",
        "port": 3010,
        "emoji": "📰",
        "version": "2.0",
        "description": """The event risk watchdog. Sentinel monitors economic calendars, central bank 
schedules, and news feeds to identify periods when trading should be paused or reduced. It maintains 
blocked windows around high-impact events and provides risk assessments for each symbol.""",
        "use_cases": [
            "Track upcoming economic events (NFP, CPI, rate decisions)",
            "Identify blocked trading windows around events",
            "Calculate event risk scores per symbol",
            "Determine trading mode (NORMAL, REDUCED, PAUSE)",
            "Alert on breaking news affecting currencies",
            "Filter symbols by event exposure"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health and global risk level"),
            ("GET /api/events", "Upcoming economic events"),
            ("GET /api/blocked", "Currently blocked trading windows"),
            ("GET /api/risk/{symbol}", "Event risk assessment for symbol"),
            ("GET /api/trading_mode", "Current recommended trading mode"),
        ],
        "sample_output": {
            "endpoint": "/api/risk/EURUSD",
            "response": {
                "symbol": "EURUSD",
                "risk_level": "high",
                "in_blocked_window": False,
                "next_event": {
                    "name": "US Core CPI",
                    "time": "2026-03-12T19:30:00Z",
                    "impact": "high",
                    "minutes_until": 45
                },
                "trading_mode": "REDUCED",
                "affected_currencies": ["USD"],
                "recommendation": "Reduce position size or wait"
            }
        },
        "orchestrator_integration": """Sentinel is consulted during Pre-Trade Approval (Step 5) to check 
if the symbol is in a blocked window. It has VETO POWER - if a trade is attempted during a blocked 
window, it will be rejected. The Incident Response workflow also monitors Sentinel for extreme risk.""",
        "data_to_orchestrator": {
            "in_blocked_window": "Boolean - hard veto if True",
            "risk_level": "low/medium/high/extreme",
            "trading_mode": "NORMAL/REDUCED/PAUSE",
            "upcoming_events": "List of events affecting the symbol"
        }
    },
    {
        "name": "Oracle",
        "role": "Macro & Fundamental Agent",
        "port": 3011,
        "emoji": "🏛️",
        "version": "2.0",
        "description": """The fundamental analyst. Oracle tracks macroeconomic conditions for each major 
currency, analyzing interest rates, inflation, growth, and employment. It provides pair-relative analysis 
comparing base vs quote currency strength to determine macro bias.""",
        "use_cases": [
            "Analyze currency fundamentals (USD, EUR, GBP, JPY, etc.)",
            "Compare base vs quote currency strength",
            "Identify carry trade opportunities",
            "Track central bank policy divergence",
            "Assess rate differential trends",
            "Generate macro bias for each pair"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health and currencies tracked"),
            ("GET /api/outlook/{symbol}", "Macro outlook for a pair"),
            ("GET /api/currency/{code}", "Fundamental profile for a currency"),
            ("GET /api/carry", "Carry trade opportunities"),
            ("GET /api/divergence", "Policy divergence analysis"),
        ],
        "sample_output": {
            "endpoint": "/api/outlook/EURUSD",
            "response": {
                "symbol": "EURUSD",
                "bias": "bearish",
                "confidence": 72,
                "base_currency": {
                    "code": "EUR",
                    "strength_score": 45,
                    "rate": 4.50,
                    "inflation": 2.8,
                    "growth": 0.5
                },
                "quote_currency": {
                    "code": "USD",
                    "strength_score": 68,
                    "rate": 5.50,
                    "inflation": 3.2,
                    "growth": 2.1
                },
                "rate_differential": -1.0,
                "carry_direction": "short",
                "key_factors": [
                    "USD rate advantage",
                    "Stronger US growth",
                    "ECB dovish pivot expected"
                ]
            }
        },
        "orchestrator_integration": """Oracle is consulted during Pre-Trade Approval (Step 3) to check 
macro alignment. While it doesn't have veto power, a strongly opposing macro bias will reduce the 
confluence score. The Weekly Review uses Oracle data to analyze performance by macro conditions.""",
        "data_to_orchestrator": {
            "bias": "bullish/bearish/neutral for the pair",
            "confidence": "0-100 confidence in the bias",
            "key_factors": "List of supporting fundamental factors",
            "rate_differential": "Interest rate difference (base - quote)"
        }
    },
    {
        "name": "Atlas Jr.",
        "role": "Technical Analysis Agent",
        "port": 3012,
        "emoji": "📊",
        "version": "2.0",
        "description": """The chart reader. Atlas Jr. performs comprehensive technical analysis using 
a suite of 20+ indicators, multi-timeframe alignment, and trend grading. It identifies trend direction, 
momentum conditions, and provides evidence-based technical assessments.""",
        "use_cases": [
            "Analyze trend direction and strength",
            "Grade trend quality (A-F scale)",
            "Detect momentum divergences",
            "Identify overbought/oversold conditions",
            "Check multi-timeframe alignment",
            "Provide invalidation levels"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health and symbols analyzed"),
            ("GET /api/analysis/{symbol}", "Full technical analysis"),
            ("GET /api/trend/{symbol}", "Trend assessment only"),
            ("GET /api/momentum/{symbol}", "Momentum indicators"),
            ("GET /api/mtf/{symbol}", "Multi-timeframe alignment"),
        ],
        "sample_output": {
            "endpoint": "/api/analysis/EURUSD",
            "response": {
                "symbol": "EURUSD",
                "trend_direction": "bearish",
                "trend_grade": "B",
                "momentum": "neutral",
                "rsi": 42,
                "macd_signal": "bearish",
                "ema_alignment": "bearish",
                "mtf_alignment": {
                    "D1": "bearish",
                    "H4": "bearish",
                    "H1": "neutral",
                    "M30": "bullish"
                },
                "supporting_evidence": [
                    "Price below 50 EMA",
                    "Lower highs forming",
                    "MACD histogram negative"
                ],
                "contradicting_evidence": [
                    "RSI showing bullish divergence",
                    "M30 showing short-term bounce"
                ],
                "invalidation_level": 1.0975
            }
        },
        "orchestrator_integration": """Atlas Jr. is consulted during Pre-Trade Approval (Step 1) to check 
technical alignment. If the trend contradicts the trade direction, it counts as a veto. The confluence 
score weights technical analysis at 25% - the highest single weight.""",
        "data_to_orchestrator": {
            "trend_direction": "bullish/bearish/neutral",
            "trend_grade": "A-F quality grade",
            "supporting_evidence": "List of confirming signals",
            "contradicting_evidence": "List of warning signals",
            "invalidation_level": "Price level that would invalidate the trade"
        }
    },
    {
        "name": "Architect",
        "role": "Price Structure Agent",
        "port": 3014,
        "emoji": "🏗️",
        "version": "2.0",
        "description": """The structure mapper. Architect analyzes price structure including support/resistance 
zones, swing highs and lows, liquidity pools, and fair value gaps. It provides a structural roadmap for 
where price is likely to react.""",
        "use_cases": [
            "Identify key support/resistance levels",
            "Label swing highs and lows (HH, HL, LH, LL)",
            "Detect liquidity sweeps",
            "Find fair value gaps (FVGs)",
            "Assess zone freshness (fresh, tested, broken)",
            "Map potential reversal zones"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health"),
            ("GET /api/structure/{symbol}", "Full structure analysis"),
            ("GET /api/levels/{symbol}", "Key price levels"),
            ("GET /api/swings/{symbol}", "Swing high/low labels"),
            ("GET /api/liquidity/{symbol}", "Liquidity pool locations"),
        ],
        "sample_output": {
            "endpoint": "/api/structure/EURUSD",
            "response": {
                "symbol": "EURUSD",
                "structure": "bearish",
                "swing_sequence": ["HH", "HL", "LH", "LL"],
                "key_levels": [
                    {"price": 1.0950, "type": "resistance", "strength": "strong", "freshness": "tested"},
                    {"price": 1.0880, "type": "support", "strength": "moderate", "freshness": "fresh"},
                    {"price": 1.0820, "type": "support", "strength": "strong", "freshness": "fresh"}
                ],
                "liquidity_pools": [
                    {"price": 1.0960, "type": "buy_stops", "size": "large"},
                    {"price": 1.0800, "type": "sell_stops", "size": "medium"}
                ],
                "fair_value_gaps": [
                    {"high": 1.0920, "low": 1.0905, "filled": False}
                ],
                "nearest_resistance": 1.0950,
                "nearest_support": 1.0880
            }
        },
        "orchestrator_integration": """Architect is consulted during Pre-Trade Approval (Step 2) to verify 
entry is near a key level. The confluence score weights structure at 20%. Structure data is also used 
by Tactician to generate stop loss and target levels.""",
        "data_to_orchestrator": {
            "structure": "Overall market structure (bullish/bearish/ranging)",
            "key_levels": "Important price levels for entries and exits",
            "nearest_support": "Closest support level",
            "nearest_resistance": "Closest resistance level"
        }
    },
    {
        "name": "Pulse",
        "role": "Sentiment Agent",
        "port": 3015,
        "emoji": "💓",
        "version": "2.0",
        "description": """The crowd watcher. Pulse monitors retail positioning, commitment of traders (COT) 
data, and market sentiment to identify overcrowding, contrarian opportunities, and potential reversals. 
It's designed to warn when everyone is on the same side of a trade.""",
        "use_cases": [
            "Track retail positioning ratios",
            "Identify overcrowded trades",
            "Spot contrarian opportunities",
            "Detect sentiment extremes",
            "Monitor COT positioning",
            "Assess reversal risk from sentiment"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health and sentiment overview"),
            ("GET /api/sentiment/{symbol}", "Sentiment analysis for symbol"),
            ("GET /api/positioning", "Retail positioning data"),
            ("GET /api/extremes", "Sentiment extremes alert"),
        ],
        "sample_output": {
            "endpoint": "/api/sentiment/EURUSD",
            "response": {
                "symbol": "EURUSD",
                "classification": "overcrowded",
                "retail_long_pct": 78,
                "retail_short_pct": 22,
                "crowding_score": 85,
                "contrarian_score": 15,
                "reversal_risk": "high",
                "recommendation": "Fade retail - consider short",
                "cot_positioning": {
                    "commercials": "net_short",
                    "large_specs": "net_long",
                    "small_specs": "extremely_long"
                },
                "warning": "Extreme retail long positioning - reversal risk elevated"
            }
        },
        "orchestrator_integration": """Pulse is consulted during Pre-Trade Approval (Step 4). If sentiment 
shows 'overcrowded' in the same direction as the trade, it triggers a warning and may reduce position size. 
Sentiment has a 10% weight in confluence scoring - the lowest weight, as it's a secondary indicator.""",
        "data_to_orchestrator": {
            "classification": "trend_supportive/overcrowded/contrarian_opportunity/neutral_no_edge",
            "crowding_score": "0-100 how crowded the trade is",
            "reversal_risk": "low/medium/high risk of sentiment-driven reversal",
            "warning": "Any sentiment-based warnings"
        }
    },
    {
        "name": "Compass",
        "role": "Regime Classification Agent",
        "port": 3016,
        "emoji": "🧭",
        "version": "2.0",
        "description": """The regime detector. Compass classifies current market conditions into one of 
8 regime types, determining which strategies are appropriate. It prevents trend strategies in ranging 
markets and range strategies in trending markets.""",
        "use_cases": [
            "Classify market regime (trending, ranging, volatile, etc.)",
            "Determine which strategy families are valid",
            "Track regime transitions",
            "Calculate regime confidence",
            "Suggest risk multipliers based on regime",
            "Filter symbols by tradeable regimes"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health and regime summary"),
            ("GET /api/regime/{symbol}", "Regime classification"),
            ("GET /api/history/{symbol}", "Regime history"),
            ("GET /api/transitions", "Recent regime changes"),
        ],
        "sample_output": {
            "endpoint": "/api/regime/EURUSD",
            "response": {
                "symbol": "EURUSD",
                "regime": "trending_down",
                "confidence": 78,
                "tradeable": True,
                "valid_strategies": [
                    "trend_continuation",
                    "pullback_in_trend",
                    "breakout"
                ],
                "invalid_strategies": [
                    "range_fade",
                    "mean_reversion"
                ],
                "risk_multiplier": 1.0,
                "volatility": "normal",
                "trend_strength": "moderate",
                "regime_age_bars": 45,
                "transition_probability": {
                    "continue": 0.65,
                    "weaken": 0.25,
                    "reverse": 0.10
                }
            }
        },
        "orchestrator_integration": """Compass is consulted during Pre-Trade Approval to verify strategy-regime 
match. If a pullback strategy is attempted in a ranging market, it will fail the regime gate. Regime has 
a 15% weight in confluence scoring.""",
        "data_to_orchestrator": {
            "regime": "One of 8 regime types",
            "tradeable": "Boolean - some regimes are untradeable (choppy)",
            "valid_strategies": "Strategy families allowed in this regime",
            "risk_multiplier": "0.5-1.5 based on regime conditions"
        }
    },
    {
        "name": "Tactician",
        "role": "Strategy Agent",
        "port": 3017,
        "emoji": "♟️",
        "version": "3.0",
        "description": """The playbook keeper. Tactician maintains 8 strategy templates and matches current 
market conditions to appropriate setups. It generates complete trade plans including entry, stop loss, 
and multiple take profit targets.""",
        "use_cases": [
            "Match market conditions to strategy templates",
            "Generate trade setups with entry/stop/targets",
            "Score setup quality",
            "Validate strategy-regime compatibility",
            "Calculate risk/reward ratios",
            "Provide exit frameworks"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health and active strategies"),
            ("GET /api/setups/{symbol}", "Available setups for symbol"),
            ("GET /api/templates", "All strategy templates"),
            ("GET /api/validate", "Validate a proposed setup"),
        ],
        "sample_output": {
            "endpoint": "/api/setups/EURUSD",
            "response": {
                "symbol": "EURUSD",
                "setups": [
                    {
                        "template": "PULLBACK_IN_TREND",
                        "direction": "short",
                        "score": 82,
                        "entry": 1.0935,
                        "stop": 1.0965,
                        "targets": [1.0880, 1.0850, 1.0800],
                        "risk_reward": "2.5:1",
                        "regime_match": True,
                        "confluence_factors": [
                            "Pullback to 50 EMA",
                            "Previous support now resistance",
                            "Bearish regime confirmed"
                        ],
                        "invalidation": "Break above 1.0975",
                        "exit_framework": "partial_tp_runner"
                    }
                ],
                "rejected_setups": [
                    {
                        "template": "RANGE_FADE",
                        "reason": "Invalid in trending regime"
                    }
                ]
            }
        },
        "orchestrator_integration": """Tactician generates the initial trade ideas during Market Open Prep 
and Intraday Scans. Its setups are then passed through all other agents for validation. Tactician also 
provides the exit framework used by Position Management.""",
        "data_to_orchestrator": {
            "setups": "List of valid trade setups",
            "template": "Which of 8 strategy templates applies",
            "entry/stop/targets": "Complete trade plan",
            "exit_framework": "How the position will be managed"
        }
    },
    {
        "name": "Guardian",
        "role": "Risk Management Agent",
        "port": 3013,
        "emoji": "🛡️",
        "version": "2.0",
        "description": """The risk enforcer. Guardian has ABSOLUTE VETO POWER over all trades. It calculates 
position sizes, enforces drawdown limits, detects revenge trading, and can halt all trading system-wide. 
No trade can execute without Guardian's approval.""",
        "use_cases": [
            "Calculate position sizes based on risk parameters",
            "Enforce daily/weekly/total drawdown limits",
            "Detect revenge trading patterns",
            "Manage risk modes (NORMAL, REDUCED, DEFENSIVE, HALTED)",
            "Veto trades that violate risk rules",
            "Activate kill switch in emergencies"
        ],
        "key_endpoints": [
            ("GET /api/status", "Risk state and kill switch status"),
            ("POST /api/approve", "Approve or reject a trade"),
            ("POST /api/position_size", "Calculate position size"),
            ("POST /api/halt", "Activate kill switch"),
            ("POST /api/resume", "Deactivate kill switch"),
        ],
        "sample_output": {
            "endpoint": "POST /api/approve",
            "request": {
                "symbol": "EURUSD",
                "direction": "short",
                "entry": 1.0935,
                "stop_loss": 1.0965,
                "position_size": 0.5
            },
            "response": {
                "approved": True,
                "risk_mode": "NORMAL",
                "recommended_size": 0.42,
                "risk_percent": 0.25,
                "risk_amount": 25.0,
                "daily_risk_remaining": 1.75,
                "warnings": [],
                "checks_passed": [
                    "Daily drawdown OK",
                    "Weekly drawdown OK",
                    "Position size within limits",
                    "No revenge trading detected"
                ]
            }
        },
        "orchestrator_integration": """Guardian is consulted during Pre-Trade Approval (Step 7) with 
ABSOLUTE VETO POWER. If Guardian rejects, the trade is blocked regardless of other scores. Guardian 
also monitors all positions and can trigger the kill switch via Incident Response.""",
        "data_to_orchestrator": {
            "approved": "Boolean - ABSOLUTE VETO if False",
            "recommended_size": "Position size that meets risk rules",
            "risk_mode": "Current risk mode (NORMAL/REDUCED/DEFENSIVE/HALTED)",
            "block_reasons": "Why trade was rejected (if applicable)"
        }
    },
    {
        "name": "Balancer",
        "role": "Portfolio Agent",
        "port": 3018,
        "emoji": "⚖️",
        "version": "2.0",
        "description": """The exposure watchdog. Balancer tracks currency-level exposure across all positions, 
not just pairs. It detects when multiple 'different' trades are actually the same bet (e.g., long EURUSD 
+ long GBPUSD = short USD) and prevents concentration risk.""",
        "use_cases": [
            "Track currency-level exposure",
            "Calculate portfolio correlation",
            "Detect hidden concentration risk",
            "Recommend position reductions",
            "Identify hedging opportunities",
            "Score overall portfolio exposure"
        ],
        "key_endpoints": [
            ("GET /api/status", "Portfolio summary"),
            ("GET /api/exposure", "Currency exposure breakdown"),
            ("GET /api/correlation", "Position correlations"),
            ("GET /api/recommendations", "Position adjustments"),
        ],
        "sample_output": {
            "endpoint": "/api/exposure",
            "response": {
                "position_count": 3,
                "exposure_score": 65,
                "by_currency": {
                    "EUR": -0.45,
                    "USD": 1.35,
                    "GBP": -0.30,
                    "JPY": -0.60
                },
                "by_theme": {
                    "dollar_long": 1.35,
                    "risk_off": 0.0,
                    "carry": 0.0
                },
                "concentration_warning": "USD exposure at 1.35 lots - exceeds 1.0 threshold",
                "correlated_clusters": [
                    {
                        "positions": ["EURUSD short", "GBPUSD short"],
                        "correlation": 0.85,
                        "effective_exposure": "1.35x USD long"
                    }
                ],
                "recommendations": [
                    "Reduce USD long exposure by 0.35 lots",
                    "Consider closing one of the correlated positions"
                ]
            }
        },
        "orchestrator_integration": """Balancer is consulted during Pre-Trade Approval (Step 6) to check 
if adding this position would create excessive exposure. An exposure_score > 80 can veto new trades in 
the same direction.""",
        "data_to_orchestrator": {
            "exposure_score": "0-100 overall exposure level",
            "by_currency": "Exposure per currency in lots",
            "concentration_warning": "Alert if any currency is over-exposed",
            "recommendations": "Suggested adjustments"
        }
    },
    {
        "name": "Executor",
        "role": "Execution Agent",
        "port": 3019,
        "emoji": "⚡",
        "version": "2.0",
        "description": """The order handler. Executor manages all communication with MT5 for order execution, 
modification, and closure. It operates in PAPER mode by default for safety, with strict validation to 
prevent dangerous operations like martingale or averaging down.""",
        "use_cases": [
            "Execute trades in paper/shadow/live modes",
            "Validate orders before submission",
            "Check execution feasibility (spread, slippage)",
            "Modify open positions (stop loss, take profit)",
            "Close positions (partial or full)",
            "Monitor MT5 bridge connectivity"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent and bridge status"),
            ("GET /api/bridge", "MT5 bridge connectivity"),
            ("POST /api/execute", "Execute a trade"),
            ("POST /api/modify", "Modify position"),
            ("POST /api/close", "Close position"),
            ("POST /api/close_all", "Emergency close all"),
            ("POST /api/feasibility", "Check if execution is feasible"),
        ],
        "sample_output": {
            "endpoint": "POST /api/execute",
            "request": {
                "symbol": "EURUSD",
                "side": "sell",
                "volume": 0.42,
                "entry_price": 1.0935,
                "stop_loss": 1.0965,
                "take_profits": [1.0880, 1.0850],
                "mode": "paper"
            },
            "response": {
                "status": "filled",
                "mode": "paper",
                "ticket": "PAPER-20260312-001",
                "symbol": "EURUSD",
                "side": "sell",
                "volume": 0.42,
                "fill_price": 1.0935,
                "stop_loss": 1.0965,
                "take_profit": 1.0880,
                "slippage_pips": 0.0,
                "spread_at_execution": 0.8,
                "timestamp": "2026-03-12T18:15:00Z"
            }
        },
        "orchestrator_integration": """Executor is the final step in Trade Execution workflow. It validates 
orders, checks Guardian approval, and submits to MT5. During Pre-Trade Approval (Step 8), it checks 
execution feasibility. During Incident Response, it can close all positions.""",
        "data_to_orchestrator": {
            "status": "filled/pending/rejected",
            "ticket": "Position identifier for tracking",
            "fill_price": "Actual execution price",
            "feasible": "Boolean - can this trade be executed now"
        }
    },
    {
        "name": "Nexus",
        "role": "Orchestrator / CIO Agent",
        "port": 3020,
        "emoji": "🎯",
        "version": "2.0",
        "description": """The central command hub. Nexus orchestrates all other agents, calculates weighted 
confluence scores, enforces hard gates, and makes final trade decisions. It manages the 8 operational 
workflows that drive the trading system.""",
        "use_cases": [
            "Coordinate all 14 other agents",
            "Calculate confluence scores (weighted)",
            "Enforce 8 hard gates (fail any = NO_TRADE)",
            "Make final EXECUTE/WATCHLIST/NO_TRADE decisions",
            "Run 8 operational workflows",
            "Track trade lifecycle from idea to exit"
        ],
        "key_endpoints": [
            ("GET /api/status", "System status"),
            ("GET /api/confluence/{symbol}", "Calculate confluence score"),
            ("GET /api/decisions", "Recent trade decisions"),
            ("GET /api/watchlist", "Current watchlist"),
            ("POST /api/workflows/trigger/{name}", "Trigger a workflow"),
            ("GET /api/workflows/status", "Workflow scheduler status"),
        ],
        "sample_output": {
            "endpoint": "/api/confluence/EURUSD?direction=short",
            "response": {
                "symbol": "EURUSD",
                "direction": "short",
                "confluence_score": 78,
                "decision": "EXECUTE",
                "score_breakdown": {
                    "technical": {"score": 85, "weight": 0.25, "contribution": 21.25},
                    "structure": {"score": 80, "weight": 0.20, "contribution": 16.0},
                    "macro": {"score": 72, "weight": 0.15, "contribution": 10.8},
                    "sentiment": {"score": 65, "weight": 0.10, "contribution": 6.5},
                    "regime": {"score": 78, "weight": 0.15, "contribution": 11.7},
                    "risk_execution": {"score": 90, "weight": 0.15, "contribution": 13.5}
                },
                "hard_gates": [
                    {"gate": "event_risk", "passed": True},
                    {"gate": "spread", "passed": True},
                    {"gate": "stop_defined", "passed": True},
                    {"gate": "regime_match", "passed": True},
                    {"gate": "data_quality", "passed": True},
                    {"gate": "portfolio_exposure", "passed": True},
                    {"gate": "guardian_mode", "passed": True},
                    {"gate": "model_version", "passed": True}
                ],
                "all_gates_passed": True,
                "vetoes": []
            }
        },
        "orchestrator_integration": """Nexus IS the orchestrator. All other agents report to it. It consults 
each agent during the Pre-Trade Approval workflow and aggregates their inputs into a final decision using 
weighted confluence scoring and hard gate evaluation.""",
        "data_to_orchestrator": "N/A - Nexus is the orchestrator"
    },
    {
        "name": "Chronicle",
        "role": "Journal Agent",
        "port": 3022,
        "emoji": "📔",
        "version": "1.0",
        "description": """The record keeper. Chronicle maintains a complete journal of all trades from 
proposal through execution and exit. It generates AI-powered after-action reviews and tracks lessons 
learned.""",
        "use_cases": [
            "Log all trade proposals",
            "Record trade executions with full context",
            "Track trade lifecycle (proposed→approved→executed→closed)",
            "Generate after-action reviews",
            "Store lessons and tags",
            "Query historical trades"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health and trade counts"),
            ("GET /api/trades", "Query trade history"),
            ("POST /api/trades", "Log a new trade"),
            ("POST /api/close/{trade_id}", "Record trade closure"),
            ("GET /api/trades/{trade_id}", "Get trade details"),
            ("POST /api/journal", "Add journal entry"),
        ],
        "sample_output": {
            "endpoint": "GET /api/trades/T-20260312-001",
            "response": {
                "trade_id": "T-20260312-001",
                "symbol": "EURUSD",
                "side": "short",
                "status": "closed",
                "entry_price": 1.08498,
                "close_price": 1.0815,
                "stop_loss": 1.0880,
                "take_profit": 1.0815,
                "volume": 0.1,
                "result_r": 1.15,
                "pnl": 34.80,
                "strategy_family": "pullback_in_trend",
                "regime": "trending_down",
                "created_at": "2026-03-12T14:30:00Z",
                "closed_at": "2026-03-12T16:45:00Z",
                "lessons": ["Good entry timing on pullback"],
                "after_action": "Trade executed as planned. Entry on 50 EMA retest, exit at TP1."
            }
        },
        "orchestrator_integration": """Chronicle is called during Trade Execution (Step 4) to log the trade 
receipt, and during Position Management to log modifications. The EOD Review workflow queries Chronicle 
for daily trade summaries.""",
        "data_to_orchestrator": {
            "trade_id": "Unique identifier for tracking",
            "status": "proposed/approved/executed/closed",
            "result_r": "R-multiple result when closed",
            "lessons": "Tagged lessons from the trade"
        }
    },
    {
        "name": "Insight",
        "role": "Analytics Agent",
        "port": 3023,
        "emoji": "📈",
        "version": "1.0",
        "description": """The performance analyst. Insight calculates comprehensive performance metrics 
including expectancy, profit factor, drawdown, and Sharpe ratio. It segments results by symbol, regime, 
strategy, and session to identify edges and weaknesses.""",
        "use_cases": [
            "Calculate expectancy and profit factor",
            "Track drawdown (daily, weekly, max)",
            "Compute risk-adjusted metrics (Sharpe, Sortino)",
            "Segment performance by symbol/regime/strategy",
            "Detect edge decay",
            "Compare expected vs actual performance"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health"),
            ("GET /api/analytics", "Full performance analytics"),
            ("GET /api/metrics", "Core performance metrics"),
            ("GET /api/by_symbol", "Performance by symbol"),
            ("GET /api/by_regime", "Performance by regime"),
            ("GET /api/by_strategy", "Performance by strategy"),
            ("GET /api/edge_status", "Edge decay detection"),
        ],
        "sample_output": {
            "endpoint": "/api/analytics",
            "response": {
                "core_metrics": {
                    "total_trades": 47,
                    "wins": 28,
                    "losses": 19,
                    "win_rate": 59.6,
                    "expectancy": 0.35,
                    "profit_factor": 1.68,
                    "avg_winner": 1.2,
                    "avg_loser": -0.85,
                    "largest_winner": 3.5,
                    "largest_loser": -1.0,
                    "max_drawdown_r": 4.2,
                    "sharpe_ratio": 1.45,
                    "sortino_ratio": 2.1
                },
                "by_regime": {
                    "trending_up": {"trades": 15, "win_rate": 73, "expectancy": 0.55},
                    "trending_down": {"trades": 12, "win_rate": 67, "expectancy": 0.42},
                    "ranging": {"trades": 10, "win_rate": 40, "expectancy": -0.1}
                },
                "edge_status": {
                    "status": "healthy",
                    "recent_expectancy": 0.38,
                    "baseline_expectancy": 0.35,
                    "significance": "within_variance"
                }
            }
        },
        "orchestrator_integration": """Insight is queried during EOD Review (Step 5) for daily metrics 
and during Weekly Review (Steps 1-3) for segmented analysis. It feeds the Adaptive Learning system 
in Arbiter with performance data.""",
        "data_to_orchestrator": {
            "expectancy": "Average R-multiple per trade",
            "edge_status": "healthy/decaying/lost",
            "by_regime/by_strategy": "Segmented performance for weakness detection"
        }
    },
    {
        "name": "Arbiter",
        "role": "Governance Agent",
        "port": 3024,
        "emoji": "⚖️",
        "version": "1.0",
        "description": """The change controller. Arbiter manages strategy versioning, validates proposed 
changes through walk-forward testing, detects overfitting, and maintains promotion gates. No strategy 
modification goes live without Arbiter's validation.""",
        "use_cases": [
            "Track strategy versions (semantic versioning)",
            "Validate proposed changes",
            "Detect overfitting (score 0-100)",
            "Require out-of-sample testing",
            "Enforce walk-forward validation",
            "Manage promotion gates"
        ],
        "key_endpoints": [
            ("GET /api/status", "Agent health and pending requests"),
            ("POST /api/request", "Submit a change request"),
            ("GET /api/requests", "List change requests"),
            ("GET /api/versions/{strategy}", "Version history"),
            ("POST /api/validate", "Validate a change"),
        ],
        "sample_output": {
            "endpoint": "GET /api/requests/CR-20260312-001",
            "response": {
                "request_id": "CR-20260312-001",
                "strategy_name": "PULLBACK_TREND",
                "change_type": "parameter_update",
                "status": "approved",
                "overfit_score": 15,
                "validation_results": {
                    "in_sample": {"pf": 1.8, "win_rate": 58, "expectancy": 0.32},
                    "out_of_sample": {"pf": 1.6, "win_rate": 55, "expectancy": 0.28},
                    "oos_degradation_pct": 12,
                    "walk_forward": {"passed": 5, "failed": 1, "pass_rate": 0.83}
                },
                "version": {
                    "from": "1.0.0",
                    "to": "1.1.0"
                },
                "red_flags": [],
                "approval_timestamp": "2026-03-12T15:30:00Z"
            }
        },
        "orchestrator_integration": """Arbiter is checked during Pre-Trade Approval via the 'model_version' 
hard gate to ensure strategies are using approved versions. The Weekly Review queues validation tasks 
with Arbiter for proposed changes.""",
        "data_to_orchestrator": {
            "approved_version": "Current approved strategy version",
            "pending_requests": "Number of changes awaiting validation",
            "overfit_score": "0-100 (>75 = automatic rejection)"
        }
    },
]

# ═══════════════════════════════════════════════════════════════
# PDF GENERATION
# ═══════════════════════════════════════════════════════════════

def create_styles():
    """Create custom paragraph styles."""
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='Title2',
        parent=styles['Title'],
        fontSize=28,
        spaceAfter=30,
        textColor=colors.HexColor('#1a365d')
    ))
    
    styles.add(ParagraphStyle(
        name='AgentTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.HexColor('#2c5282')
    ))
    
    styles.add(ParagraphStyle(
        name='SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=15,
        spaceAfter=8,
        textColor=colors.HexColor('#2d3748')
    ))
    
    styles.add(ParagraphStyle(
        name='BodyText2',
        parent=styles['BodyText'],
        fontSize=10,
        alignment=TA_JUSTIFY,
        spaceBefore=6,
        spaceAfter=6
    ))
    
    styles.add(ParagraphStyle(
        name='CodeBlock',
        parent=styles['Code'],
        fontSize=8,
        fontName='Courier',
        backColor=colors.HexColor('#f7fafc'),
        borderColor=colors.HexColor('#e2e8f0'),
        borderWidth=1,
        borderPadding=5
    ))
    
    return styles


def create_cover_page(styles):
    """Create the cover page elements."""
    elements = []
    
    elements.append(Spacer(1, 2*inch))
    
    title = Paragraph("Forex Trading Platform", styles['Title2'])
    elements.append(title)
    
    subtitle = Paragraph("Multi-Agent System Documentation", styles['Heading2'])
    elements.append(subtitle)
    
    elements.append(Spacer(1, 0.5*inch))
    
    version = Paragraph(f"<b>Version 1.0</b> — {datetime.now().strftime('%B %d, %Y')}", styles['Normal'])
    elements.append(version)
    
    elements.append(Spacer(1, 1*inch))
    
    # Agent summary table
    summary_data = [["Port", "Agent", "Role", "Version"]]
    for agent in AGENTS:
        summary_data.append([
            str(agent["port"]),
            f"{agent['emoji']} {agent['name']}",
            agent["role"],
            agent["version"]
        ])
    
    summary_table = Table(summary_data, colWidths=[0.6*inch, 1.5*inch, 2.5*inch, 0.7*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
    ]))
    
    elements.append(summary_table)
    elements.append(PageBreak())
    
    return elements


def create_toc(styles):
    """Create table of contents."""
    elements = []
    
    elements.append(Paragraph("Table of Contents", styles['Heading1']))
    elements.append(Spacer(1, 0.3*inch))
    
    for i, agent in enumerate(AGENTS, 1):
        toc_entry = Paragraph(
            f"{i}. {agent['emoji']} {agent['name']} — {agent['role']}",
            styles['Normal']
        )
        elements.append(toc_entry)
        elements.append(Spacer(1, 4))
    
    elements.append(PageBreak())
    
    return elements


def create_architecture_page(styles):
    """Create system architecture overview page."""
    elements = []
    
    elements.append(Paragraph("System Architecture", styles['Heading1']))
    elements.append(Spacer(1, 0.2*inch))
    
    arch_text = """
    The Forex Trading Platform is a multi-agent system consisting of 15 specialized AI agents, 
    each responsible for a specific aspect of the trading process. The system follows a hub-and-spoke 
    architecture where <b>Nexus</b> (the Orchestrator) serves as the central command hub, coordinating 
    all other agents.
    """
    elements.append(Paragraph(arch_text, styles['BodyText2']))
    
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("Data Flow Architecture", styles['SectionTitle']))
    
    flow_text = """
    <b>Read-Anywhere, Write-to-Hub:</b> Agents can read data directly from each other for efficiency, 
    but all significant outputs (decisions, recommendations, alerts) are written to the Orchestrator. 
    This prevents bias contamination while maintaining performance.
    """
    elements.append(Paragraph(flow_text, styles['BodyText2']))
    
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("Confluence Scoring Weights", styles['SectionTitle']))
    
    weights_data = [
        ["Component", "Weight", "Description"],
        ["Technical", "25%", "Trend, momentum, indicators (Atlas Jr.)"],
        ["Structure", "20%", "S/R levels, swing structure (Architect)"],
        ["Macro", "15%", "Fundamentals, rate differentials (Oracle)"],
        ["Sentiment", "10%", "Retail positioning, COT (Pulse)"],
        ["Regime", "15%", "Market state classification (Compass)"],
        ["Risk/Execution", "15%", "Risk approval, feasibility (Guardian, Executor)"],
    ]
    
    weights_table = Table(weights_data, colWidths=[1.2*inch, 0.8*inch, 3.5*inch])
    weights_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
    ]))
    elements.append(weights_table)
    
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("8 Hard Gates (Fail Any = NO_TRADE)", styles['SectionTitle']))
    
    gates_data = [
        ["Gate", "Agent", "Condition"],
        ["Event Risk", "Sentinel", "Not in blocked window"],
        ["Spread", "Curator", "Within threshold (2.5 pips major)"],
        ["Stop Defined", "Tactician", "Valid stop loss provided"],
        ["Regime Match", "Compass", "Strategy valid for regime"],
        ["Data Quality", "Curator", "Quality score ≥ 70%"],
        ["Portfolio Exposure", "Balancer", "Exposure score < 80"],
        ["Guardian Mode", "Guardian", "Not in HALTED mode"],
        ["Model Version", "Arbiter", "Using approved version"],
    ]
    
    gates_table = Table(gates_data, colWidths=[1.3*inch, 1*inch, 3.2*inch])
    gates_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c53030')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fff5f5')]),
    ]))
    elements.append(gates_table)
    
    elements.append(PageBreak())
    
    return elements


def create_agent_page(agent, styles):
    """Create documentation page for a single agent."""
    elements = []
    
    # Header
    header = f"{agent['emoji']} {agent['name']} — {agent['role']}"
    elements.append(Paragraph(header, styles['AgentTitle']))
    
    # Metadata
    meta = f"<b>Port:</b> {agent['port']} | <b>Version:</b> {agent['version']}"
    elements.append(Paragraph(meta, styles['Normal']))
    elements.append(Spacer(1, 0.1*inch))
    
    # Description
    elements.append(Paragraph("Overview", styles['SectionTitle']))
    elements.append(Paragraph(agent['description'], styles['BodyText2']))
    
    # Use Cases
    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("Use Cases", styles['SectionTitle']))
    
    use_case_items = []
    for uc in agent['use_cases']:
        use_case_items.append(ListItem(Paragraph(uc, styles['Normal']), leftIndent=20))
    
    elements.append(ListFlowable(use_case_items, bulletType='bullet', start='•'))
    
    # Key Endpoints
    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("Key API Endpoints", styles['SectionTitle']))
    
    endpoint_data = [["Endpoint", "Description"]]
    for ep, desc in agent['key_endpoints']:
        endpoint_data.append([ep, desc])
    
    endpoint_table = Table(endpoint_data, colWidths=[2.5*inch, 3.5*inch])
    endpoint_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (0, -1), 'Courier'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(endpoint_table)
    
    # Sample Output
    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("Sample Output", styles['SectionTitle']))
    
    sample = agent['sample_output']
    sample_text = f"<b>Endpoint:</b> <font face='Courier'>{sample['endpoint']}</font>"
    elements.append(Paragraph(sample_text, styles['Normal']))
    
    json_str = json.dumps(sample['response'], indent=2)
    # Truncate if too long
    if len(json_str) > 1000:
        json_str = json_str[:1000] + "\n  ... (truncated)"
    
    code_style = ParagraphStyle(
        'CodeBlock',
        fontName='Courier',
        fontSize=7,
        leftIndent=10,
        backColor=colors.HexColor('#f7fafc')
    )
    elements.append(Preformatted(json_str, code_style))
    
    # Orchestrator Integration
    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("Orchestrator Integration", styles['SectionTitle']))
    elements.append(Paragraph(agent['orchestrator_integration'], styles['BodyText2']))
    
    # Data to Orchestrator
    if agent['data_to_orchestrator'] != "N/A - Nexus is the orchestrator":
        elements.append(Spacer(1, 0.1*inch))
        elements.append(Paragraph("Data Passed to Orchestrator", styles['SectionTitle']))
        
        data_items = [["Field", "Description"]]
        for field, desc in agent['data_to_orchestrator'].items():
            data_items.append([field, desc])
        
        data_table = Table(data_items, colWidths=[1.5*inch, 4.5*inch])
        data_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (0, -1), 'Courier'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(data_table)
    
    elements.append(PageBreak())
    
    return elements


def create_workflows_page(styles):
    """Create workflows summary page."""
    elements = []
    
    elements.append(Paragraph("Operational Workflows", styles['Heading1']))
    elements.append(Spacer(1, 0.2*inch))
    
    workflows = [
        ("A: Market Open Prep", "Run before each trading session", 
         ["Refresh data (Curator)", "Compute levels (Architect)", "Update macro (Oracle)", 
          "Update events (Sentinel)", "Classify regimes (Compass)", "Generate watchlist (Tactician)"]),
        ("B: Intraday Scan", "Runs every 5 minutes",
         ["Scan all symbols", "Find setups (Tactician)", "Score via confluence (Nexus)", "Alert on score ≥75"]),
        ("C: Pre-Trade Approval", "9-step multi-agent validation",
         ["Technical (Atlas Jr.)", "Structure (Architect)", "Macro (Oracle)", "Sentiment (Pulse)",
          "Events (Sentinel)", "Portfolio (Balancer)", "Risk (Guardian) - VETO", "Execution (Executor)"]),
        ("D: Trade Execution", "Order submission and logging",
         ["Run approval (if needed)", "Send to Executor", "Validate response", "Log in Chronicle", "Monitor"]),
        ("E: Position Management", "Active position monitoring",
         ["Monitor thesis health", "Move stop (BE at +1R)", "Scale out at targets", "Exit on invalidation"]),
        ("F: EOD Review", "Daily performance summary",
         ["Summarize decisions", "List trades taken/rejected", "Find missed opportunities", "Compute metrics"]),
        ("G: Weekly Review", "Strategy analysis",
         ["Analyze by regime", "Analyze by strategy", "Identify weaknesses", "Queue validations (Arbiter)"]),
        ("H: Incident Response", "System monitoring",
         ["Detect MT5 disconnect", "Detect data corruption", "Detect drawdown breach", "Halt if needed"]),
    ]
    
    for name, timing, steps in workflows:
        elements.append(Paragraph(f"<b>{name}</b> — {timing}", styles['Normal']))
        step_items = [ListItem(Paragraph(s, styles['Normal']), leftIndent=20) for s in steps]
        elements.append(ListFlowable(step_items, bulletType='bullet', start='•'))
        elements.append(Spacer(1, 0.1*inch))
    
    elements.append(PageBreak())
    
    return elements


def generate_pdf(output_path):
    """Generate the complete PDF document."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    styles = create_styles()
    elements = []
    
    # Cover page
    elements.extend(create_cover_page(styles))
    
    # Table of contents
    elements.extend(create_toc(styles))
    
    # Architecture overview
    elements.extend(create_architecture_page(styles))
    
    # Workflows summary
    elements.extend(create_workflows_page(styles))
    
    # Individual agent pages
    for agent in AGENTS:
        elements.extend(create_agent_page(agent, styles))
    
    # Build PDF
    doc.build(elements)
    print(f"✅ PDF generated: {output_path}")


if __name__ == "__main__":
    output_path = "/Users/atlas/Projects/forex-trading-platform/docs/Agent_Documentation.pdf"
    generate_pdf(output_path)
