#!/bin/bash

# Auto-detect Project Directory
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"

# Create logs directory if it doesn't exist
mkdir -p "$PROJECT_DIR/logs"

# Locking mechanism to prevent concurrent runs
LOCKFILE="/tmp/nmap_api_cron.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "[$(date '+%H:%M:%S')] Another instance of cron.sh is already running. Exiting."
    exit 0
fi

cd $PROJECT_DIR

echo "--- Cron Cycle Started: $(date '+%Y-%m-%d %H:%M:%S') ---"

# Step 0: Sync Devices (Old Server -> Local)
echo "[$(date '+%H:%M:%S')] [Step 0] Running Devices Sync..."
$VENV_PYTHON core/sync_devices.py >> "$PROJECT_DIR/logs/sync_devices.log" 2>&1

# Step 1: Sync Engine (Old Server -> Local)
# Syncs today's tasks and marks high-failure places for real-time optimization (is_optimizer=1)
echo "[$(date '+%H:%M:%S')] [Step 1] Running Sync Engine..."
$VENV_PYTHON core/sync_engine.py >> "$PROJECT_DIR/logs/sync.log" 2>&1

# Step 2: Daily Aggregator
echo "[$(date '+%H:%M:%S')] [Step 2] Running Daily Aggregator..."
$VENV_PYTHON core/daily_aggregator.py >> "$PROJECT_DIR/logs/aggregator.log" 2>&1

# Step 3: GPS Boundary Optimizer
# Runs optimization for places with is_optimizer=1
echo "[$(date '+%H:%M:%S')] [Step 3] Running GPS Boundary Optimizer..."
$VENV_PYTHON core/optimizer.py >> "$PROJECT_DIR/logs/optimizer.log" 2>&1

echo "--- Cron Cycle Finished: $(date '+%Y-%m-%d %H:%M:%S') ---"
echo ""
