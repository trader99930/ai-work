#!/usr/bin/env bash

WORKSPACE_DIR="/ai_workspace"
BRIDGE_DIR="$WORKSPACE_DIR/bridge"
PID_FILE="$BRIDGE_DIR/bridge.pid"

echo "=========================================================="
echo "  🛑 Stopping Local AI Workspace Services"
echo "=========================================================="

if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  echo "[*] Killing bridge process PID: $PID"
  kill -15 "$PID" 2>/dev/null || true
  rm -f "$PID_FILE"
fi

echo "[*] Cleaning up background processes..."
pkill -f "llama-server.*--port 8085" 2>/dev/null || true
pkill -f "uvicorn.*app:app.*8082" 2>/dev/null || true
fuser -k 8082/tcp 2>/dev/null || true
fuser -k 8085/tcp 2>/dev/null || true

echo "✅ All AI workspace services stopped."
