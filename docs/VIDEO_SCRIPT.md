# Forex Trading Platform - Video Script

**Duration:** ~10 minutes  
**Style:** Screen recording with voiceover  
**Audience:** Developers/Traders setting up the system

---

## INTRO (0:00 - 0:45)

**[SCREEN: Show main README.md]**

> "Welcome to the Forex Multi-Agent Trading Platform. This is a production-grade trading system built with 14 specialized AI agents that work together to analyze markets and execute trades.
>
> In this video, I'll walk you through:
> - How the system works
> - Setting it up on your machine
> - Running your first trade evaluation
> - Understanding the monitoring dashboard
>
> Let's dive in."

---

## PART 1: Architecture Overview (0:45 - 2:30)

**[SCREEN: Show architecture diagram from HOW_IT_WORKS.md]**

> "The platform consists of 14 microservices, each an expert in one area of trading.
>
> At the top, we have the DATA LAYER - these agents collect information:
> - Curator gets price data from MT5
> - Sentinel monitors news and economic events
> - Oracle analyzes macro fundamentals
> - Pulse tracks market sentiment
>
> In the middle is the ANALYSIS LAYER:
> - Atlas Jr. calculates technical indicators
> - Architect analyzes market structure
> - Compass identifies the current regime
> - Tactician validates strategy rules
>
> And at the bottom, the DECISION LAYER:
> - Nexus, the orchestrator, combines all inputs and makes decisions
> - Guardian has veto power on any trade for risk management
> - Executor handles the actual trade execution"

**[SCREEN: Show agent communication diagram]**

> "All agents communicate via REST APIs. When Nexus needs to evaluate a trade, it polls each agent, gathers their assessments, and calculates a confluence score."

---

## PART 2: The Trading Flow (2:30 - 4:00)

**[SCREEN: Terminal showing curl commands]**

> "Let me show you the actual trading flow. When we ask the system to evaluate EUR/USD..."

```bash
curl "http://localhost:3020/api/confluence/EURUSD?direction=long" | jq
```

**[SCREEN: Show JSON response]**

> "The system returns a confluence score. This score is a weighted average:
> - 25% from technical analysis
> - 20% from market structure  
> - 15% from regime detection
> - And so on...
>
> If the score is 75 or above, the system recommends executing. Between 60-74 goes to watchlist. Below 60 is a no-trade."

**[SCREEN: Show hard gates section]**

> "But before that score even matters, 8 hard gates must pass. These are binary checks - fail ANY one and the trade is rejected. Things like: is there a stop loss? Is the spread acceptable? Is there a high-impact news event coming?"

---

## PART 3: Setting Up the System (4:00 - 6:00)

**[SCREEN: Terminal in /app/agents directory]**

> "Let's set up the system. First, navigate to the agents directory."

```bash
cd /app/agents
```

> "Check that your environment file is configured:"

```bash
cat .env | head -20
```

**[SCREEN: Show .env file]**

> "You'll need:
> - ANTHROPIC_API_KEY for AI-powered news analysis
> - FRED_API_KEY for macro data (optional)
> - Myfxbook credentials for sentiment (optional)
>
> The agent URLs are pre-configured for localhost."

> "Now start all agents with the startup script:"

```bash
./start_agents.sh
```

**[SCREEN: Show agents starting up]**

> "You'll see each agent starting on its port. This takes about 30 seconds."

> "To feed the system with test data, run the simulated feed:"

```bash
python3 simulated_feed.py &
```

> "This generates realistic price movements for testing."

---

## PART 4: Using the Monitoring Dashboard (6:00 - 7:30)

**[SCREEN: Open browser to http://localhost:3020/monitor]**

> "The monitoring dashboard gives you a real-time view of the system."

**[SCREEN: Point to agent health grid]**

> "Here you can see all 14 agents. Green means online and healthy. If any agent goes down, it turns red immediately."

**[SCREEN: Point to message flow section]**

> "This section shows inter-agent communication - how many messages are flowing and the average latency."

**[SCREEN: Point to route statistics]**

> "And here are the API routes being called, with success rates and response times."

---

## PART 5: Evaluating and Executing Trades (7:30 - 9:00)

**[SCREEN: Terminal]**

> "Let's evaluate a real trade. I'll ask Nexus to analyze a long position on EUR/USD:"

```bash
curl -X POST http://localhost:3020/api/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "direction": "long",
    "entry_price": 1.0850,
    "stop_loss": 1.0820,
    "take_profit": 1.0910
  }' | jq
```

**[SCREEN: Show response with gates and score]**

> "The response shows all 8 gates checked, and a confluence score of... let's say 72. That's watchlist territory - close but not quite ready."

> "If we had a score of 78, we could execute in paper mode:"

```bash
curl -X POST http://localhost:3019/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "direction": "long",
    "lot_size": 0.10,
    "entry_price": 1.0850,
    "stop_loss": 1.0820,
    "take_profit": 1.0880,
    "take_profit_2": 1.0910,
    "take_profit_3": 1.0940
  }' | jq
```

**[SCREEN: Show execution receipt]**

> "The Executor confirms the paper trade with an order ID. Notice we set three take-profit levels - the system will automatically close 33% at TP1, another 50% at TP2, and the rest at TP3."

---

## PART 6: Position Lifecycle (9:00 - 9:45)

**[SCREEN: Terminal]**

> "Once a position is open, the lifecycle manager takes over:"

```bash
curl http://localhost:3019/api/lifecycle/positions | jq
```

**[SCREEN: Show lifecycle state]**

> "You can see the position state here. It starts as OPEN, then moves to BREAKEVEN after 10 pips profit - the stop loss automatically moves to entry plus one pip. Then as take-profits are hit, the state updates and partial positions close."

---

## OUTRO (9:45 - 10:00)

**[SCREEN: Show documentation files]**

> "That's the forex trading platform in action. For more details:
> - Check HOW_IT_WORKS.md for the complete system guide
> - AGENTS_DIRECTORY.md for quick agent reference
> - And individual agent READMEs for specific endpoints
>
> Remember: this system runs in paper mode by default. Real money trading requires passing all promotion gates and manual approval.
>
> Happy trading!"

---

## B-ROLL SUGGESTIONS

1. Architecture diagram animation
2. Agent health dashboard refreshing
3. Terminal showing real-time curl responses
4. Price chart with trade markers
5. Confluence score breakdown visualization

## TIMESTAMPS FOR CHAPTERS

```
0:00 - Introduction
0:45 - Architecture Overview
2:30 - Trading Flow Explained
4:00 - Setting Up the System
6:00 - Monitoring Dashboard
7:30 - Evaluating Trades
9:00 - Position Lifecycle
9:45 - Wrap Up
```
