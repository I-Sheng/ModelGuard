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
import {
  VALID_HMAC_BATCH,
  TAMPERED_BATCH,
  FORGED_SIGNATURE,
} from "./fixtures/hmac-batch-fixtures";

dotenv.config({ path: path.resolve(__dirname, "../.env") });

const BASE_URL = "http://localhost:8000";

// ---------------------------------------------------------------------------
// T-01 — Batch HMAC integrity
// ---------------------------------------------------------------------------

let partnerToken: string;

beforeAll(async () => {
  const params = new URLSearchParams({
    username: process.env.PARTNER1!,
    password: process.env.PARTNER1_PASSWORD!,
  }).toString();
  const res = await axios.post(`${BASE_URL}/auth/login`, params, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    validateStatus: () => true,
  });
  partnerToken = res.data.access_token;
});

describe("T-01 batch HMAC integrity", () => {
  test("TAMPERED_BATCH with FORGED_SIGNATURE is rejected with 401", async () => {
    const res = await axios.post(`${BASE_URL}/batch/analyze`, TAMPERED_BATCH, {
      headers: {
        Authorization: `Bearer ${partnerToken}`,
        "X-Batch-Signature": FORGED_SIGNATURE,
      },
      validateStatus: () => true,
    });
    expect(res.status).toBe(401);
  });

  test("VALID_HMAC_BATCH with correct signature is accepted with 200", async () => {
    const body = JSON.stringify(VALID_HMAC_BATCH);
    const sig =
      "sha256=" +
      crypto
        .createHmac("sha256", process.env.BATCH_HMAC_SECRET!)
        .update(body)
        .digest("hex");
    const res = await axios.post(`${BASE_URL}/batch/analyze`, VALID_HMAC_BATCH, {
      headers: {
        Authorization: `Bearer ${partnerToken}`,
        "X-Batch-Signature": sig,
      },
      validateStatus: () => true,
    });
    expect(res.status).toBe(200);
  });
});

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
    expect(statuses.some((s) => s === 429 || s === 403)).toBe(true);
  });
});
