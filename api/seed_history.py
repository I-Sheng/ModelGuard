"""
seed_history.py — populate MinIO with mock historical batch analysis records.

Usage (from project root, stack already running):
    docker compose exec backend python seed_history.py
  or directly:
    python api/seed_history.py

Three partners, each with a distinct narrative:

  openai-demo     (16 batches) — escalating campaign
    Days 7–5 back : all clean (LOW)
    Days 4–3 back : suspect appears (MEDIUM)
    Days 2–1 back : active extraction campaign (HIGH → CRITICAL)
    Day 0          : winding down (HIGH → MEDIUM)
    Theft reports  : 6  (3× HIGH, 3× CRITICAL)

  anthropic-demo  (13 batches) — burst then gone
    Days 7–3 back : all clean (LOW)
    Day 2 back     : 3 consecutive CRITICAL batches (burst campaign)
    Days 1–0       : clean again (attacker stopped)
    Theft reports  : 3  (3× CRITICAL)

  cohere-demo     (12 batches) — clean throughout
    7 days of clean traffic (all LOW)
    Theft reports  : 0

Grand total: 41 batches, 9 theft reports across 3 partners.
"""

import io
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from minio import Minio

# ---------------------------------------------------------------------------
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT",   "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

BUCKET_AUDITLOG = "modelguard-auditlog"
BUCKET_REPORTS  = "modelguard-reports"
# ---------------------------------------------------------------------------

mc = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)

for bucket in [BUCKET_AUDITLOG, BUCKET_REPORTS]:
    if not mc.bucket_exists(bucket):
        mc.make_bucket(bucket)
        print(f"Created bucket: {bucket}")

rng = random.Random(2024)
now = datetime.now(timezone.utc)

LEVEL_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _risk_level(score: float) -> str:
    if   score >= 80: return "CRITICAL"
    elif score >= 60: return "HIGH"
    elif score >= 40: return "MEDIUM"
    return "LOW"


def make_user_result(
    user_id: str,
    query_count: int,
    unique_input_ratio: float,
    avg_input_length: float,
    input_entropy: float,
    output_diversity: float,
    noise: float = 5.0,
) -> dict:
    """Score a user based on their feature profile (mirrors the Isolation Forest's direction)."""
    score = 0.0
    if query_count > 100:   score += 25
    if query_count > 200:   score += 15
    if unique_input_ratio > 0.90: score += 20
    if avg_input_length > 250:    score += 15
    if input_entropy > 4.5:       score += 15
    if output_diversity > 0.85:   score += 10
    score = round(min(max(score + rng.uniform(-noise, noise), 0.0), 100.0), 1)
    level = _risk_level(score)
    return {
        "query_user":  user_id,
        "query_count": query_count,
        "risk_score":  score,
        "risk_level":  level,
        "anomaly":     score >= 40,
        "features": {
            "query_count":        query_count,
            "unique_input_ratio": round(unique_input_ratio, 4),
            "avg_input_length":   round(avg_input_length,   2),
            "input_entropy":      round(input_entropy,       4),
            "output_diversity":   round(output_diversity,    4),
        },
    }


def make_normal_users(n: int, id_prefix: str, id_offset: int = 0) -> list[dict]:
    return [
        make_user_result(
            f"{id_prefix}-{id_offset + i:04d}",
            query_count=rng.randint(3, 28),
            unique_input_ratio=rng.uniform(0.35, 0.72),
            avg_input_length=rng.uniform(35, 135),
            input_entropy=rng.uniform(2.8, 4.0),
            output_diversity=rng.uniform(0.25, 0.60),
        )
        for i in range(n)
    ]


