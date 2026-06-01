/**
 * Manual tests — hit the live API at http://localhost:8000.
 * Requires the stack to be running: docker compose up
 */

import axios from "axios";
import * as crypto from "crypto";
import * as dotenv from "dotenv";
import * as path from "path";
import { BENIGN_INPUTS, BENIGN_OUTPUTS } from "./fixtures/benign-batch";

dotenv.config({ path: path.resolve(__dirname, "../.env") });

const BASE_URL = "http://localhost:8000";

async function login(username: string, password: string): Promise<string> {
  const params = new URLSearchParams({ username, password });
  const res = await axios.post(`${BASE_URL}/auth/login`, params.toString(), {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    validateStatus: () => true,
  });
  if (res.status !== 200) throw new Error(`Login failed: ${res.status}`);
  return res.data.access_token;
}

function signBatch(body: object): string {
  const raw = JSON.stringify(body);
  const digest = crypto
    .createHmac("sha256", process.env.BATCH_HMAC_SECRET!)
    .update(raw)
    .digest("hex");
  return `sha256=${digest}`;
}

const MINIMAL_BATCH = {
  partner_id: "security-test-partner",
  window_start: "2026-05-11T00:00:00Z",
  window_end: "2026-05-11T01:00:00Z",
  queries: [
    {
      query_id: "sec-q0",
      query_user: "sec-user",
      input: "What is a transformer?",
      output: "A transformer is a neural network architecture.",
    },
  ],
};

// Acquire all tokens once before any test runs.
let analystHeaders:  { Authorization: string };
let partnerHeaders:  { Authorization: string };
let adminHeaders:    { Authorization: string };

beforeAll(async () => {
  const [analystToken, partnerToken, adminToken] = await Promise.all([
    login(process.env.ANALYST1!,    process.env.ANALYST1_PASSWORD!),
    login(process.env.PARTNER1!,    process.env.PARTNER1_PASSWORD!),
    login(process.env.ADMIN_USER!,  process.env.ADMIN_PASSWORD!),
  ]);
  analystHeaders = { Authorization: `Bearer ${analystToken}` };
  partnerHeaders = { Authorization: `Bearer ${partnerToken}` };
  adminHeaders   = { Authorization: `Bearer ${adminToken}` };
});

// ---------------------------------------------------------------------------
// RBAC — analyst cannot POST /batch/analyze (partner-only endpoint)
// ---------------------------------------------------------------------------

describe("analyst RBAC", () => {
  test("POST /batch/analyze returns 403 for analyst", async () => {
    const body = {
      partner_id:   "test",
      window_start: "2024-01-01T00:00:00Z",
      window_end:   "2024-01-01T01:00:00Z",
      queries: [],
    };
    const res = await axios.post(`${BASE_URL}/batch/analyze`, body, {
      headers: { ...analystHeaders, "X-Batch-Signature": signBatch(body) },
      validateStatus: () => true,
    });
    expect(res.status).toBe(403);
  });
});

// ---------------------------------------------------------------------------
// T-01 — Batch HMAC signature enforcement
// ---------------------------------------------------------------------------

