#!/usr/bin/env bash
# ModelGuard AI — quick smoke-test against the running stack.
# Usage: bash demo.sh
# Requires: docker compose up -d (stack already running)
set -euo pipefail

source "$(dirname "$0")/.env"

API="http://localhost:8000"
PARTNER="openai-demo"

echo "=== ModelGuard AI Demo ==="
echo ""

echo "1. Health check..."
curl -s "$API/health" | python3 -m json.tool
echo ""

echo "2. Obtain admin JWT..."
TOKEN=$(curl -s -X POST "$API/auth/login" \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASSWORD}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token obtained."
echo ""

echo "3. Seed historical batch data into MinIO..."
docker compose exec -T backend python seed_history.py
echo ""

echo "4. POST /batch/analyze — normal batch (LOW risk)..."
curl -s -X POST "$API/batch/analyze" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"partner_id\": \"$PARTNER\",
    \"window_start\": \"$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)\",
    \"window_end\":   \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"queries\": [
      {\"query_id\": \"q-001\", \"query_user\": \"alice\", \"input\": \"What is the weather today?\", \"output\": \"It is sunny.\"},
      {\"query_id\": \"q-002\", \"query_user\": \"bob\",   \"input\": \"Translate hello to French.\",  \"output\": \"Bonjour.\"},
      {\"query_id\": \"q-003\", \"query_user\": \"alice\", \"input\": \"Summarize this article.\",     \"output\": \"The article covers...\"}
    ]
  }" | python3 -m json.tool
echo ""

echo "5. POST /batch/analyze — theft-attempt batch (HIGH/CRITICAL risk)..."
curl -s -X POST "$API/batch/analyze" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"partner_id\": \"$PARTNER\",
    \"window_start\": \"$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)\",
    \"window_end\":   \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"queries\": $(python3 -c "
import json, random, string
rng = random.Random(99)
qs = []
for i in range(300):
    inp = ' '.join(''.join(rng.choices(string.ascii_letters, k=rng.randint(5,20))) for _ in range(rng.randint(20,50)))
    out = 'output_' + str(i)
    qs.append({'query_id': f'q-{i:04d}', 'query_user': 'attacker-bot', 'input': inp, 'output': out})
print(json.dumps(qs))")
  }" | python3 -m json.tool
echo ""

echo "6. GET /audit/$PARTNER — list audit logs..."
curl -s -H "Authorization: Bearer $TOKEN" "$API/audit/$PARTNER" | python3 -m json.tool
echo ""

echo "7. GET /reports/$PARTNER — list theft reports..."
curl -s -H "Authorization: Bearer $TOKEN" "$API/reports/$PARTNER" | python3 -m json.tool
echo ""

echo "=== Done. ==="
echo "=== SwaggerAI Frontend:  http://localhost:3000                       ==="
echo "=== OE Dashboard:        http://localhost:8501                       ==="
echo "=== MinIO Console:       http://localhost:9001 (minioadmin/minioadmin)==="
