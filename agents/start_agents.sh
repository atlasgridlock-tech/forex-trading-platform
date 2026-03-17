#!/bin/bash
# Forex Trading Platform - Agent Launcher
# Loads environment and starts agents

set -e

# Load environment
export $(cat /app/agents/.env | xargs)

# Set MT5 data path
export MT5_DATA_PATH=/app/mt5_data
export SYMBOL_SUFFIX=.s

# Function to start an agent
start_agent() {
    local name=$1
    local port=$2
    local dir=$3
    
    echo "Starting $name on port $port..."
    cd /app/agents/$dir
    
    # Create workspace if needed
    mkdir -p workspace/memory
    
    # Start agent
    uvicorn app:app --host 0.0.0.0 --port $port &
    echo "  $name PID: $!"
}

# Start core agents in order
echo "=== Starting Forex Trading Platform Agents ==="

start_agent "Data Agent (Curator)" 3021 "data-agent"
sleep 2

start_agent "Risk Agent (Guardian)" 3013 "risk-agent"
sleep 1

start_agent "Execution Agent (Executor)" 3019 "execution-agent"
sleep 1

start_agent "Orchestrator (Nexus)" 3020 "orchestrator-agent"
sleep 1

# Optional: Start more agents
start_agent "News Agent (Sentinel)" 3010 "news-agent"
start_agent "Technical Agent (Atlas)" 3012 "technical-agent"
start_agent "Structure Agent (Architect)" 3014 "structure-agent"
start_agent "Regime Agent (Compass)" 3016 "regime-agent"
start_agent "Strategy Agent (Tactician)" 3017 "strategy-agent"

echo ""
echo "=== All agents started ==="
echo "Dashboard: http://localhost:3020"
echo ""
echo "Use 'jobs' to see running agents"
echo "Use 'curl http://localhost:PORT/api/status' to check individual agents"
