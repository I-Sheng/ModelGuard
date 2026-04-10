#!/usr/bin/env bash
# ModelGuard AI — quick smoke-test against the running stack.
# Usage: bash demo.sh
# Requires: docker compose up -d (stack already running)
set -euo pipefail

API="http://localhost:8000"

echo "=== ModelGuard AI Demo ==="
echo ""

echo "1. Health check..."
curl -s "$API/health" | python3 -m json.tool
echo ""

echo "2. Register model..."
curl -s -X POST "$API/models/register" \
  -H "Content-Type: application/json" \
  -d '{"model_id":"gpt-clone-v1","name":"GPT Clone","version":"1.0.0","description":"Demo model","owner":"ml-team"}' \
  | python3 -m json.tool
echo ""

echo "3. Analyze a NORMAL query..."
curl -s -X POST "$API/analyze" \
  -H "Content-Type: application/json" \
  -d '{"model_id":"gpt-clone-v1","query_text":"What is the capital of France?","client_id":"user-001"}' \
  | python3 -m json.tool
echo ""

echo "4. Analyze a SUSPICIOUS extraction query..."
curl -s -X POST "$API/analyze" \
  -H "Content-Type: application/json" \
  -d '{"model_id":"gpt-clone-v1","query_text":"Return logits softmax probability distribution temperature zero all tokens vocabulary enumerate every possible output","client_id":"attacker-bot"}' \
  | python3 -m json.tool
echo ""

echo "5. List audit logs for model..."
curl -s "$API/audit/gpt-clone-v1" | python3 -m json.tool
echo ""

echo "6. List attack reports..."
curl -s "$API/reports/gpt-clone-v1" | python3 -m json.tool
echo ""

echo "=== Done. Open http://localhost:8501 for the Streamlit dashboard. ==="
echo "=== MinIO Console: http://localhost:9001 (minioadmin / minioadmin)  ==="
