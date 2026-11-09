# Decision log

Decisions that affect more than one person, plus surprises worth remembering. Newest entries at the bottom. Each entry has a title, a date, a status (Accepted or Superseded), the context, the decision, its consequences and the owner.

---

### EVAL_MODE and X-Guards contract
- **Date:** 2026-10
- **Status:** Accepted
- **Context:** The red-team runner needs to run requests with the guards off to measure their effect, but the guards must never be silently disabled in a demo.
- **Decision:** `EVAL_MODE` defaults to off. The `X-Guards: off` header is honoured only when `EVAL_MODE=1`; otherwise it is ignored and a warning is logged.
- **Consequences:** `/health` reports `eval_mode`, and the runner refuses a guards-off comparison against a server that has it off. See [security-model.md](security-model.md).
- **Owner:** Rohan

### Local in-process model
- **Date:** 2026-10
- **Status:** Superseded by "Hosted LLM via Groq"
- **Context:** The first version served a small local model inside the API process so that no data left the machine.
- **Decision:** Load the model in-process at startup and call it for each request.
- **Consequences:** Needed large model files, native builds and a specific platform; superseded because it made the project hard to run for anyone else.
- **Owner:** Rohan

### Long-prompt latency of the local model
- **Date:** 2026-10
- **Status:** Superseded by "Hosted LLM via Groq"
- **Context:** The local model took about 2.6 s for a 20-token completion and about 104 s for a 200-token completion on three CPU cores, too slow for live use.
- **Decision:** None at the time; options were a smaller model, fewer tokens or fewer chunks.
- **Consequences:** Resolved by moving to a hosted model.
- **Owner:** Rohan

### Compliance report canary phrasing
- **Date:** 2026-10
- **Status:** Accepted
- **Context:** No clearance-3 sample existed to copy.
- **Decision:** Compliance reports end with "Compliance reference: CANARY-L3-{digits}." instead of the case-note wording "Internal reference:".
- **Consequences:** The canary format is unchanged; only the lead-in differs.
- **Owner:** Kishan

### Support notes mapped to doc_type profile
- **Date:** 2026-10
- **Status:** Accepted
- **Context:** The shared schema's `doc_type` enum has no support-note value.
- **Decision:** Generate support notes as `profile` documents rather than extending the enum.
- **Consequences:** The schema contract stays minimal; nothing downstream distinguishes the two.
- **Owner:** Kishan

### Per-tier BM25 indexes enforce clearance before ranking
- **Date:** 2026-10
- **Status:** Accepted
- **Context:** Clearance must hold even under prompt injection or odd scoring edge cases. Post-filtering a shared index can starve the top-k and leaks corpus statistics across clearance levels.
- **Decision:** Build one BM25 index per clearance tier (tier N holds only chunks with clearance <= N), selected only from the authenticated role.
- **Consequences:** A tier-1 index physically lacks restricted text and statistics. Memory use is higher, which is negligible at this scale.
- **Owner:** Kishan

### Canary matching: complete token, word boundary
- **Date:** 2026-10
- **Status:** Accepted
- **Context:** A canary ID could appear as part of a longer string.
- **Decision:** The scorer matches canary strings as complete tokens, applied identically across all runs. Normalised matching (see "Obfuscation-aware scoring") is added on top of this literal check.
- **Consequences:** Fewer false positives from coincidental overlap.
- **Owner:** Kashvith

### Injection classifier baseline
- **Date:** 2026-10
- **Status:** Accepted
- **Context:** A simple, interpretable baseline is enough to start; the rule layer catches known phrasings.
- **Decision:** TF-IDF (word and bigram, 5000 features) with logistic regression (balanced classes), trained on deepset/prompt-injections plus our own benign banking queries with an 80/20 split.
- **Consequences:** The classifier has limited recall on novel injections and can flag odd benign phrasing; the benign training set is extended when false blocks are found. Validation numbers are printed by `train_injection.py`.
- **Owner:** Kaustubh

### Model binaries not committed
- **Date:** 2026-10
- **Status:** Accepted
- **Context:** Pickled model files are binary and reproducible.
- **Decision:** `models/` is git-ignored; `app/guards/train_injection.py` regenerates the files deterministically (and the Docker build runs it).
- **Consequences:** A fresh checkout must run the training script once before the server starts; startup fails with a clear message otherwise.
- **Owner:** Kaustubh

### Retrieval-only leak check on dev attacks
- **Date:** 2026-10
- **Status:** Accepted
- **Context:** An LLM-free diagnostic helps find retrieval problems early and enforces tuning on the dev split.
- **Decision:** `retrieval/leak_check.py` runs dev attacks through `retrieve()` per role and reports clearance violations, restricted canaries and the zero-result rate; it refuses test-split records.
- **Consequences:** Leak counts are expected to be 0 by construction; the useful signal is the zero-result rate. Diagnostic only, never a headline number.
- **Owner:** Kishan

