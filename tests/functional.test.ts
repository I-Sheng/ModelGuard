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
  const res = await axios.post(`${BASE_URL}/auth/login`, params.toString(), {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return res.data.access_token;
}

// ---------------------------------------------------------------------------
// RBAC — ml_user must be denied customer-only endpoints
// ---------------------------------------------------------------------------

describe("ml_user RBAC", () => {
  let headers: { Authorization: string };

  beforeAll(async () => {
    const token = await login(
      process.env.ML_USER!,
      process.env.ML_USER_PASSWORD!
    );
    headers = { Authorization: `Bearer ${token}` };
  });

  test("GET /audit/{model_id} returns 403 for ml_user", async () => {
    await expect(
      axios.get(`${BASE_URL}/audit/any-model`, { headers })
    ).rejects.toMatchObject({ response: { status: 403 } });
  });

  test("GET /reports/{model_id} returns 403 for ml_user", async () => {
    await expect(
      axios.get(`${BASE_URL}/reports/any-model`, { headers })
    ).rejects.toMatchObject({ response: { status: 403 } });
  });
});
