#!/usr/bin/env bash
set -e

WORKSPACE_DIR="/ai_workspace"
BRIDGE_DIR="$WORKSPACE_DIR/bridge"
LOG_DIR="$BRIDGE_DIR/logs"
PID_FILE="$BRIDGE_DIR/bridge.pid"

mkdir -p "$LOG_DIR"

echo "=========================================================="
echo "  🚀 Starting Local AI Workspace & llama.cpp Bridge"
echo "  Root Project: $WORKSPACE_DIR"
echo "  Web UI & OpenAI API Port: 8082"
echo "=========================================================="

# 1. Kill any stale process on port 8082 or 8085
echo "[*] Ensuring ports 8082 and 8085 are clear..."
fuser -k 8082/tcp 2>/dev/null || true
fuser -k 8085/tcp 2>/dev/null || true
pkill -f "llama-server.*--port 8085" 2>/dev/null || true
pkill -f "uvicorn.*app:app.*8082" 2>/dev/null || true
sleep 1

# 2. Start bridge server via Termux python
PYTHON_BIN="/data/data/com.termux/files/usr/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

echo "[*] Launching Bridge Server with $PYTHON_BIN..."
cd "$BRIDGE_DIR"
nohup "$PYTHON_BIN" -m uvicorn app:app --host 0.0.0.0 --port 8082 > "$LOG_DIR/bridge.log" 2>&1 &
BRIDGE_PID=$!
echo $BRIDGE_PID > "$PID_FILE"
echo "[*] Bridge process spawned (PID: $BRIDGE_PID)"

# 3. Wait for port 8082 to become responsive
echo "[*] Waiting for Bridge Web UI to initialize on port 8082..."
READY=0
for i in {1..30}; do
  if curl -s http://127.0.0.1:8082/health >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [ $READY -eq 1 ]; then
  echo "✅ Local AI Workspace is UP and RUNNING on port 8082!"
  echo "----------------------------------------------------------"
  echo "  • Web UI Dashboard:  http://localhost:8082"
  echo "  • OpenAI API URL:    http://localhost:8082/v1"
  echo "  • Models Endpoint:   http://localhost:8082/v1/models"
  echo "  • Chat Completions:  http://localhost:8082/v1/chat/completions"
  echo "  • Bridge Logs:       $LOG_DIR/bridge.log"
  echo "  • Llama Logs:        $LOG_DIR/llama.log"
  echo "----------------------------------------------------------"
  curl -s http://127.0.0.1:8082/health
  echo ""
else
  echo "❌ Error: Bridge failed to start. Last log lines:"
  tail -n 25 "$LOG_DIR/bridge.log"
  exit 1
fi
