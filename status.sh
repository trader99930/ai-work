#!/usr/bin/env bash

echo "=========================================================="
echo "  ⚡ Local AI Workspace Status (Port 8082)"
echo "=========================================================="

STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8082/health || echo "DOWN")

if [ "$STATUS_CODE" = "200" ]; then
  echo "✅ Bridge Status: ACTIVE (HTTP 200)"
  echo ""
  echo "--- System & Model Details ---"
  curl -s http://127.0.0.1:8082/api/status | /data/data/com.termux/files/usr/bin/python3 -m json.tool 2>/dev/null || curl -s http://127.0.0.1:8082/api/status
  echo ""
  echo "--- Active Models ---"
  curl -s http://127.0.0.1:8082/v1/models | /data/data/com.termux/files/usr/bin/python3 -m json.tool 2>/dev/null || curl -s http://127.0.0.1:8082/v1/models
else
  echo "❌ Bridge Status: DOWN (HTTP $STATUS_CODE)"
  echo "Run '/ai_workspace/start.sh' to start the workspace."
fi
