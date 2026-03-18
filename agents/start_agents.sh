#!/bin/bash
# Forex Trading Platform - Agent Launcher (Mac/Local Version)
# Loads environment and starts agents

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "Script directory: $SCRIPT_DIR"

# CRITICAL: Set PYTHONPATH so agents can find the shared module
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
echo "PYTHONPATH: $PYTHONPATH"

# Load environment from .env file (create one if it doesn't exist)
ENV_FILE="$SCRIPT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo "Loading environment from $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "WARNING: No .env file found at $ENV_FILE"
    echo "Creating default .env file..."
    cat > "$ENV_FILE" << 'EOF'
# Forex Trading Platform Environment Variables
ANTHROPIC_API_KEY=your_key_here
QUALITY_THRESHOLD=0.7
SYMBOL_SUFFIX=.ecn
EOF
    echo "Please edit $ENV_FILE and add your API keys"
fi

# Set MT5 data path for Mac - MUST match what EA writes to
# MT5 on Mac writes to: ~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files
export MT5_DATA_PATH="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
echo "MT5_DATA_PATH: $MT5_DATA_PATH"

# Check if MT5 data directory exists
if [ -d "$MT5_DATA_PATH" ]; then
    echo "✅ MT5 data directory found"
    ls -la "$MT5_DATA_PATH"/*.csv 2>/dev/null || echo "  (no CSV files yet)"
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
        echo "ERROR: Agent directory not found: $agent_dir"
        return 1
    fi
    
    echo "Starting $name on port $port..."
    cd "$agent_dir"
    
    # Create workspace if needed
    mkdir -p workspace/memory
    
    # Start agent in background with PYTHONPATH set
    PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH" uvicorn app:app --host 0.0.0.0 --port $port &
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

# Start core agents in order
echo ""
echo "=== Starting Forex Trading Platform Agents ==="
echo ""

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
echo ""
echo "Dashboard: http://localhost:3020"
echo "Data Agent: http://localhost:3021"
echo ""
echo "To check agents: curl http://localhost:3020/api/status"
echo "To stop agents: pkill -f 'uvicorn app:app'"
echo ""

# Keep script running to show logs
wait
