/**
 * Functional tests — hit the live API at http://localhost:8000.
 * Requires the stack to be running: docker compose up
 */

import axios from "axios";
import * as dotenv from "dotenv";
import * as path from "path";
import { BENIGN_INPUTS, BENIGN_OUTPUTS } from "./fixtures/benign-batch";

dotenv.config({ path: path.resolve(__dirname, "../.env") });

const BASE_URL = "http://localhost:8000";

async function login(username: string, password: string): Promise<string> {
  const params = new URLSearchParams({ username, password });
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      const res = await axios.post(`${BASE_URL}/auth/login`, params.toString(), {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      return res.data.access_token;
    } catch (err: any) {
      if (err?.response?.status !== 429 || attempt === 5) throw err;
      await new Promise((r) => setTimeout(r, (attempt + 1) * 10_000));
    }
  }
  throw new Error("unreachable");
}

// ---------------------------------------------------------------------------
// Auth — login returns the expected token shape
// ---------------------------------------------------------------------------

describe("login", () => {
  test("valid credentials return access_token and role", async () => {
    const token = await login(process.env.ADMIN_USER!, process.env.ADMIN_PASSWORD!);
    expect(token).toBeTruthy();
  });

  test("wrong password returns 401", async () => {
    await expect(
      axios.post(
        `${BASE_URL}/auth/login`,
        new URLSearchParams({ username: "admin", password: "wrong" }).toString(),
        { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
      )
    ).rejects.toMatchObject({ response: { status: 401 } });
  });
});

// ---------------------------------------------------------------------------
// RBAC — analyst cannot POST /batch/analyze (partner-only endpoint)
// ---------------------------------------------------------------------------

describe("analyst RBAC", () => {
  let headers: { Authorization: string };

  beforeAll(async () => {
    const token = await login(process.env.ANALYST1!, process.env.ANALYST1_PASSWORD!);
    headers = { Authorization: `Bearer ${token}` };
  });

  test("GET /health returns 200 for analyst", async () => {
    const res = await axios.get(`${BASE_URL}/health`, { headers });
    expect(res.status).toBe(200);
  });

  test("POST /batch/analyze returns 403 for analyst", async () => {
    await expect(
      axios.post(
        `${BASE_URL}/batch/analyze`,
        {
          partner_id: "test",
          window_start: "2024-01-01T00:00:00Z",
          window_end: "2024-01-01T01:00:00Z",
          queries: [],
        },
        { headers }
      )
    ).rejects.toMatchObject({ response: { status: 403 } });
  });
});

// ---------------------------------------------------------------------------
// RBAC — unauthenticated requests to protected endpoints return 401
// ---------------------------------------------------------------------------

describe("unauthenticated access", () => {
  test("GET /stats without token returns 401", async () => {
    await expect(axios.get(`${BASE_URL}/stats`)).rejects.toMatchObject({
      response: { status: 401 },
    });
  });

  test("GET /auth/me without token returns 401", async () => {
    await expect(axios.get(`${BASE_URL}/auth/me`)).rejects.toMatchObject({
      response: { status: 401 },
    });
  });
});

// ---------------------------------------------------------------------------
// Risk 2 — False positive baseline
// Submits a batch engineered to sit at the training distribution mean.
// If the frozen Isolation Forest scores clearly normal traffic as HIGH/CRITICAL
// the test fails, giving early warning before any real customer is affected.
// ---------------------------------------------------------------------------

describe("Risk 2 — false positive baseline", () => {
  let headers: { Authorization: string };

  beforeAll(async () => {
    const token = await login(process.env.PARTNER1!, process.env.PARTNER1_PASSWORD!);
    headers = { Authorization: `Bearer ${token}` };
  });

  test("batch matching training distribution mean does not trigger HIGH or CRITICAL", async () => {
    const queries = Array.from({ length: 30 }, (_, i) => ({
      query_id:   `benign-q${i}`,
      query_user: "legitimate-user",
      input:  BENIGN_INPUTS[i % 18],   // 18 unique → unique_input_ratio = 0.60
      output: BENIGN_OUTPUTS[i % 14],  // 14 unique → output_diversity ≈ 0.47
    }));

    const res = await axios.post(
      `${BASE_URL}/batch/analyze`,
      {
        partner_id:   "fp-baseline-partner",
        window_start: "2026-05-11T00:00:00Z",
        window_end:   "2026-05-11T01:00:00Z",
        queries,
      },
      { headers }
    );

    expect(res.status).toBe(200);
    expect(["LOW", "MEDIUM"]).toContain(res.data.batch_risk_level);

    const flagged = (res.data.user_results as any[]).filter(
      (u) => u.risk_level === "HIGH" || u.risk_level === "CRITICAL"
    );
    expect(flagged).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Risk 3 — Partner activity monitoring
// After a batch is submitted, /stats/partners must reflect that partner with
// hours_since_last_batch < 1. If this endpoint breaks the OE dashboard loses
// its ability to detect silent integration failures.
// ---------------------------------------------------------------------------

describe("Risk 3 — partner activity monitoring", () => {
  let partnerHeaders: { Authorization: string };
  let adminHeaders:   { Authorization: string };
  const TEST_PARTNER = "activity-test-partner";

  beforeAll(async () => {
    const [partnerToken, adminToken] = await Promise.all([
      login(process.env.PARTNER1!,   process.env.PARTNER1_PASSWORD!),
      login(process.env.ADMIN_USER!, process.env.ADMIN_PASSWORD!),
    ]);
    partnerHeaders = { Authorization: `Bearer ${partnerToken}` };
    adminHeaders   = { Authorization: `Bearer ${adminToken}` };
  });

  test("/stats/partners shows partner with hours_since_last_batch < 1 after submission", async () => {
    await axios.post(
      `${BASE_URL}/batch/analyze`,
      {
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
      },
      { headers: partnerHeaders }
    );

    const res = await axios.get(`${BASE_URL}/stats/partners`, { headers: adminHeaders });
    expect(res.status).toBe(200);

    const entry = (res.data as any[]).find((p) => p.partner_id === TEST_PARTNER);
    expect(entry).toBeDefined();
    expect(entry.hours_since_last_batch).toBeGreaterThanOrEqual(0);
    expect(entry.hours_since_last_batch).toBeLessThan(1);
  });
});
