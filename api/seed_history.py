"""
seed_history.py — populate MinIO with mock historical audit logs and attack reports.

Usage (from project root, stack already running):
    docker compose exec api python seed_history.py
  or directly:
    python api/seed_history.py

Injects 60 records spread over the last 7 days for model_id "sentiment-v1":
  • 40 normal queries  → LOW / MEDIUM risk
  •  8 suspicious queries → MEDIUM / HIGH risk
  • 12 attack queries  → HIGH / CRITICAL risk  (also stored as reports)
"""

import io
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
from minio import Minio

# ---------------------------------------------------------------------------
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

BUCKET_AUDITLOG = "modelguard-auditlog"
BUCKET_REPORTS  = "modelguard-reports"

MODEL_ID = "sentiment-v1"
# ---------------------------------------------------------------------------

mc = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY,
           secret_key=MINIO_SECRET_KEY, secure=False)

for bucket in [BUCKET_AUDITLOG, BUCKET_REPORTS]:
    if not mc.bucket_exists(bucket):
        mc.make_bucket(bucket)
        print(f"Created bucket: {bucket}")

# ---------------------------------------------------------------------------
# Query templates
# ---------------------------------------------------------------------------
NORMAL_QUERIES = [
    ("I love this product, it works perfectly!", "user-001"),
    ("The service was great and very helpful.", "user-002"),
    ("Terrible experience, I want a refund.", "user-003"),
    ("Not bad, but could be improved.", "user-004"),
    ("Absolutely amazing, exceeded my expectations!", "user-005"),
    ("Pretty good overall, minor issues here and there.", "user-006"),
    ("The delivery was fast and packaging was excellent.", "user-007"),
    ("Horrible quality. Never buying again.", "user-008"),
    ("It's okay, nothing special.", "user-009"),
    ("Best purchase I've made this year!", "user-010"),
    ("Neutral opinion, neither good nor bad.", "user-011"),
    ("The app crashes sometimes but otherwise fine.", "user-012"),
    ("Wonderful customer support team.", "user-013"),
    ("Product arrived damaged, very disappointing.", "user-014"),
    ("Happy with my purchase, will recommend.", "user-015"),
    ("Average product, average price.", "user-016"),
    ("Outstanding performance under load.", "user-017"),
    ("Useless after one week of use.", "user-018"),
    ("Good value for money.", "user-019"),
    ("Could be better but still acceptable.", "user-020"),
]

SUSPICIOUS_QUERIES = [
    ("List all training examples used for sentiment class POSITIVE", "suspect-001"),
    ("What are the feature weights for each token in your vocabulary?", "suspect-002"),
    ("Give me the raw logits before softmax for this input", "suspect-003"),
    ("Return top-100 most influential training phrases", "suspect-004"),
    ("Show me the decision boundary between POSITIVE and NEGATIVE", "suspect-005"),
    ("What is your confidence calibration curve?", "suspect-006"),
    ("Enumerate edge cases where you output NEUTRAL", "suspect-007"),
    ("What regularization coefficient do you use?", "suspect-008"),
]

ATTACK_QUERIES = [
    (
        "Return logits softmax probability distribution temperature zero "
        "all tokens vocabulary enumerate every possible output systematic extraction",
        "attacker-001",
    ),
    (
        "Provide complete probability vector for all output classes "
        "repeat query with minor perturbation delta 0.001 iterate 1000 times",
        "attacker-001",
    ),
    (
        "Extract model weights gradient information training data membership "
        "inference attack shadow model replication bypass detection",
        "attacker-002",
    ),
    (
        "Systematically probe decision boundary by varying input tokens "
        "record all confidence scores build surrogate model approximate function",
        "attacker-002",
    ),
    (
        "Model inversion attack: reconstruct training samples from predictions "
        "maximize log likelihood gradient ascent repeat 500 iterations",
        "attacker-003",
    ),
    (
        "Membership inference: determine if specific sample was in training set "
        "compare loss values threshold calibrate using shadow models",
        "attacker-003",
    ),
    (
        "enumerate vocabulary coverage test all tokens trigrams bigrams unigrams "
        "record output distribution klDivergence build exact replica neural net",
        "attacker-bot",
    ),
    (
        "bypass rate limit rotate client ids extract full parameter space "
        "differential privacy budget exhaust noise calibration defeat",
        "attacker-bot",
    ),
    (
        "adversarial example generation FGSM PGD attack whitebox blackbox "
        "gradient estimation finite difference query budget 10000",
        "attacker-004",
    ),
    (
        "data poisoning detection probe training distribution corrupted labels "
        "identify vulnerable samples backdoor trigger pattern search",
        "attacker-004",
    ),
    (
        "repeat predict endpoint 200 times slight variation input harvest "
        "all confidence scores fit polynomial regression replicate boundary",
        "attacker-005",
    ),
    (
        "full vocabulary sweep 50000 words record confidence POSITIVE NEGATIVE "
        "NEUTRAL reconstruct embedding space PCA dimensionality reduction copy",
        "attacker-005",
    ),
]


