# Interactive Quick Start Tutorial

Welcome to the Forex Multi-Agent Trading Platform! This hands-on tutorial will guide you through setting up and using the system in about 15 minutes.

---

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] Python 3.11+ installed
- [ ] PostgreSQL running (for TimescaleDB)
- [ ] Redis running
- [ ] Terminal access to `/app/agents`

---

## Step 1: Verify Your Environment (2 minutes)

### 1.1 Check the agents directory

```bash
cd /app/agents
ls -la
```

**Expected output:** You should see directories like `orchestrator-agent/`, `data-agent/`, `execution-agent/`, etc.

✅ **Checkpoint:** Do you see 14+ agent directories? If yes, continue. If no, check your installation.

### 1.2 Check environment configuration

```bash
cat .env | grep -E "^[A-Z]" | head -10
```

**Expected output:** You should see environment variables like `ANTHROPIC_API_KEY`, `ORCHESTRATOR_URL`, etc.

✅ **Checkpoint:** Is `ANTHROPIC_API_KEY` set? (Required for AI features)

---

## Step 2: Start the Agent Swarm (3 minutes)

### 2.1 Launch all agents

```bash
./start_agents.sh
```

**What you'll see:** Each agent starting up with its port number.

```
Starting orchestrator-agent on port 3020...
Starting data-agent on port 3021...
Starting news-agent on port 3010...
...
```

⏳ **Wait 30 seconds** for all agents to initialize.

### 2.2 Verify agents are running

```bash
curl -s http://localhost:3020/api/status | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Orchestrator: {d.get(\"status\", \"unknown\")}')"
```

**Expected output:** `Orchestrator: online`

✅ **Checkpoint:** Is the orchestrator online? If yes, continue.

### 2.3 Check all agent status

```bash
curl -s http://localhost:3020/api/agents | python3 -c "
import sys, json
agents = json.load(sys.stdin)
online = sum(1 for a in agents.values() if a.get('status') == 'online')
print(f'Agents online: {online}/14')
"
```

**Expected output:** `Agents online: 14/14` (or close to it)

---

## Step 3: Start the Data Feed (2 minutes)

### 3.1 Launch simulated feed

The system needs price data to analyze. For testing, use the simulated feed:

```bash
python3 simulated_feed.py &
```

**What you'll see:** Messages about sending price updates.

### 3.2 Verify data is flowing

```bash
sleep 5 && curl -s http://localhost:3021/api/market/EURUSD | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'EURUSD Price: {d.get(\"bid\", 0):.5f}')
print(f'Spread: {d.get(\"spread\", 0):.1f} pips')
"
```

**Expected output:** A price around 1.08xxx and a spread.

✅ **Checkpoint:** Do you see live price data? If yes, the system is receiving data!

---

## Step 4: Explore the Analysis (3 minutes)

### 4.1 Get technical analysis

```bash
curl -s http://localhost:3012/api/analysis/EURUSD | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Trend Grade: {d.get(\"trend_grade\", \"?\")}')"
print(f'Bias: {d.get(\"directional_lean\", \"neutral\")}')
print(f'RSI: {d.get(\"indicators\", {}).get(\"rsi_14\", 0):.1f}')
"
```

### 4.2 Get sentiment data

```bash
curl -s http://localhost:3015/api/sentiment/EURUSD | python3 -c "
import sys, json
d = json.load(sys.stdin)
retail = d.get('retail_positioning', {})
print(f'Retail Long: {retail.get(\"long_pct\", 50)}%')
print(f'Retail Short: {retail.get(\"short_pct\", 50)}%')
"
```

### 4.3 Get macro analysis

```bash
curl -s http://localhost:3011/api/pair/EURUSD | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Macro Bias: {d.get(\"relative_bias\", \"neutral\")}')
print(f'Confidence: {d.get(\"confidence\", 0)}%')
"
```

✅ **Checkpoint:** Are all three analyses returning data? You're seeing the multi-agent system in action!

---

## Step 5: Evaluate a Trade (3 minutes)

### 5.1 Get confluence score

This is the key metric - how aligned are all the agents?

```bash
curl -s "http://localhost:3020/api/confluence/EURUSD?direction=long" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('='*50)
print(f'EURUSD LONG Confluence Score: {d.get(\"score\", 0)}/100')
print('='*50)
print(f'Decision: {d.get(\"decision\", \"UNKNOWN\")}')
print()
print('Breakdown:')
for k, v in d.get('breakdown', {}).items():
    print(f'  {k}: {v}')
"
```

