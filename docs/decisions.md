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

### PII name detection fallback
- Stage: 1
- Decision: use a word-list (250+ names) plus honorific/title context (Mr., Ms., Dr., "Customer", "Name:") instead of an NER library for first_name detection, with stop-word protection against ambiguous capitalized words (May, Will, Mark).
- Why: no NER library has been tested on the s390x VM yet, and scikit-learn already failed to pip-install there (needed the Ubuntu system package instead). Avoiding a similarly risky dependency for name detection this early, when regex/word-list has zero install risk and ships now.
- Alternatives considered: spaCy or a Hugging Face NER model (not yet tested on s390x, deferred as a possible upgrade if time permits); Presidio (same risk, not attempted).
- Owner: Kaustubh
- Affects: Kaustubh (PII detection recall on names, the weakest part of the detector per the project's own limitations list); whole team (README/limitations section, since this is an honestly-reported weakness, not a hidden one)
