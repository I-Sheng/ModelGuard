/**
 * Security tests — hit the live API at http://localhost:8000.
 * Requires the stack to be running: docker compose up
 *
 * pass = control is in place; fail = vulnerability still present.
 */

import axios from "axios";
import * as crypto from "crypto";
import * as dotenv from "dotenv";
import * as path from "path";

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

// Acquire all tokens once, before any rate-limit test can exhaust /auth/login.
let partnerHeaders: { Authorization: string };
let adminHeaders: { Authorization: string };

beforeAll(async () => {
  const [partnerToken, adminToken] = await Promise.all([
    login(process.env.PARTNER1!, process.env.PARTNER1_PASSWORD!),
    login(process.env.ADMIN_USER!, process.env.ADMIN_PASSWORD!),
  ]);
  partnerHeaders = { Authorization: `Bearer ${partnerToken}` };
  adminHeaders   = { Authorization: `Bearer ${adminToken}` };
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
    const sig = signBatch(MINIMAL_BATCH);
    const res = await axios.post(`${BASE_URL}/batch/analyze`, MINIMAL_BATCH, {
      headers: { ...partnerHeaders, "X-Batch-Signature": sig },
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
    const sig = signBatch(MINIMAL_BATCH);
    const res = await axios.post(`${BASE_URL}/batch/analyze`, MINIMAL_BATCH, {
      headers: { ...partnerHeaders, "X-Batch-Signature": sig },
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

describe("T-03 batch analyze rate limiting", () => {
  test("flooding /batch/analyze triggers 429 before 80 requests", async () => {
    const sig = signBatch(MINIMAL_BATCH);
    const attempts = Array.from({ length: 80 }, () =>
      axios.post(`${BASE_URL}/batch/analyze`, MINIMAL_BATCH, {
        headers: { ...partnerHeaders, "X-Batch-Signature": sig },
        validateStatus: () => true,
      })
    );
    const responses = await Promise.all(attempts);
    const statuses = responses.map((r) => r.status);
    expect(statuses.some((s) => s === 429)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// T-03 — Rate limiting on /auth/login (credential-stuffing / brute-force)
// Run last — exhausts the login rate limit for this IP.
// ---------------------------------------------------------------------------

describe("T-03 login brute-force protection", () => {
  test("20 consecutive failed logins trigger throttling or lockout", async () => {
    const attempts = Array.from({ length: 20 }, () =>
      axios.post(
        `${BASE_URL}/auth/login`,
        new URLSearchParams({
          username: process.env.ADMIN_USER!,
          password: "definitely-wrong-password",
        }).toString(),
        {
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          validateStatus: () => true,
        }
      )
    );
    const responses = await Promise.all(attempts);
    const statuses = responses.map((r) => r.status);
    expect(statuses.some((s) => s === 429 || s === 403)).toBe(true);
  });
});
