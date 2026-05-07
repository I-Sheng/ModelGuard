# OE Dashboard Runbook — ModelGuard AI

This document explains how to use the ModelGuard OE Dashboard day-to-day. It covers navigation, each page's purpose, and common workflows.

> OE Dashboard URL: `http://localhost:8501`  
> Source: [`oe-dashboard/app.py`](../oe-dashboard/app.py)  
> For incident response, see [`Oncall_Runbook.md`](Oncall_Runbook.md)

---

## Access

The dashboard auto-logs in as `admin` on startup — no login step required. Open `http://localhost:8501` in a browser while the stack is running (`docker compose up`).

If the page is blank or shows an API error, the backend may not be ready yet. Wait ~10 seconds and refresh, or see [Oncall_Runbook.md § OE Dashboard Itself Is Unreachable](Oncall_Runbook.md).

---

## Layout

```
┌─────────────────────────────────────────────────────────┐
│  Sidebar                │  Main panel                   │
│  ─────────────────────  │  ─────────────────────────── │
│  Navigation             │  Content for selected page    │
│  Live System Health     │                               │
└─────────────────────────────────────────────────────────┘
```

### Sidebar — Live System Health

Always visible. Refreshes on every page load. Shows four status indicators:

| Indicator | Healthy value |
|---|---|
| Frontend | ✅ ok |
| API | ✅ ok |
| MinIO | ✅ ok |
| Detector | ✅ loaded |

Any ❌ means a subsystem is down. Refer to the [Oncall Runbook triage tree](Oncall_Runbook.md) for remediation steps.

### Sidebar — Navigation

Use the radio buttons to switch between the four pages:

- **System Health**
- **Statistics**
- **Audit Logs**
- **Theft Reports**

---

## Pages

### System Health

Gives a detailed view of all four subsystems plus the raw JSON health payload from the backend.

**Metric tiles** (top row):

| Tile | What it shows |
|---|---|
| Frontend | nginx container reachability |
| API Status | backend `/health` response |
| MinIO | object storage connectivity |
| Detection Engine | whether the Isolation Forest model is in memory (`LOADED` / `NOT LOADED`) |

**Risk Level Reference chart** — a bar chart showing the score ranges that map to each risk level:

| Level | Score range |
|---|---|
| LOW | 0 – 39 |
| MEDIUM | 40 – 59 |
| HIGH | 60 – 79 |
| CRITICAL | 80 – 100 |

Use this page first whenever you suspect something is wrong with the system.

---

### Statistics

High-level platform counters. Useful for a quick operational snapshot.

| Metric | Description |
|---|---|
| Registered Partners | Total number of partner accounts |
| Batches Analyzed | Cumulative count of `/batch/analyze` calls |
| Detection Engine | Model load status |
| MinIO | Storage connectivity |

No inputs required — the page loads automatically.

---

### Audit Logs

Shows batch analysis records stored in the `modelguard-auditlog` MinIO bucket. Every call to `/batch/analyze` writes one record here regardless of risk level.

**Inputs:**

| Field | Description | Example |
|---|---|---|
| Partner ID | The partner whose logs to retrieve | `openai-demo` |
| Date filter | Narrow results to a specific date (optional) | `2026-05-07` |

Click **Fetch Audit Logs**. Results appear as a table with one row per batch window.

**Typical workflow:**

1. Enter the partner ID you want to investigate.
2. Leave the date filter blank to see all records, or enter a date to narrow the results.
3. Click **Fetch Audit Logs**.
4. Sort the table by `window_start` to see the most recent batches first.
5. Look for consecutive HIGH or CRITICAL `batch_risk_level` values — this may indicate an active extraction campaign.

---

### Theft Reports

Shows detailed reports for batches scored HIGH or CRITICAL, stored in the `modelguard-reports` MinIO bucket. LOW and MEDIUM batches do not produce a theft report.

**Inputs:**

| Field | Description | Example |
|---|---|---|
| Partner ID | The partner to look up | `openai-demo` |

Click **Fetch Theft Reports**. If reports exist, a table lists all of them. Select one from the dropdown to inspect it.

**Report detail view:**

| Section | What it shows |
|---|---|
| Batch Risk Level | Color-coded overall level (green → dark red) |
| Flagged Users | Count of users whose risk score exceeded the threshold |
| Total Queries | Number of queries in the batch window |
| Batch ID | Unique identifier for this batch |
| User Results | Table of flagged users with per-user feature vectors |
| Full Report | Raw JSON for the complete report |

**Reading the feature vectors:**

| Feature | Theft signal when elevated |
|---|---|
| `query_count` | High-volume automated querying (> 200/hr is suspicious) |
| `unique_input_ratio` | Systematic prompt diversity sweep (> 0.95) |
| `avg_input_length` | Long, structured prompts typical of model stealing (> 300 chars) |
| `input_entropy` | Varied prompt engineering (> 4.5) |
| `output_diversity` | Mapping many distinct outputs (> 0.90) |

Multiple flagged users all showing elevated values across all five features in the same batch window is a strong signal of an active model extraction campaign.

**Typical workflow:**

1. Enter the partner ID.
2. Click **Fetch Theft Reports**.
3. If reports are found, review the table for recent HIGH or CRITICAL entries.
4. Select a report from the dropdown to open the detail view.
5. Check **User Results** for flagged users and their feature vectors.
6. Copy the `query_user` values from **Full Report** to share with the partner.
7. Cross-reference with **Audit Logs** for the same partner and date range to see how many consecutive windows were affected.

---

## Common Workflows

### Daily health check (< 2 minutes)

1. Open `http://localhost:8501`.
2. Sidebar → confirm all four indicators are ✅.
3. Navigate to **Statistics** → verify Batches Analyzed has increased since yesterday.
4. Navigate to **Theft Reports** → enter each active partner ID → confirm no unexpected HIGH/CRITICAL reports.

### Investigating a flagged partner

1. **Audit Logs** → enter partner ID → Fetch → sort by `window_start` descending.
2. Note how many consecutive windows are HIGH or CRITICAL.
3. **Theft Reports** → enter same partner ID → Fetch → inspect each HIGH/CRITICAL report.
4. Record flagged `query_user` values, time range, and risk score range for the incident report.
5. Follow the [Oncall Runbook § Theft Event Spike](Oncall_Runbook.md) escalation checklist.

### Verifying recovery after a restart

1. Sidebar → **Live System Health** → confirm all four indicators are ✅.
2. **System Health** page → confirm Detection Engine = `LOADED`.
3. **Audit Logs** → fetch for the affected partner and time window → confirm records are present (no gap caused by MinIO downtime).
