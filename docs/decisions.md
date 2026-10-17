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