def write_batch(partner_id: str, window_end_ts: str, user_results: list[dict]) -> str:
    batch_id     = str(uuid.uuid4())
    total_q      = sum(u["query_count"] for u in user_results)
    flagged      = sum(1 for u in user_results if u["risk_level"] in ("HIGH", "CRITICAL"))
    batch_risk   = max(user_results, key=lambda u: LEVEL_ORDER[u["risk_level"]])["risk_level"]
    window_start = (datetime.fromisoformat(window_end_ts) - timedelta(hours=1)).isoformat()

    record = {
        "batch_id":         batch_id,
        "partner_id":       partner_id,
        "window_start":     window_start,
        "window_end":       window_end_ts,
        "total_queries":    total_q,
        "total_users":      len(user_results),
        "flagged_users":    flagged,
        "batch_risk_level": batch_risk,
        "user_results":     user_results,
        "timestamp":        window_end_ts,
        "seeded":           True,
    }

    date_str  = window_end_ts[:10]
    audit_key = f"{partner_id}/{date_str}/{batch_id}.json"
    data      = json.dumps(record, ensure_ascii=False).encode()
    mc.put_object(BUCKET_AUDITLOG, audit_key, io.BytesIO(data),
                  length=len(data), content_type="application/json")

    if batch_risk in ("HIGH", "CRITICAL"):
        report_key = f"{partner_id}/{batch_id}_report.json"
        mc.put_object(BUCKET_REPORTS, report_key, io.BytesIO(data),
                      length=len(data), content_type="application/json")

    return batch_risk


def ts(days_back: float, hour: int = 10) -> str:
    """Return an ISO timestamp for N days ago at the given hour (UTC)."""
    dt = now - timedelta(days=days_back)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# openai-demo — escalating campaign by "mx-stealer-7f3a"
#
# Attacker profiles:
#   MEDIUM suspect : qc=110, uir=0.91, ail=180, ent=3.9, od=0.68
#   HIGH attacker  : qc=200, uir=0.94, ail=290, ent=4.35, od=0.89
#   CRITICAL burst : qc=420, uir=0.98, ail=430, ent=5.0,  od=0.95
# ---------------------------------------------------------------------------
print("Seeding openai-demo ...")
PARTNER = "openai-demo"
counts  = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}

# Day 7–5: clean
for d, h in [(7, 9), (7, 21), (6, 9), (6, 21), (5, 9), (5, 21)]:
    level = write_batch(PARTNER, ts(d, h),
                        make_normal_users(rng.randint(60, 130), "oai-usr", id_offset=d * 200))
    counts[level] += 1

# Day 4: suspect appears (MEDIUM)
users = make_normal_users(rng.randint(50, 100), "oai-usr", id_offset=4000)
users.append(make_user_result("mx-stealer-7f3a", 110, 0.91, 180, 3.9, 0.68, noise=3.0))
level = write_batch(PARTNER, ts(4, 10), users); counts[level] += 1

users = make_normal_users(rng.randint(50, 100), "oai-usr", id_offset=4200)
level = write_batch(PARTNER, ts(4, 22), users); counts[level] += 1

# Day 3: suspect turns attacker (MEDIUM → HIGH)
users = make_normal_users(rng.randint(40, 80), "oai-usr", id_offset=3000)
users.append(make_user_result("mx-stealer-7f3a", 145, 0.93, 240, 4.3, 0.83, noise=3.0))
level = write_batch(PARTNER, ts(3, 9), users); counts[level] += 1

users = make_normal_users(rng.randint(40, 80), "oai-usr", id_offset=3200)
users.append(make_user_result("mx-stealer-7f3a", 200, 0.94, 290, 4.4, 0.89, noise=2.0))
level = write_batch(PARTNER, ts(3, 21), users); counts[level] += 1

# Day 2: full extraction campaign (HIGH → CRITICAL)
users = make_normal_users(rng.randint(30, 70), "oai-usr", id_offset=2000)
users.append(make_user_result("mx-stealer-7f3a", 310, 0.96, 370, 4.8, 0.92, noise=2.0))
level = write_batch(PARTNER, ts(2, 8), users); counts[level] += 1

users = make_normal_users(rng.randint(30, 70), "oai-usr", id_offset=2200)
users.append(make_user_result("mx-stealer-7f3a", 420, 0.98, 430, 5.0, 0.95, noise=2.0))
level = write_batch(PARTNER, ts(2, 20), users); counts[level] += 1

# Day 1: still active (two CRITICAL batches)
users = make_normal_users(rng.randint(30, 60), "oai-usr", id_offset=1000)
users.append(make_user_result("mx-stealer-7f3a", 450, 0.98, 450, 5.1, 0.96, noise=1.5))
level = write_batch(PARTNER, ts(1, 7), users); counts[level] += 1

users = make_normal_users(rng.randint(30, 60), "oai-usr", id_offset=1200)
users.append(make_user_result("mx-stealer-7f3a", 460, 0.99, 460, 5.1, 0.97, noise=1.5))
level = write_batch(PARTNER, ts(1, 19), users); counts[level] += 1

