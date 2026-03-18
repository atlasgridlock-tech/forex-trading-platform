#!/bin/bash
# Forex Trading Platform - Agent Launcher (Mac/Local Version)
# Starts ALL agents for full functionality

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "Script directory: $SCRIPT_DIR"

# CRITICAL: Set PYTHONPATH so agents can find the shared module
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
echo "PYTHONPATH: $PYTHONPATH"

# Load environment from .env file
ENV_FILE="$SCRIPT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo "Loading environment from $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "ERROR: No .env file found at $ENV_FILE"
    echo "Please copy .env.example to .env and configure it"
    exit 1
fi

# Set MT5 data path for Mac
export MT5_DATA_PATH="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
echo "MT5_DATA_PATH: $MT5_DATA_PATH"

# Check if MT5 data directory exists
if [ -d "$MT5_DATA_PATH" ]; then
    echo "✅ MT5 data directory found"
else
    echo "⚠️ MT5 data directory not found - make sure MT5 is running with the EA"
fi

# Function to start an agent
start_agent() {
    local name=$1
    local port=$2
    local dir=$3
    
    local agent_dir="$SCRIPT_DIR/$dir"
    
    if [ ! -d "$agent_dir" ]; then
        echo "⚠️ Agent directory not found: $dir (skipping)"
        return 0
    fi
    
    echo "Starting $name on port $port..."
    cd "$agent_dir"
    
    # Create workspace if needed
    mkdir -p workspace/memory 2>/dev/null || true
    
    # Start agent in background with PYTHONPATH set
    PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH" uvicorn app:app --host 0.0.0.0 --port $port 2>&1 &
    local pid=$!
    echo "  $name PID: $pid"
    
    # Go back to script directory
    cd "$SCRIPT_DIR"
}

# Kill any existing agents
echo ""
echo "Stopping any existing agents..."
pkill -f "uvicorn app:app" 2>/dev/null || true
sleep 2

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     FOREX MULTI-AGENT TRADING PLATFORM - STARTING ALL       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════════════════════
# TIER 1: Core Infrastructure (must start first)
# ═══════════════════════════════════════════════════════════════
echo "▶ Starting Tier 1: Core Infrastructure..."

start_agent "Data Agent (Curator)" 3021 "data-agent"
sleep 2

start_agent "Orchestrator (Nexus)" 3020 "orchestrator-agent"
sleep 1

# ═══════════════════════════════════════════════════════════════
# TIER 2: Data & Analysis Agents
# ═══════════════════════════════════════════════════════════════
echo ""
echo "▶ Starting Tier 2: Data & Analysis Agents..."

start_agent "News Agent (Sentinel)" 3010 "news-agent"
start_agent "Macro Agent (Oracle)" 3011 "macro-agent"
start_agent "Technical Agent (Atlas)" 3012 "technical-agent"
start_agent "Structure Agent (Architect)" 3014 "structure-agent"
start_agent "Sentiment Agent (Pulse)" 3015 "sentiment-agent"
start_agent "Regime Agent (Compass)" 3016 "regime-agent"
sleep 1

# ═══════════════════════════════════════════════════════════════
# TIER 3: Decision & Strategy Agents
# ═══════════════════════════════════════════════════════════════
echo ""
echo "▶ Starting Tier 3: Decision & Strategy Agents..."

start_agent "Strategy Agent (Tactician)" 3017 "strategy-agent"
start_agent "Risk Agent (Guardian)" 3013 "risk-agent"
start_agent "Portfolio Agent (Balancer)" 3018 "portfolio-agent"
sleep 1

# ═══════════════════════════════════════════════════════════════
# TIER 4: Execution & Monitoring Agents
# ═══════════════════════════════════════════════════════════════
echo ""
echo "▶ Starting Tier 4: Execution & Monitoring Agents..."

start_agent "Execution Agent (Executor)" 3019 "execution-agent"
start_agent "Journal Agent (Chronicle)" 3022 "journal-agent"
start_agent "Analytics Agent (Insight)" 3023 "analytics-agent"
start_agent "Governance Agent (Arbiter)" 3024 "governance-agent"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                  ALL AGENTS STARTED                          ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Dashboard:    http://localhost:3020                         ║"
echo "║  Data Agent:   http://localhost:3021                         ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Agent Ports:                                                ║"
echo "║    3010 Sentinel (News)      3017 Tactician (Strategy)       ║"
echo "║    3011 Oracle (Macro)       3018 Balancer (Portfolio)       ║"
echo "║    3012 Atlas (Technical)    3019 Executor (Execution)       ║"
echo "║    3013 Guardian (Risk)      3020 Nexus (Orchestrator)       ║"
echo "║    3014 Architect (Structure)3021 Curator (Data)             ║"
echo "║    3015 Pulse (Sentiment)    3022 Chronicle (Journal)        ║"
echo "║    3016 Compass (Regime)     3023 Insight (Analytics)        ║"
echo "║                              3024 Arbiter (Governance)       ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Commands:                                                   ║"
echo "║    Stop all:  pkill -f 'uvicorn app:app'                     ║"
echo "║    Check:     curl http://localhost:3020/api/status          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Keep script running to show logs
wait