**Interpretation:**
- Score ≥ 75: System recommends trading
- Score 60-74: Watchlist (close but not ready)
- Score < 60: No trade

### 5.2 Check the hard gates

```bash
curl -s "http://localhost:3020/api/confluence/EURUSD?direction=long" | python3 -c "
import sys, json
d = json.load(sys.stdin)
gates = d.get('gates', {})
print('Hard Gates:')
for gate, info in gates.items():
    status = '✅' if info.get('passed') else '❌'
    print(f'  {status} {gate}: {info.get(\"message\", \"\")}')
"
```

All gates must pass (✅) for a trade to be considered.

---

## Step 6: Execute a Paper Trade (2 minutes)

### 6.1 Submit a trade order

```bash
curl -s -X POST http://localhost:3019/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "direction": "long",
    "lot_size": 0.10,
    "entry_price": 1.0850,
    "stop_loss": 1.0820,
    "take_profit": 1.0880
  }' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('='*50)
print('TRADE EXECUTED')
print('='*50)
print(f'Order ID: {d.get(\"order_id\", \"N/A\")}')
print(f'Status: {d.get(\"status\", \"N/A\")}')
print(f'Fill Price: {d.get(\"fill_price\", 0):.5f}')
print(f'Mode: {d.get(\"mode\", \"paper\")}')
"
```

### 6.2 Check open positions

```bash
curl -s http://localhost:3019/api/positions | python3 -c "
import sys, json
positions = json.load(sys.stdin)
if isinstance(positions, list):
    print(f'Open positions: {len(positions)}')
    for p in positions:
        print(f'  {p.get(\"symbol\")} {p.get(\"direction\")} @ {p.get(\"entry_price\", 0):.5f}')
else:
    print('No positions or error')
"
```

✅ **Checkpoint:** Did you execute a paper trade? Congratulations! 🎉

---

## Step 7: Open the Monitoring Dashboard (1 minute)

### 7.1 Open in browser

```bash
echo "Open this URL in your browser:"
echo "http://localhost:3020/monitor"
```

Or if you have a browser command:
```bash
open http://localhost:3020/monitor  # macOS
# or
xdg-open http://localhost:3020/monitor  # Linux
```

### 7.2 What you'll see

- **Agent Health Grid:** All 14 agents with status indicators
- **Message Flow:** Inter-agent communication stats
- **Route Activity:** API endpoint usage and latency

---

## 🎓 You've Completed the Tutorial!

### What you learned:

1. ✅ How to start the agent swarm
2. ✅ How to feed data to the system
3. ✅ How to get analysis from individual agents
4. ✅ How to calculate confluence scores
5. ✅ How to execute paper trades
6. ✅ How to monitor the system

### Next steps:

| Goal | Resource |
|------|----------|
| Understand the full system | [HOW_IT_WORKS.md](HOW_IT_WORKS.md) |
| Learn all agent endpoints | [AGENTS_DIRECTORY.md](AGENTS_DIRECTORY.md) |
| Connect real MT5 data | [Agent_Data_Reference.md](Agent_Data_Reference.md) |
| Customize the system | [/app/agents/.env](/app/agents/.env) |

---

## Quick Reference Commands

```bash
# Start everything
cd /app/agents && ./start_agents.sh && python3 simulated_feed.py &

# Check system health
curl http://localhost:3020/api/agents | jq

# Get confluence
curl "http://localhost:3020/api/confluence/EURUSD?direction=long" | jq

# Full pair analysis
curl http://localhost:3020/api/pair-analysis/EURUSD | jq

# Execute paper trade
curl -X POST http://localhost:3019/api/execute -H "Content-Type: application/json" \
  -d '{"symbol":"EURUSD","direction":"long","lot_size":0.1,"stop_loss":1.08,"take_profit":1.09}'

# Check positions
curl http://localhost:3019/api/positions | jq

# Open dashboard
open http://localhost:3020/monitor
```

---

## Troubleshooting

### Agents not starting?
```bash
# Check if ports are in use
lsof -i :3020
lsof -i :3021

# Check Python syntax
cd /app/agents/orchestrator-agent && python3 -c "import app"
```

### No data flowing?
```bash
# Check simulated feed
ps aux | grep simulated_feed

# Test curator directly
curl http://localhost:3021/api/status
```

### Low confluence scores?
```bash
# Get detailed breakdown
curl http://localhost:3020/api/pair-analysis/EURUSD | jq '.agents'
```

---

*Tutorial complete! You're ready to explore the forex trading platform.*
