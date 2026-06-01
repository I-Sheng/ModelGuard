/**
 * Mock batch payloads for T-01 HMAC integrity incident testing.
 *
 * VALID_HMAC_BATCH  — a legitimate partner submission; sign with signBatch() before sending.
 * TAMPERED_BATCH    — attacker replaced high-risk queries with benign ones to suppress
 *                     detection; accompanied by FORGED_SIGNATURE which does not match.
 */

// ---------------------------------------------------------------------------
// Valid batch — represents real queries from partner "openai-demo".
// Features land in the MEDIUM risk band when scored:
//   query_count=12, unique_input_ratio≈0.83, avg_input_length≈95 chars,
//   input_entropy≈3.6, output_diversity≈0.75
// This payload MUST be signed with BATCH_HMAC_SECRET before submission.
// ---------------------------------------------------------------------------
export const VALID_HMAC_BATCH = {
  partner_id: "openai-demo",
  window_start: "2026-05-30T09:00:00Z",
  window_end: "2026-05-30T10:00:00Z",
  queries: [
    {
      query_id: "q-001",
      query_user: "user-alice",
      input: "How does self-attention work in transformer architectures?",
      output: "Self-attention computes a weighted sum of all positions in the sequence.",
    },
    {
      query_id: "q-002",
      query_user: "user-alice",
      input: "What is the difference between BERT and GPT model architectures?",
      output: "BERT is bidirectional; GPT is autoregressive and unidirectional.",
    },
    {
      query_id: "q-003",
      query_user: "user-alice",
      input: "Explain how token embeddings encode semantic meaning in large language models.",
      output: "Tokens are mapped to dense vectors that capture co-occurrence statistics.",
    },
    {
      query_id: "q-004",
      query_user: "user-bob",
      input: "What are the computational trade-offs of using mixture-of-experts layers?",
      output: "MoE reduces per-token compute by activating only a subset of parameters.",
    },
    {
      query_id: "q-005",
      query_user: "user-bob",
      input: "How does temperature sampling affect the diversity of generated text outputs?",
      output: "Higher temperature flattens the distribution, increasing output randomness.",
    },
    {
      query_id: "q-006",
      query_user: "user-bob",
      input: "Describe the role of layer normalization in stabilizing transformer training.",
      output: "Layer norm normalizes activations to have zero mean and unit variance.",
    },
    {
      query_id: "q-007",
      query_user: "user-carol",
      input: "What is RLHF and how does it align language models with human preferences?",
      output: "RLHF fine-tunes a model using a reward model trained on human comparisons.",
    },
    {
      query_id: "q-008",
      query_user: "user-carol",
      input: "How do rotary positional embeddings improve length generalization in LLMs?",
      output: "RoPE encodes absolute position via rotation, enabling relative attention.",
    },
    {
      query_id: "q-009",
      query_user: "user-carol",
      input: "What is speculative decoding and how does it accelerate inference throughput?",
      output: "A small draft model proposes tokens; the main model verifies them in parallel.",
    },
    {
      query_id: "q-010",
      query_user: "user-alice",
      input: "How do multi-head attention heads learn to specialize on different linguistic patterns?",
      output: "Each head attends to different subspaces, capturing syntax, coreference, and semantics.",
    },
    {
      query_id: "q-011",
      query_user: "user-bob",
      input: "Explain how flash attention reduces memory usage during transformer training.",
      output: "Flash attention tiles the attention computation to avoid materializing the full matrix.",
    },
    {
      query_id: "q-012",
      query_user: "user-carol",
      input: "What is chain-of-thought prompting and why does it improve reasoning performance?",
      output: "CoT prompts the model to output intermediate steps, improving multi-step accuracy.",
    },
  ],
};

// ---------------------------------------------------------------------------
// Tampered batch — the attacker originally submitted 40 high-volume, high-entropy
// queries from a single user (would score CRITICAL). They intercepted the batch
// in transit, replaced all records with low-risk benign queries, and recalculated
// a fake signature without knowledge of the real BATCH_HMAC_SECRET.
//
// Expected API response: 401 — Invalid batch signature.
// FORGED_SIGNATURE is a plausible-looking but incorrect hex digest.
// ---------------------------------------------------------------------------
export const TAMPERED_BATCH = {
  partner_id: "openai-demo",
  window_start: "2026-05-30T09:00:00Z",
  window_end: "2026-05-30T10:00:00Z",
  queries: [
    {
      query_id: "q-001",
      query_user: "user-mallory",
      input: "What is AI?",
      output: "AI stands for artificial intelligence.",
    },
    {
      query_id: "q-002",
      query_user: "user-mallory",
      input: "What is AI?",
      output: "AI stands for artificial intelligence.",
    },
    {
      query_id: "q-003",
      query_user: "user-mallory",
      input: "What is AI?",
      output: "AI stands for artificial intelligence.",
    },
    {
      query_id: "q-004",
      query_user: "user-mallory",
      input: "What is AI?",
      output: "AI stands for artificial intelligence.",
    },
    {
      query_id: "q-005",
      query_user: "user-mallory",
      input: "What is AI?",
      output: "AI stands for artificial intelligence.",
    },
  ],
};

// A fabricated signature — does not match TAMPERED_BATCH signed with any known secret.
export const FORGED_SIGNATURE =
  "sha256=aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899";
