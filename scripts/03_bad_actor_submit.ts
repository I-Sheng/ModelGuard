/**
 * Script 3 — Bad actor submits a tampered batch with a forged signature.
 *
 * Logs in as bad-actor, sends TAMPERED_BATCH with FORGED_SIGNATURE.
 * Expected result: HTTP 401 — Invalid batch signature.
 * The backend logs: HMAC_SIGNATURE_FAILURE partner_id=openai-demo api_user=bad-actor
 *
 * Run: bun scripts/03_bad_actor_submit.ts
 */

import axios from "axios";
import * as dotenv from "dotenv";
import * as path from "path";
import { TAMPERED_BATCH, FORGED_SIGNATURE } from "../tests/fixtures/hmac-batch-fixtures";

dotenv.config({ path: path.resolve(__dirname, "../.env") });

const BASE_URL = "http://localhost:8000";

async function main() {
  // Login
  const loginRes = await axios.post(
    `${BASE_URL}/auth/login`,
    new URLSearchParams({
      username: process.env.BAD_ACTOR!,
      password: process.env.BAD_ACTOR_PASSWORD!,
    }).toString(),
    {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      validateStatus: () => true,
    }
  );
  if (loginRes.status !== 200) {
    console.error("Login failed:", loginRes.status, loginRes.data);
    process.exit(1);
  }
  const token = loginRes.data.access_token;
  console.log(`[bad-actor] logged in`);
  console.log(`[bad-actor] forged signature: ${FORGED_SIGNATURE}`);

  // Submit tampered batch with forged signature
  const res = await axios.post(`${BASE_URL}/batch/analyze`, TAMPERED_BATCH, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Batch-Signature": FORGED_SIGNATURE,
    },
    validateStatus: () => true,
  });

  console.log(`[bad-actor] HTTP ${res.status}`);
  if (res.status === 401) {
    console.log(`[bad-actor] rejected: ${res.data.detail}`);
    console.log(`\nCheck backend logs for the HMAC_SIGNATURE_FAILURE line:`);
    console.log(`  docker compose logs --tail=20 backend | grep HMAC_SIGNATURE_FAILURE`);
  } else {
    console.error("[bad-actor] UNEXPECTED — request should have been rejected:", res.data);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
