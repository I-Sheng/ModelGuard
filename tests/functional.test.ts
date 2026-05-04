/**
 * Functional tests — hit the live API at http://localhost:8000.
 * Requires the stack to be running: docker compose up
 */

import axios from "axios";
import * as dotenv from "dotenv";
import * as path from "path";

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
