# Security model

Zero-Exposure RAG answers bank staff questions from internal documents. Its security goal is that restricted documents and personal data are never exposed to a user who is not cleared for them. This page lists the invariants the code relies on, then the threat model: what is protected, and what is not.

All data is synthetic. Prompts go to a hosted LLM (Groq) when `LLM_PROVIDER=groq`.

## Roles and clearance

| Role | Clearance | Sees documents at |
|---|---|---|
| `support_agent` | 1 | clearance 1 |
| `fraud_analyst` | 2 | clearance 1 and 2 |
| `compliance_officer` | 3 | clearance 1, 2 and 3 |

PII visibility per role is data, in `app/guards/policy.json`.

## Invariants

1. **Role comes only from the token.** `app/auth.py` maps a token to a user and role. The role is never read from the request body, headers other than the token, or the query text. Claiming a role in a question changes nothing.
2. **`X-Guards: off` works only with `EVAL_MODE=1`.** Otherwise the header is ignored (and a warning is logged). `/health` reports `eval_mode` so a run can be checked. `EVAL_MODE` must be 0 for any demo.
3. **Exactly one audit row per `/ask` request.** This includes authentication failures, input blocks, output blocks and errors (`decision="error"`).
4. **Per-clearance indexes.** There is one BM25 index per clearance tier. A tier-1 index does not contain tier-2 or tier-3 text or statistics, so a lower-clearance role cannot retrieve restricted text, however the question is phrased.
5. **Redact before generation, and again after.** With guards on, each retrieved chunk is redacted for the caller's role before it is put in the prompt, so the model never sees PII the role may not see. The model's answer is redacted again by the output guard as a second layer.
6. **Card numbers are always masked**, for every role, whatever the policy file says.
7. **Responses never repeat a secret.** A blocked response carries no answer and no sources, and the client-facing guard info is only `{label, score}` for the input guard and `{blocked, redaction_count}` for the output guard. The detailed reasons (which may quote the leaked value) go only to the audit log.
8. **`/audit` is compliance-only.** It needs a valid token (401 otherwise) and the `compliance_officer` role (403 otherwise). Questions are stored in the audit log with PII redacted using the support policy.
9. **Errors are generic.** An LLM failure or internal error returns a generic message (429, 503 or 500) with no internals; the details are logged and audited.
10. **Startup checks.** Settings, the retrieval index, the injection classifier, the audit database and the LLM provider are loaded at startup. A misconfiguration stops the server instead of failing on the first request.

## Request flow

token -> role -> input guard (rules + classifier) -> per-clearance retrieval -> redact context for the role -> LLM -> output guard (canaries, verbatim restricted text, repeated-digit loops, PII redaction) -> audit -> response.

The output guard blocks `CANARY-SYSPROMPT` for every role, and `CANARY-L{n}-dddd` only when `n` is above the role's clearance. It also blocks any answer containing an 8-token window that appears only in documents above the role's clearance. Matching is done on normalised text, so spaced-out, spelled-out or base64-encoded canaries are caught.

## Threat model

### What is protected

- Documents above a user's clearance are not retrievable by that user (invariants 1 and 4).
- Personal data the role may not see is removed before the model sees it and again before the user does (invariants 5 and 6).
- Secrets used as canaries do not appear in any response (invariant 7).
- An operator can see who asked what and what was decided (invariants 3 and 8).

### What is not protected

- **Prompts go to a hosted LLM.** Retrieved text, even redacted, is sent to Groq. Use only synthetic data. Do not point this at real customer data without a different deployment.
- **No per-customer scoping.** A support agent can read every customer's clearance-1 records. This is an accepted limitation of this phase; scoping is planned for a later phase.
- **Regex PII detection has limits.** Detection relies on patterns and word lists (names, phone, email, card with Luhn, account and national ID formats). Unusual formats, misspellings and names that are not in the lists can slip through.
- **Obfuscation coverage is finite.** The guards normalise spacing, case, spelled-out digits and base64. Other encodings (for example reversed text, other languages or custom ciphers) are not covered.
- **The classifier is small.** The injection classifier is TF-IDF with logistic regression trained on a few hundred examples, and the rules are phrase based. Novel phrasings can pass the input guard; the other layers exist for that reason.
- **Model files are pickles.** `models/*.pkl` are built by `app/guards/train_injection.py` and must only ever come from that script.
- **The audit log holds guard reasons**, which can quote leaked values. Protect the database file and the `/audit` endpoint accordingly.