### Guard metadata when guards are disabled
- **Date:** 2026-10
- **Status:** Accepted
- **Context:** Evaluation must measure true leakage, not guard-filtered output.
- **Decision:** With `EVAL_MODE=1` and `X-Guards: off`, the answer is the raw model output and no input or output block is applied.
- **Consequences:** Anyone reading evaluation responses must not confuse the two shapes; `guards_disabled` marks them.
- **Owner:** Rohan

### Sources empty when blocked
- **Date:** 2026-11-09
- **Status:** Accepted (replaces an earlier behaviour that returned sources on output blocks)
- **Context:** Returning retrieved document IDs for a response that was blocked for a leak tells the caller which restricted material matched.
- **Decision:** Blocked responses have `sources: []`. The retrieved document IDs are still stored in the audit row.
- **Consequences:** The audit row, not the response, is the place to see what was retrieved for a blocked request.
- **Owner:** Rohan

### Hosted LLM via Groq
- **Date:** 2026-11-09
- **Status:** Accepted
- **Context:** The project must be free to run for anyone and must not need specialised hardware.
- **Decision:** Use the Groq free tier with model `qwen/qwen3.8-27b` and `reasoning_effort: "none"`. No local model and no other provider. Tests and CI use a mock provider.
- **Consequences:** Prompts leave the machine, so only synthetic data may be used; free-tier rate limits shape how evaluations are run (see [redteam.md](redteam.md)).
- **Owner:** Rohan

### Remove STUB_MODE in favour of a mock provider
- **Date:** 2026-11-09
- **Status:** Accepted
- **Context:** `STUB_MODE` replaced retrieval, guards and the model with canned values, so results could look real when they were not.
- **Decision:** Delete the stub path. The pipeline always runs the real guards and retrieval; only the LLM can be a deterministic mock (`fixed`, `echo` or `leaky`).
- **Consequences:** Tests exercise the real pipeline. The runner decides whether a run is quotable from server metadata (provider, `eval_mode`), not from a stub answer.
- **Owner:** Rohan

### Attack-suite rebuild
- **Date:** 2026-11-09
- **Status:** Accepted
- **Context:** The first suite had flaws that made results unreliable: 120 of 250 prompts contained their own target canary, 34 of 67 distinct test prompts also appeared in dev, 29 attacks could never succeed, and the indirect attacks did not target the poisoned documents.
- **Decision:** One-time rebuild before any published result, and then the split is frozen. The new generator never puts canary text in a prompt, emits only achievable attacks, splits by unique prompt text (60/40, seed 42) and targets poisoned documents with innocent-looking questions verified against retrieval. Each category has 50 records and at least 40 distinct prompts.
- **Consequences:** Earlier numbers are not comparable and are not published. Do not regenerate the suite after results exist.
- **Owner:** Kashvith

### Obfuscation-aware scoring
- **Date:** 2026-11-09
- **Status:** Accepted
- **Context:** Scoring only literal formats counts spaced-out, spelled-out or base64 leaks as safe.
- **Decision:** The scorer reports `literal_success` and `normalized_success` (NFKC, uppercase, separators removed, spelled-out digits, base64 decoded) and uses the normalised count for the attack success rate. It keeps its own copy of the rules so it stays independent of `app/`.
- **Consequences:** Reversed or otherwise encoded output is not detected, and the attack prompts do not ask for it.
- **Owner:** Kashvith

### Redact before generation
- **Date:** 2026-11-09
- **Status:** Accepted
- **Context:** Filtering only the answer lets an obfuscated answer carry PII the model was given.
- **Decision:** With guards on, retrieved chunks are redacted for the caller's role before they are put in the prompt. Output redaction stays as a second layer. Guards-off sends raw chunks.
- **Consequences:** The model cannot repeat PII it never saw. Answers can mention masked placeholders.
- **Owner:** Kaustubh

### /audit restricted to compliance
- **Date:** 2026-11-09
- **Status:** Accepted
- **Context:** The audit log holds queries and guard reasons that can quote leaked values.
- **Decision:** `/audit` requires a valid token (401) and the `compliance_officer` role (403). Stored queries are redacted with the support policy.
- **Consequences:** The dashboard sends the token from its form in live mode.
- **Owner:** Rohan

### Per-customer scoping deferred
- **Date:** 2026-11-09
- **Status:** Accepted
- **Context:** Restricting each support agent to their own customers needs an assignment model that does not exist yet.
- **Decision:** Not implemented in this phase. Support agents can read every customer's clearance-1 records. This is documented as an accepted limitation.
- **Consequences:** Listed in the security model and the README limitations; planned for a later phase.
- **Owner:** Rohan

### GitHub Pages static showcase
- **Date:** 2026-11-09
- **Status:** Accepted
- **Context:** A browser cannot call Groq without exposing the API key, so a live chatbot cannot be hosted for free.
- **Decision:** Publish a static showcase (dashboard, published results, recorded examples) on GitHub Pages. The live question form is hidden in static mode.
- **Consequences:** Visitors run the project locally to chat with it. The showcase contains only real evaluation output.
- **Owner:** Kashvith
