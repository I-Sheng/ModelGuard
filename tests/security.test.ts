/**
 * Security tests — hit the live API at http://localhost:8000.
 * Requires the stack to be running: docker compose up
 *
 * Each test asserts that a known vulnerability currently exists.
 * Tests will start failing once mitigations are applied.
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
// T-03 — Rate limiting on /auth/login (credential-stuffing / brute-force)
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

    // Passes when rate limiting or lockout is in place: at least one response
    // must be 429 (Too Many Requests) or 403 (account locked).
    // Fails if every attempt returns 401 — meaning no protection exists.
    expect(statuses.some((s) => s === 429 || s === 403)).toBe(true);
  });
});