# Day 0: winding down after detection (HIGH → MEDIUM)
users = make_normal_users(rng.randint(40, 80), "oai-usr", id_offset=100)
users.append(make_user_result("mx-stealer-7f3a", 210, 0.94, 310, 4.5, 0.88, noise=2.0))
level = write_batch(PARTNER, ts(0, 8), users); counts[level] += 1

users = make_normal_users(rng.randint(50, 90), "oai-usr", id_offset=300)
users.append(make_user_result("mx-stealer-7f3a", 90, 0.88, 190, 4.1, 0.74, noise=3.0))
level = write_batch(PARTNER, ts(0, 20), users); counts[level] += 1

total_batches = sum(counts.values())
total_reports = counts["HIGH"] + counts["CRITICAL"]
print(f"  {total_batches} batches  ({counts})")
print(f"  {total_reports} theft reports  (HIGH: {counts['HIGH']}, CRITICAL: {counts['CRITICAL']})")


# ---------------------------------------------------------------------------
# anthropic-demo — burst campaign by "api-scanner-b291" on day 2, then clean
# ---------------------------------------------------------------------------
print("Seeding anthropic-demo ...")
PARTNER = "anthropic-demo"
counts  = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}

# Day 7–3: clean traffic
for d, h in [(7, 10), (7, 22), (6, 10), (6, 22), (5, 11), (4, 9), (3, 14)]:
    level = write_batch(PARTNER, ts(d, h),
                        make_normal_users(rng.randint(70, 160), "ant-usr", id_offset=d * 300))
    counts[level] += 1

# Day 2: 3 consecutive CRITICAL batches (burst campaign, 4-hour intervals)
for h in [6, 10, 14]:
    users = make_normal_users(rng.randint(40, 80), "ant-usr", id_offset=2000 + h * 50)
    users.append(make_user_result("api-scanner-b291", 480, 0.99, 460, 5.2, 0.97, noise=1.0))
    level = write_batch(PARTNER, ts(2, h), users); counts[level] += 1

# Day 2 evening: clean (scanner stopped after three rounds)
users = make_normal_users(rng.randint(60, 120), "ant-usr", id_offset=2900)
level = write_batch(PARTNER, ts(2, 22), users); counts[level] += 1

# Day 1–0: clean again
for d, h in [(1, 9), (1, 21), (0, 11)]:
    level = write_batch(PARTNER, ts(d, h),
                        make_normal_users(rng.randint(70, 150), "ant-usr", id_offset=d * 100 + h))
    counts[level] += 1

total_batches = sum(counts.values())
total_reports = counts["HIGH"] + counts["CRITICAL"]
print(f"  {total_batches} batches  ({counts})")
print(f"  {total_reports} theft reports  (HIGH: {counts['HIGH']}, CRITICAL: {counts['CRITICAL']})")


# ---------------------------------------------------------------------------
# cohere-demo — clean throughout, no threats
# ---------------------------------------------------------------------------
print("Seeding cohere-demo ...")
PARTNER = "cohere-demo"
counts  = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}

for d, h in [(7, 8), (7, 20), (6, 8), (6, 20), (5, 9), (4, 11),
             (3, 8), (3, 20), (2, 9), (1, 10), (1, 22), (0, 10)]:
    level = write_batch(PARTNER, ts(d, h),
                        make_normal_users(rng.randint(80, 180), "coh-usr", id_offset=d * 400 + h))
    counts[level] += 1

total_batches = sum(counts.values())
total_reports = counts["HIGH"] + counts["CRITICAL"]
print(f"  {total_batches} batches  ({counts})")
print(f"  {total_reports} theft reports")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
print("Done. MinIO now contains:")
print("  Bucket: modelguard-auditlog")
print("    openai-demo/     16 batch records  (escalating campaign)")
print("    anthropic-demo/  13 batch records  (burst then clean)")
print("    cohere-demo/     12 batch records  (clean throughout)")
print("  Bucket: modelguard-reports")
print("    openai-demo/      6 reports  (HIGH + CRITICAL)")
print("    anthropic-demo/   3 reports  (CRITICAL)")
print()
print("OE Dashboard quick-check:")
print("  http://localhost:8501  →  Statistics page: 3 partners, 41 batches")
print("  Audit Logs: enter 'openai-demo' or 'anthropic-demo' or 'cohere-demo'")
print("  Theft Reports: enter 'openai-demo' to see the escalating campaign")
