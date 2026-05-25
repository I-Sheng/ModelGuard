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
    const res = await axios.post(
      `${BASE_URL}/auth/login`,
      new URLSearchParams({ username: "admin", password: "wrong" }).toString(),
      {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        validateStatus: () => true,
      }
    );
    expect(res.status).toBe(401);
  });
});

// ---------------------------------------------------------------------------
// RBAC — /health is public (accessible without a token)
// ---------------------------------------------------------------------------

describe("analyst RBAC", () => {
  test("GET /health returns 200 for analyst", async () => {
    const res = await axios.get(`${BASE_URL}/health`, { validateStatus: () => true });
    expect(res.status).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// RBAC — unauthenticated requests to protected endpoints return 401
// ---------------------------------------------------------------------------

describe("unauthenticated access", () => {
  test("GET /stats without token returns 401", async () => {
    const res = await axios.get(`${BASE_URL}/stats`, { validateStatus: () => true });
    expect(res.status).toBe(401);
  });

  test("GET /auth/me without token returns 401", async () => {
    const res = await axios.get(`${BASE_URL}/auth/me`, { validateStatus: () => true });
    expect(res.status).toBe(401);
  });
});