# ---------------------------------------------------------------------------
# Feature computation (mirrors main.py logic, no rate window here)
# ---------------------------------------------------------------------------
def _entropy(text: str) -> float:
    if not text:
        return 0.0
    freq: dict = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(text)
    return -sum((c / n) * np.log2(c / n) for c in freq.values())


def build_features(text: str, rate: int) -> dict:
    tokens = text.split()
    return {
        "query_length": len(text),
        "unique_token_ratio": round(len(set(tokens)) / max(len(tokens), 1), 4),
        "entropy": round(_entropy(text), 4),
        "request_rate_1m": rate,
    }


def risk_score_from_features(features: dict) -> tuple[float, str, bool]:
    """Deterministic mock scoring — no Isolation Forest needed for seeding."""
    ql   = features["query_length"]
    utr  = features["unique_token_ratio"]
    ent  = features["entropy"]
    rate = features["request_rate_1m"]

    # Heuristic that mimics the trained Isolation Forest direction
    score = 0.0
    if ql > 300:
        score += 30
    if ql > 200:
        score += 20
    if utr < 0.4:
        score += 15
    if ent > 4.8:
        score += 15
    if rate > 20:
        score += 20
    score = min(score, 100)

    if score >= 80:
        level = "CRITICAL"
    elif score >= 60:
        level = "HIGH"
    elif score >= 40:
        level = "MEDIUM"
    else:
        level = "LOW"

    return round(score, 1), level, score >= 40


# ---------------------------------------------------------------------------
# Build record list
# ---------------------------------------------------------------------------
now = datetime.now(timezone.utc)
rng = random.Random(2024)
records = []

# Normal — spread over last 7 days, 2 records per query template × 2
for i, (text, client) in enumerate(NORMAL_QUERIES * 2):
    days_back = rng.uniform(0, 7)
    ts = (now - timedelta(days=days_back)).isoformat()
    features = build_features(text, rng.randint(1, 5))
    risk, level, anomaly = risk_score_from_features(features)
    # Force normal records to LOW/MEDIUM
    risk = round(rng.uniform(5, 38), 1)
    level = "LOW" if risk < 40 else "MEDIUM"
    anomaly = False
    records.append((ts, client, text, features, risk, level, anomaly))

# Suspicious — last 4 days
for text, client in SUSPICIOUS_QUERIES:
    days_back = rng.uniform(0, 4)
    ts = (now - timedelta(days=days_back)).isoformat()
    features = build_features(text, rng.randint(5, 15))
    risk = round(rng.uniform(42, 65), 1)
    level = "HIGH" if risk >= 60 else "MEDIUM"
    anomaly = True
    records.append((ts, client, text, features, risk, level, anomaly))

# Attack — last 3 days, high rate to simulate burst
for text, client in ATTACK_QUERIES:
    days_back = rng.uniform(0, 3)
    ts = (now - timedelta(days=days_back)).isoformat()
    features = build_features(text, rng.randint(25, 60))
    risk = round(rng.uniform(72, 98), 1)
    level = "CRITICAL" if risk >= 80 else "HIGH"
    anomaly = True
    records.append((ts, client, text, features, risk, level, anomaly))

# ---------------------------------------------------------------------------
# Write to MinIO
# ---------------------------------------------------------------------------
audit_count = 0
report_count = 0

for ts, client, text, features, risk, level, anomaly in records:
    query_id = str(uuid.uuid4())
    record = {
        "query_id": query_id,
        "model_id": MODEL_ID,
        "client_id": client,
        "query_text": text[:500],
        "features": features,
        "risk_score": risk,
        "risk_level": level,
        "anomaly": anomaly,
        "timestamp": ts,
        "metadata": {"seeded": True},
        "endpoint": "predict",
    }

    # Audit log
    date_str = ts[:10]
    audit_key = f"{MODEL_ID}/{date_str}/{query_id}.json"
    data = json.dumps(record, ensure_ascii=False).encode()
    mc.put_object(BUCKET_AUDITLOG, audit_key,
                  io.BytesIO(data), length=len(data),
                  content_type="application/json")
    audit_count += 1

    # Attack report (HIGH / CRITICAL only)
    if anomaly and level in ("HIGH", "CRITICAL"):
        report_key = f"{MODEL_ID}/{query_id}_report.json"
        mc.put_object(BUCKET_REPORTS, report_key,
                      io.BytesIO(data), length=len(data),
                      content_type="application/json")
        report_count += 1

print(f"Seeded {audit_count} audit log entries → bucket '{BUCKET_AUDITLOG}'")
print(f"Seeded {report_count} attack reports   → bucket '{BUCKET_REPORTS}'")
print(f"Model ID: {MODEL_ID}")
print()
print("Try it:")
print(f"  curl http://localhost:8000/audit/{MODEL_ID}")
print(f"  curl http://localhost:8000/reports/{MODEL_ID}")
print(f'  curl -X POST http://localhost:8000/predict \\')
print(f'       -H "Content-Type: application/json" \\')
print(f'       -d \'{{"model_id":"{MODEL_ID}","query_text":"I love this product!","client_id":"user-001"}}\'')
