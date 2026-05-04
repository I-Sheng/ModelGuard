// Pure unit tests — no HTTP calls, no live server needed.

// ---------------------------------------------------------------------------
// Risk level classification (mirrors api/main.py risk_level())
// Thresholds: CRITICAL >= 80, HIGH >= 60, MEDIUM >= 40, LOW < 40
// ---------------------------------------------------------------------------

function classifyRiskLevel(score: number): string {
  if (score >= 80) return "CRITICAL";
  if (score >= 60) return "HIGH";
  if (score >= 40) return "MEDIUM";
  return "LOW";
}

describe("classifyRiskLevel", () => {
  test.each([
    [80, "CRITICAL"],
    [95, "CRITICAL"],
    [100, "CRITICAL"],
  ])("score %d → CRITICAL", (score, expected) => {
    expect(classifyRiskLevel(score)).toBe(expected);
  });

  test.each([
    [60, "HIGH"],
    [70, "HIGH"],
    [79.9, "HIGH"],
  ])("score %d → HIGH", (score, expected) => {
    expect(classifyRiskLevel(score)).toBe(expected);
  });

  test.each([
    [40, "MEDIUM"],
    [50, "MEDIUM"],
    [59.9, "MEDIUM"],
  ])("score %d → MEDIUM", (score, expected) => {
    expect(classifyRiskLevel(score)).toBe(expected);
  });

  test.each([
    [0, "LOW"],
    [25, "LOW"],
    [39.9, "LOW"],
  ])("score %d → LOW", (score, expected) => {
    expect(classifyRiskLevel(score)).toBe(expected);
  });
});

// ---------------------------------------------------------------------------
// Batch payload builder
// Mirrors BatchAnalyzeRequest schema from api/main.py
// ---------------------------------------------------------------------------

interface QueryRecord {
  query_id: string;
  query_user: string;
  input: string;
  output: string;
}

interface BatchPayload {
  partner_id: string;
  window_start: string;
  window_end: string;
  queries: QueryRecord[];
}

function buildBatchPayload(
  partnerId: string,
  windowStart: string,
  windowEnd: string,
  queries: QueryRecord[]
): BatchPayload {
  return {
    partner_id: partnerId,
    window_start: windowStart,
    window_end: windowEnd,
    queries,
  };
}

describe("buildBatchPayload", () => {
  const record: QueryRecord = {
    query_id: "q1",
    query_user: "user_a",
    input: "What is a transformer?",
    output: "A transformer is a neural network architecture...",
  };

  test("includes all required top-level fields", () => {
    const p = buildBatchPayload("acme", "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", [record]);
    expect(p).toMatchObject({
      partner_id: "acme",
      window_start: "2024-01-01T00:00:00Z",
      window_end: "2024-01-01T01:00:00Z",
    });
  });

  test("each query record has the four required fields", () => {
    const p = buildBatchPayload("acme", "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", [record]);
    expect(p.queries[0]).toMatchObject({
      query_id: expect.any(String),
      query_user: expect.any(String),
      input: expect.any(String),
      output: expect.any(String),
    });
  });

  test("empty queries list is preserved", () => {
    const p = buildBatchPayload("acme", "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", []);
    expect(p.queries).toHaveLength(0);
  });

  test("multiple records are all included", () => {
    const records = Array.from({ length: 5 }, (_, i) => ({
      ...record,
      query_id: `q${i}`,
      query_user: `user_${i}`,
    }));
    const p = buildBatchPayload("acme", "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", records);
    expect(p.queries).toHaveLength(5);
  });
});

// ---------------------------------------------------------------------------
// JWT expiry check (no crypto — reads the exp claim from the payload segment)
// ---------------------------------------------------------------------------

function isTokenExpired(token: string): boolean {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return true;
    const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString());
    return typeof payload.exp !== "number" || payload.exp < Math.floor(Date.now() / 1000);
  } catch {
    return true;
  }
}

function makeTestToken(exp: number): string {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ sub: "user", role: "partner", exp })).toString("base64url");
  return `${header}.${payload}.fakesig`;
}

describe("isTokenExpired", () => {
  test("past exp → expired", () => {
    expect(isTokenExpired(makeTestToken(Math.floor(Date.now() / 1000) - 3600))).toBe(true);
  });

  test("future exp → not expired", () => {
    expect(isTokenExpired(makeTestToken(Math.floor(Date.now() / 1000) + 3600))).toBe(false);
  });

  test("malformed token → expired", () => {
    expect(isTokenExpired("not-a-jwt")).toBe(true);
    expect(isTokenExpired("")).toBe(true);
    expect(isTokenExpired("a.b.c.d")).toBe(true);
  });
});
