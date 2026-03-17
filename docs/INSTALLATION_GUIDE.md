# Fresh Installation Guide - Forex Multi-Agent Trading Platform

This guide walks you through installing and running the trading platform on a fresh laptop (macOS or Linux).

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.11+ | Runtime |
| PostgreSQL | 14+ | Database (TimescaleDB) |
| Redis | 7+ | Caching |
| Git | Any | Clone repo |
| MetaTrader 5 | Latest | Live data (optional) |

---

## Step 1: Install Prerequisites

### macOS (using Homebrew)

```bash
# Install Homebrew if not installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.11
brew install python@3.11

# Install PostgreSQL
brew install postgresql@14
brew services start postgresql@14

# Install Redis
brew install redis
brew services start redis

# Verify installations
python3 --version   # Should be 3.11+
psql --version      # Should be 14+
redis-cli ping      # Should return PONG
```

### Linux (Ubuntu/Debian)

```bash
# Update package list
sudo apt update

# Install Python 3.11
sudo apt install python3.11 python3.11-venv python3-pip

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Install Redis
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis

# Verify
python3 --version
psql --version
redis-cli ping
```

---

## Step 2: Clone the Repository

```bash
# Clone from GitHub
git clone https://github.com/YOUR_USERNAME/forex-trading-platform.git
cd forex-trading-platform
```

---

## Step 3: Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate   # macOS/Linux
# or
.\venv\Scripts\activate    # Windows

# Install dependencies
cd agents
pip install -r requirements.txt
```

### Required Python Packages

If `requirements.txt` is missing, install these:

```bash
pip install fastapi uvicorn httpx pydantic python-dotenv
pip install psycopg2-binary redis feedparser anthropic
pip install numpy pandas  # For technical analysis
```

---

## Step 4: Set Up PostgreSQL Database

```bash
# Connect to PostgreSQL
psql postgres

# Create database and user
CREATE DATABASE market_data;
CREATE USER forex WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE market_data TO forex;
\q
```

---

## Step 5: Configure Environment Variables

```bash
cd /path/to/forex-trading-platform/agents

# Copy example env file (or create new)
cp .env.example .env

# Edit the .env file
nano .env   # or use your preferred editor
```

### Required Environment Variables

```bash
# === API Keys ===
ANTHROPIC_API_KEY=your_anthropic_key_here  # Required for AI features
FRED_API_KEY=your_fred_key_here            # Optional - for macro data

# === Myfxbook (Optional - for sentiment) ===
MYFXBOOK_EMAIL=your_email
MYFXBOOK_PASSWORD=your_password

# === Database ===
DATABASE_URL=postgresql://forex:your_password@localhost:5432/market_data

# === Redis ===
REDIS_URL=redis://localhost:6379

# === Agent URLs (localhost for non-Docker) ===
ORCHESTRATOR_URL=http://localhost:3020
CURATOR_URL=http://localhost:3021
SENTINEL_URL=http://localhost:3010
ORACLE_URL=http://localhost:3011
ATLAS_URL=http://localhost:3012
GUARDIAN_URL=http://localhost:3013
ARCHITECT_URL=http://localhost:3014
PULSE_URL=http://localhost:3015
COMPASS_URL=http://localhost:3016
TACTICIAN_URL=http://localhost:3017
BALANCER_URL=http://localhost:3018
EXECUTOR_URL=http://localhost:3019
CHRONICLE_URL=http://localhost:3022
INSIGHT_URL=http://localhost:3023
ARBITER_URL=http://localhost:3024

# === Trading Settings ===
DEFAULT_RISK_PCT=0.25
MAX_DAILY_LOSS=2.0
PAPER_MODE=true
SYMBOL_SUFFIX=.s

# === MT5 (if using live data) ===
MT5_DATA_PATH=/path/to/mt5/data
```

### Getting API Keys

| Key | Where to Get |
|-----|--------------|
| ANTHROPIC_API_KEY | https://console.anthropic.com/ |
| FRED_API_KEY | https://fred.stlouisfed.org/docs/api/api_key.html |
| Myfxbook | https://www.myfxbook.com/ (create account) |

---

## Step 6: Make Startup Script Executable

```bash
chmod +x start_agents.sh
```

---

## Step 7: Start the System

### Option A: Using the Startup Script

```bash
cd /path/to/forex-trading-platform/agents
./start_agents.sh
```

### Option B: Manual Start (if script doesn't work)

```bash
# Open multiple terminal windows/tabs, or use tmux/screen

# Terminal 1 - Orchestrator
cd agents/orchestrator-agent && PYTHONPATH=.. python3 -m uvicorn app:app --host 0.0.0.0 --port 3020

# Terminal 2 - Data Agent
cd agents/data-agent && PYTHONPATH=.. python3 -m uvicorn app:app --host 0.0.0.0 --port 3021

