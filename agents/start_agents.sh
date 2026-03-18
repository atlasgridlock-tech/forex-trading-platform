#!/bin/bash
# Forex Trading Platform - Agent Launcher (Mac/Local Version)
# Starts ALL agents for full functionality with health checks

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

# ═══════════════════════════════════════════════════════════════
# HEALTH CHECK FUNCTION
# ═══════════════════════════════════════════════════════════════
wait_for_agent() {
    local name=$1
    local port=$2
    local max_attempts=${3:-20}  # Default 20 attempts (10 seconds)
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s "http://localhost:$port/api/status" > /dev/null 2>&1; then
            echo "  ✅ $name is ready on port $port"
            return 0
        fi
        sleep 0.5
        attempt=$((attempt + 1))
    done
    
    echo "  ⚠️ $name health check timed out (port $port) - continuing anyway"
    return 0  # Don't fail the script, just warn
}

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

# Function to start agent and wait for health
start_and_wait() {
    local name=$1
    local port=$2
    local dir=$3
    local wait_time=${4:-20}  # Default wait attempts
    
    start_agent "$name" "$port" "$dir"
    wait_for_agent "$name" "$port" "$wait_time"
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
# TIER 1: Core Infrastructure (must start first and be healthy)
# ═══════════════════════════════════════════════════════════════
echo "▶ Starting Tier 1: Core Infrastructure..."

start_and_wait "Data Agent (Curator)" 3021 "data-agent" 30
start_and_wait "Orchestrator (Nexus)" 3020 "orchestrator-agent" 30

# ═══════════════════════════════════════════════════════════════
# TIER 2: Data & Analysis Agents
# ═══════════════════════════════════════════════════════════════
echo ""
echo "▶ Starting Tier 2: Data & Analysis Agents..."

# Start all tier 2 agents
start_agent "News Agent (Sentinel)" 3010 "news-agent"
start_agent "Macro Agent (Oracle)" 3011 "macro-agent"
start_agent "Technical Agent (Atlas)" 3012 "technical-agent"
start_agent "Structure Agent (Architect)" 3014 "structure-agent"
start_agent "Sentiment Agent (Pulse)" 3015 "sentiment-agent"
start_agent "Regime Agent (Compass)" 3016 "regime-agent"

# Wait for all tier 2 to be healthy before tier 3
echo "  Waiting for Tier 2 agents..."
sleep 2
wait_for_agent "News Agent" 3010 10
wait_for_agent "Macro Agent" 3011 10
wait_for_agent "Technical Agent" 3012 10
wait_for_agent "Structure Agent" 3014 10
wait_for_agent "Sentiment Agent" 3015 10
wait_for_agent "Regime Agent" 3016 10

# ═══════════════════════════════════════════════════════════════
# TIER 3: Decision & Strategy Agents
# ═══════════════════════════════════════════════════════════════
echo ""
echo "▶ Starting Tier 3: Decision & Strategy Agents..."

start_agent "Strategy Agent (Tactician)" 3017 "strategy-agent"
start_agent "Risk Agent (Guardian)" 3013 "risk-agent"
start_agent "Portfolio Agent (Balancer)" 3018 "portfolio-agent"

# Wait for tier 3 before starting execution
echo "  Waiting for Tier 3 agents..."
sleep 1
wait_for_agent "Strategy Agent" 3017 10
wait_for_agent "Risk Agent" 3013 10
wait_for_agent "Portfolio Agent" 3018 10

# ═══════════════════════════════════════════════════════════════
# TIER 4: Execution & Monitoring Agents
# ═══════════════════════════════════════════════════════════════
echo ""
echo "▶ Starting Tier 4: Execution & Monitoring Agents..."

start_agent "Execution Agent (Executor)" 3019 "execution-agent"
start_agent "Journal Agent (Chronicle)" 3022 "journal-agent"
start_agent "Analytics Agent (Insight)" 3023 "analytics-agent"
start_agent "Governance Agent (Arbiter)" 3024 "governance-agent"

# Final health check for all agents
echo ""
echo "▶ Running final health checks..."
sleep 2
wait_for_agent "Execution Agent" 3019 10
wait_for_agent "Journal Agent" 3022 10
wait_for_agent "Analytics Agent" 3023 10
wait_for_agent "Governance Agent" 3024 10

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