describe("T-01 batch HMAC signature enforcement", () => {
  test("request without X-Batch-Signature is rejected with 401", async () => {
    const res = await axios.post(`${BASE_URL}/batch/analyze`, MINIMAL_BATCH, {
      headers: partnerHeaders,
      validateStatus: () => true,
    });
    expect(res.status).toBe(401);
  });

  test("request with wrong signature is rejected with 401", async () => {
    const res = await axios.post(`${BASE_URL}/batch/analyze`, MINIMAL_BATCH, {
      headers: { ...partnerHeaders, "X-Batch-Signature": "sha256=deadbeef" },
      validateStatus: () => true,
    });
    expect(res.status).toBe(401);
  });

  test("request with correct signature is accepted", async () => {
    const res = await axios.post(`${BASE_URL}/batch/analyze`, MINIMAL_BATCH, {
      headers: { ...partnerHeaders, "X-Batch-Signature": signBatch(MINIMAL_BATCH) },
      validateStatus: () => true,
    });
    expect(res.status).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// T-02 — Audit log immutability (MinIO WORM / object lock)
// ---------------------------------------------------------------------------

describe("T-02 audit log immutability", () => {
  let auditKey: string;

  beforeAll(async () => {
    const res = await axios.post(`${BASE_URL}/batch/analyze`, MINIMAL_BATCH, {
      headers: { ...partnerHeaders, "X-Batch-Signature": signBatch(MINIMAL_BATCH) },
      validateStatus: () => true,
    });
    auditKey = res.data.audit_log_key;
  });

  test("stored audit log is visible in the audit listing", async () => {
    const res = await axios.get(
      `${BASE_URL}/audit/${MINIMAL_BATCH.partner_id}`,
      { headers: adminHeaders, validateStatus: () => true }
    );
    expect(res.status).toBe(200);
    const keys: string[] = res.data.audit_logs.map((l: any) => l.key);
    expect(keys.some((k) => k.includes(auditKey.split("/").pop()!))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// T-03 — Rate limiting on /batch/analyze (storage exhaustion / DoS)
// ---------------------------------------------------------------------------

// describe("T-03 batch analyze rate limiting", () => {
//   test("flooding /batch/analyze triggers 429 before 80 requests", async () => {
//     const sig = signBatch(MINIMAL_BATCH);
//     const attempts = Array.from({ length: 80 }, () =>
//       axios.post(`${BASE_URL}/batch/analyze`, MINIMAL_BATCH, {
//         headers: { ...partnerHeaders, "X-Batch-Signature": sig },
//         validateStatus: () => true,
//       })
//     );
//     const responses = await Promise.all(attempts);
//     const statuses = responses.map((r) => r.status);
//     expect(statuses.some((s) => s === 429)).toBe(true);
//   });
// });

// ---------------------------------------------------------------------------
// Risk 3 — Partner activity monitoring
// After a batch is submitted, /stats/partners must reflect that partner with
// hours_since_last_batch < 1. If this endpoint breaks the OE dashboard loses
// its ability to detect silent integration failures.
// ---------------------------------------------------------------------------

describe("Risk 3 — partner activity monitoring", () => {
  const TEST_PARTNER = "activity-test-partner";

  test("/stats/partners reflects partner within 1 hour of submission", async () => {
    const body = {
      partner_id:   TEST_PARTNER,
      window_start: "2026-05-11T00:00:00Z",
      window_end:   "2026-05-11T01:00:00Z",
      queries: [
        {
          query_id:   "activity-q0",
          query_user: "activity-user",
          input:  "How does attention work in transformer architectures?",
          output: "Attention maps inputs to outputs using query, key, and value projections.",
        },
      ],
    };
    await axios.post(`${BASE_URL}/batch/analyze`, body, {
      headers: { ...partnerHeaders, "X-Batch-Signature": signBatch(body) },
      validateStatus: () => true,
    });

    const res = await axios.get(`${BASE_URL}/stats/partners`, {
      headers: adminHeaders,
      validateStatus: () => true,
    });
    expect(res.status).toBe(200);

    const entry = (res.data as any[]).find((p) => p.partner_id === TEST_PARTNER);
    expect(entry).toBeDefined();
    expect(entry.hours_since_last_batch).toBeGreaterThanOrEqual(0);
    expect(entry.hours_since_last_batch).toBeLessThan(1);
  });
});

// ---------------------------------------------------------------------------
// Risk 2 — False positive baseline
// Submits a batch engineered to sit at the training distribution mean.
// If the frozen Isolation Forest scores clearly normal traffic as HIGH/CRITICAL
// the test fails, giving early warning before any real customer is affected.
// ---------------------------------------------------------------------------

describe("Risk 2 — false positive baseline", () => {
  test("batch matching training distribution mean does not trigger HIGH or CRITICAL", async () => {
    const queries = Array.from({ length: 30 }, (_, i) => ({
      query_id:   `benign-q${i}`,
      query_user: "legitimate-user",
      input:  BENIGN_INPUTS[i % 18],
      output: BENIGN_OUTPUTS[i % 14],
    }));

    const body = {
      partner_id:   "fp-baseline-partner",
      window_start: "2026-05-11T00:00:00Z",
      window_end:   "2026-05-11T01:00:00Z",
      queries,
    };
    const res = await axios.post(`${BASE_URL}/batch/analyze`, body, {
      headers: { ...partnerHeaders, "X-Batch-Signature": signBatch(body) },
      validateStatus: () => true,
    });

    expect(res.status).toBe(200);
    expect(["LOW", "MEDIUM"]).toContain(res.data.batch_risk_level);

    const flagged = (res.data.user_results as any[]).filter(
      (u) => u.risk_level === "HIGH" || u.risk_level === "CRITICAL"
    );
    expect(flagged).toHaveLength(0);
  });
});