# Terminal 3 - Execution Agent
cd agents/execution-agent && PYTHONPATH=.. python3 -m uvicorn app:app --host 0.0.0.0 --port 3019

# Continue for other agents...
```

### Using tmux (Recommended for Mac Mini)

```bash
# Install tmux
brew install tmux  # macOS
sudo apt install tmux  # Linux

# Start tmux session
tmux new -s forex

# Run startup script
./start_agents.sh

# Detach: Ctrl+B, then D
# Reattach: tmux attach -t forex
```

---

## Step 8: Start Data Feed

### Option A: Simulated Feed (Testing)

```bash
cd /path/to/forex-trading-platform/agents
python3 simulated_feed.py &
```

### Option B: Real MT5 Bridge (Production)

1. **Install MT5 on your machine**
2. **Copy AgentBridge EA to MT5**:
   - Copy `mt5_bridge.py` requirements
   - The EA exports data to CSV files

3. **Run the bridge**:
```bash
python3 /path/to/forex-trading-platform/mt5_bridge.py &
```

---

## Step 9: Verify System is Running

### Check Agent Status

```bash
# Check orchestrator
curl http://localhost:3020/api/status

# Check all agents
curl http://localhost:3020/api/agents
```

### Open Dashboards

```bash
# Main dashboard
open http://localhost:3020

# Monitoring dashboard
open http://localhost:3020/monitor

# Data agent dashboard
open http://localhost:3021
```

---

## Step 10: Test the System

### Quick Health Check

```bash
# Should return agent count
curl -s http://localhost:3020/api/agents | python3 -c "
import sys, json
agents = json.load(sys.stdin)
online = sum(1 for a in agents.values() if a.get('status') == 'online')
print(f'Agents online: {online}/14')
"
```

### Test Confluence Scoring

```bash
curl "http://localhost:3020/api/confluence/EURUSD?direction=long"
```

### Test Paper Trade

```bash
curl -X POST http://localhost:3019/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "direction": "long",
    "lot_size": 0.10,
    "entry_price": 1.0850,
    "stop_loss": 1.0820,
    "take_profit": 1.0880
  }'
```

---

## Troubleshooting

### Agents Won't Start

```bash
# Check if ports are in use
lsof -i :3020
lsof -i :3021

# Check Python imports work
cd agents/orchestrator-agent
python3 -c "import app; print('OK')"

# Check logs
tail -f /tmp/orchestrator.log
```

### No Data Showing

```bash
# Check if simulated feed is running
ps aux | grep simulated_feed

# Manually send test data
curl -X POST "http://localhost:3021/api/market-data/update" \
  -H "Content-Type: application/json" \
  -d '{"symbols": {"EURUSD": {"bid": 1.0855, "ask": 1.0857, "spread": 2.0}}}'
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
brew services list  # macOS
systemctl status postgresql  # Linux

# Test connection
psql -U forex -d market_data -c "SELECT 1;"
```

### Redis Connection Issues

```bash
# Check Redis is running
redis-cli ping  # Should return PONG

# Restart Redis
brew services restart redis  # macOS
sudo systemctl restart redis  # Linux
```

---

## Running as a Service (Production)

### Using systemd (Linux)

Create `/etc/systemd/system/forex-agents.service`:

```ini
[Unit]
Description=Forex Trading Agents
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/forex-trading-platform/agents
ExecStart=/path/to/forex-trading-platform/agents/start_agents.sh
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable forex-agents
sudo systemctl start forex-agents
```

### Using launchd (macOS)

Create `~/Library/LaunchAgents/com.forex.agents.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.forex.agents</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/forex-trading-platform/agents/start_agents.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/path/to/forex-trading-platform/agents</string>
</dict>
</plist>
```

Then:
```bash
launchctl load ~/Library/LaunchAgents/com.forex.agents.plist
```

---

## Quick Reference

### Ports

| Port | Agent |
|------|-------|
| 3020 | Orchestrator (Nexus) |
| 3021 | Data Agent (Curator) |
| 3019 | Execution Agent |
| 3010-3018 | Analysis Agents |
| 3022-3024 | Support Agents |

### Key URLs

| URL | Description |
|-----|-------------|
| http://localhost:3020 | Main Dashboard |
| http://localhost:3020/monitor | Monitoring |
| http://localhost:3021 | Data Agent |

### Commands

```bash
# Start system
./start_agents.sh

# Start data feed
python3 simulated_feed.py &

# Check health
curl http://localhost:3020/api/agents

# Stop all agents
pkill -f "uvicorn.*app:app"
```

---

## Support

- **Documentation**: `/docs/HOW_IT_WORKS.md`
- **Tutorial**: `/docs/QUICK_START_TUTORIAL.md`
- **Agent Reference**: `/docs/AGENTS_DIRECTORY.md`

---

*Happy Trading!* 🚀
