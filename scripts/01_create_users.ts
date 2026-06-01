/**
 * Script 1 — Create demo users.
 *
 * Logs in as admin and prints confirmation that demo-partner and bad-actor
 * exist in the running backend (they are seeded from .env at startup).
 *
 * Run: bun scripts/01_create_users.ts
 */

import axios from "axios";
import * as dotenv from "dotenv";
import * as path from "path";

dotenv.config({ path: path.resolve(__dirname, "../.env") });

const BASE_URL = "http://localhost:8000";

async function main() {
  // Verify admin can log in
  const adminRes = await axios.post(
    `${BASE_URL}/auth/login`,
    new URLSearchParams({
      username: process.env.ADMIN_USER!,
      password: process.env.ADMIN_PASSWORD!,
    }).toString(),
    {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      validateStatus: () => true,
    }
  );
  if (adminRes.status !== 200) {
    console.error("Admin login failed:", adminRes.status, adminRes.data);
    process.exit(1);
  }
  console.log(`[admin]        login OK  (role: ${adminRes.data.role})`);

  // Verify demo-partner can log in
  const partnerRes = await axios.post(
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
  if (partnerRes.status !== 200) {
    console.error("demo-partner login failed:", partnerRes.status, partnerRes.data);
    process.exit(1);
  }
  console.log(`[demo-partner] login OK  (role: ${partnerRes.data.role})`);

  // Verify bad-actor can log in
  const badRes = await axios.post(
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
  if (badRes.status !== 200) {
    console.error("bad-actor login failed:", badRes.status, badRes.data);
    process.exit(1);
  }
  console.log(`[bad-actor]    login OK  (role: ${badRes.data.role})`);

  console.log("\nBoth demo users are ready.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
