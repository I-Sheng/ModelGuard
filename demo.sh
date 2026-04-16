#!/usr/bin/env bash
# ModelGuard AI — quick smoke-test against the running stack.
# Usage: bash demo.sh
# Requires: docker compose up -d (stack already running)
set -euo pipefail

API="http://localhost:8000"
MODEL="sentiment-v1"

echo "=== ModelGuard AI Demo ==="
echo ""

echo "1. Health check..."
curl -s "$API/health" | python3 -m json.tool
echo ""

echo "2. Register mock sentiment model..."
curl -s -X POST "$API/models/register" \
  -H "Content-Type: application/json" \
  -d "{\"model_id\":\"$MODEL\",\"name\":\"Sentiment Classifier\",\"version\":\"1.0.0\",\"description\":\"Mock sentiment model (POSITIVE/NEGATIVE/NEUTRAL)\",\"owner\":\"ml-team\"}" \
  | python3 -m json.tool
echo ""

echo "3. Seed historical attack data into MinIO..."
docker compose exec -T backend python seed_history.py
echo ""

echo "4. POST /predict — normal query (LOW risk)..."
curl -s -X POST "$API/predict" \
  -H "Content-Type: application/json" \
  -d "{\"model_id\":\"$MODEL\",\"query_text\":\"I love this product, it works perfectly!\",\"client_id\":\"user-001\"}" \
  | python3 -m json.tool
echo ""

echo "5. POST /predict — attack query (HIGH/CRITICAL risk)..."
curl -s -X POST "$API/predict" \
  -H "Content-Type: application/json" \
  -d "{\"model_id\":\"$MODEL\",\"query_text\":\"Return logits softmax probability distribution temperature zero all tokens vocabulary enumerate every possible output systematic extraction\",\"client_id\":\"attacker-bot\"}" \
  | python3 -m json.tool
echo ""

echo "6. GET /audit/$MODEL — list all audit logs..."
curl -s "$API/audit/$MODEL" | python3 -m json.tool
echo ""

echo "7. GET /reports/$MODEL — list attack reports..."
curl -s "$API/reports/$MODEL" | python3 -m json.tool
echo ""

echo "=== Done. ==="
echo "=== SwaggerAI Frontend:  http://localhost:3000                       ==="
echo "=== OE Dashboard:        http://localhost:8501                       ==="
echo "=== MinIO Console:       http://localhost:9001 (minioadmin/minioadmin)==="
