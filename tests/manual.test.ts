/**
 * Manual tests — hit the live API at http://localhost:8000.
 * Requires the stack to be running: docker compose up
 */

import axios from "axios";
import * as dotenv from "dotenv";
import * as path from "path";

dotenv.config({ path: path.resolve(__dirname, "../.env") });

const BASE_URL = "http://localhost:8000";

async function login(username: string, password: string): Promise<string> {
  const params = new URLSearchParams({ username, password });
  const res = await axios.post(`${BASE_URL}/auth/login`, params.toString(), {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return res.data.access_token;
}

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
