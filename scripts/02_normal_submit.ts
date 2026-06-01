/**
 * Script 2 — Normal partner submits a valid batch.
 *
 * Logs in as demo-partner, signs VALID_HMAC_BATCH with the correct
 * BATCH_HMAC_SECRET, and submits to /batch/analyze.
 * Expected result: HTTP 200 with a risk assessment.
 *
 * Run: bun scripts/02_normal_submit.ts
 */

import axios from "axios";
import * as crypto from "crypto";
import * as dotenv from "dotenv";
import * as path from "path";
import { VALID_HMAC_BATCH } from "../tests/fixtures/hmac-batch-fixtures";

dotenv.config({ path: path.resolve(__dirname, "../.env") });

const BASE_URL = "http://localhost:8000";

async function main() {
  // Login
  const loginRes = await axios.post(
    `${BASE_URL}/auth/login`,
    new URLSearchParams({
      username: process.env.DEMO_PARTNER!,
      password: process.env.DEMO_PARTNER_PASSWORD!,
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
  console.log(`[demo-partner] logged in`);

  // Sign the batch body
  const body = JSON.stringify(VALID_HMAC_BATCH);
  const sig =
    "sha256=" +
    crypto
      .createHmac("sha256", process.env.BATCH_HMAC_SECRET!)
      .update(body)
      .digest("hex");
  console.log(`[demo-partner] signature: ${sig}`);

  // Submit
  const res = await axios.post(`${BASE_URL}/batch/analyze`, VALID_HMAC_BATCH, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Batch-Signature": sig,
    },
    validateStatus: () => true,
  });

  console.log(`[demo-partner] HTTP ${res.status}`);
  if (res.status === 200) {
    const d = res.data;
    console.log(`[demo-partner] batch_id:    ${d.batch_id}`);
    console.log(`[demo-partner] risk_level:  ${d.batch_risk_level}`);
    console.log(`[demo-partner] total_users: ${d.total_users}`);
    console.log(`[demo-partner] audit_key:   ${d.audit_log_key}`);
  } else {
    console.error("[demo-partner] unexpected response:", res.data);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
