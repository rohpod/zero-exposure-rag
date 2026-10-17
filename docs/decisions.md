# Decision log

Record decisions that affect more than one person, plus surprises worth remembering. Newest entries at the bottom. These notes feed the README and the pitch.

## Format

```
### Short title
- Stage:
- Decision:
- Why:
- Alternatives considered:
- Owner:
- Affects:
```

## Entries
### EVAL_MODE and X-Guards contract
- Stage: 1
- Decision: EVAL_MODE defaults to off. The X-Guards header (used by the red-team harness to run with guards off) is only honoured by the server when the environment variable EVAL_MODE=1 is set. EVAL_MODE must be off for the demo and the final submission.
- Why: prevents the guards from ever being silently disabled outside controlled evaluation runs; this is a security invariant (see PLAN.docx).
- Alternatives considered: none, this is fixed by the project interfaces document.
- Owner: Rohan
- Affects: Kaustubh (guards), Kashvith (red-team harness)

### Granite model served in-process, not via the notebook container
- Stage: 1
- Decision: app/llm.py loads the Granite GGUF model directly in the FastAPI process using llama-cpp-python, after copying the model file out of the JupyterLab container to models/ on the host. The notebook/container is kept only as the original reference, not used for serving.
- Why: the JupyterLab container exposes no serving API, only an interactive notebook; in-process loading is simplest for a 24-hour build and matches PLAN.docx's fallback philosophy.
- Alternatives considered: calling into the notebook container somehow (rejected, no exposed API, fragile); running a separate model-serving process (rejected, unnecessary complexity for this scale).
- Owner: Rohan
- Affects: everyone (this is the generate() interface retrieval/pipeline build against); Kashvith (latency numbers matter for demo pacing)

### Long-prompt latency is high, needs a decision before Stage 3
- Stage: 1
- Decision: not yet made. Measured 2.58s for a 20-token completion and 104.19s for a 200-token completion, both at temperature 0, on this VM's 3 CPU cores. This is too slow for a live demo if many turns need ~200 tokens.
- Why: CPU-only, modest core count, and this is a non-quantised f16 model.
- Alternatives considered: not yet evaluated. Candidates per PROJECT.docx fallback table: a smaller/more quantised model, lower max_tokens, fewer retrieved chunks.
- Owner: Rohan
- Affects: Kashvith (demo script timing), whole team (Stage 3 measurement latency numbers)

### Compliance report canary phrasing
- Stage: 1
- Decision: Compliance reports use "Compliance reference: CANARY-L3-{digits}." instead of copying the case_note sample's "Internal reference:" wording.
- Why: No clearance-3 sample existed to copy. The canary format itself didn't change, just the lead-in phrase.
- Alternatives considered: Reusing "Internal reference:" for all levels.
- Owner: Kishan (data and retrieval)
- Affects: data/generate.py, Kashvith's red-team prompts for compliance_report canaries

### Support notes mapped to doc_type profile
- Stage: 1
- Decision: Support notes are generated with doc_type "profile" rather than adding a separate enum value.
- Why: The schema's doc_type enum has no separate "support_note" value; support notes serve as customer profile and context documents, and nothing downstream (retrieval, guards) currently distinguishes between the two.
- Alternatives considered: Adding "support_note" to the schema's doc_type enum (rejected to keep the shared schema contract minimal and avoid breaking existing consumers).
- Owner: Kishan (data and retrieval)
- Affects: data/generate.py, retrieval filter queries, docs/schema.json

### Per-tier BM25 indexes enforce clearance before ranking
- Stage: 1
- Decision: Build one BM25 index per clearance tier (tier N contains only chunks with clearance <= N). The tier is selected strictly from the authenticated role enum.
- Why: Structural isolation by construction. A tier-1 index literally does not contain tier-2 or tier-3 chunk text or BM25 corpus statistics (IDF, average document length). Lower clearance roles cannot receive higher-clearance text even under prompt injection, canary queries, or search scoring edge cases.
- Alternatives considered:
  1. Single BM25 index with post-retrieval filtering (retrieve top-K, drop chunks where clearance > role_clearance). Rejected because: (a) top-K could be dominated by restricted documents, leaving fewer than K results for the user; (b) IDF statistics computed over restricted documents leak corpus frequency information across security boundaries; (c) post-filtering is an authorization layer on top of search rather than isolation by construction.
  2. Single BM25 index with pre-filtering query filter. Rejected because rank-bm25 is an in-memory library without query filter predicates, and modifying its scoring loop adds complexity and overhead.
  3. One BM25 index per clearance tier (chosen).
- Owner: Kishan (data and retrieval)
- Affects: retrieval/index.py, retrieval/retriever.py, app/pipeline.py (future wiring, Stage 2)

