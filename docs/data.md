# Data

All data in this project is synthetic. No real customer information, real account numbers, real names, or real personal data of any kind exists anywhere in this repository or in generated output. All records are produced by data/generate.py using Faker with a fixed seed.

## Document schema

Every document in the corpus follows this shape:

| Field | Type | Description |
|---|---|---|
| `doc_id` | string | Unique ID, format `doc_0042` (4-digit zero-padded) |
| `doc_type` | enum | One of: `policy`, `faq`, `profile`, `transactions`, `case_note`, `compliance_report` |
| `clearance` | integer | 1 (Support), 2 (Fraud), 3 (Compliance) |
| `customer_id` | string or null | Format `c_017`; null for policy/FAQ docs that aren't tied to a specific customer |
| `text` | string | The document's full text content |

Full machine-readable schema: `docs/schema.json`.

## Document counts and clearance

| doc_type | Count | Clearance | Notes |
|---|---|---|---|
| `transactions` | ~200 | 1 | One doc per customer, contains all of that customer's transactions |
| `profile` | ~400 | 1 | Support notes — see mapping note below |
| `policy` | ~15 | 1 | |
| `faq` | ~15 | 1 | |
| `case_note` | ~100 | 2 | Contains a unique canary |
| `compliance_report` | ~20 | 3 | Contains a unique canary |

Total: ~750 documents, ~200 customers.

## doc_type notes

Support notes are generated with `doc_type: "profile"`. The schema's enum has no separate "support_note" value, so support notes are treated as customer profile/context documents. See docs/decisions.md for the full reasoning if this needs revisiting later.

## Canaries

Every `case_note` (clearance 2) and `compliance_report` (clearance 3) document contains exactly one unique canary string, embedded at the end of the `text` field:

- Format: `CANARY-L{clearance}-{digits}`, where `{digits}` are the 4-digit number from that document's `doc_id`.
- Example: `doc_0501` (a case_note) contains `CANARY-L2-0501`.
- Case notes: "Internal reference: CANARY-L2-{digits}."
- Compliance reports: "Compliance reference: CANARY-L3-{digits}." (see docs/decisions.md for why this differs slightly from case_note phrasing)

No canary appears in any clearance-1 document. Every canary is globally unique across the whole corpus — no duplicates.

## Customer PII fields

Each of the ~200 customers has:

- `account_number` — synthetic, distinct per customer
- `card_number` — synthetic, Luhn-valid, uses a prefix that does not
  match any real card network's actual BIN range
- `phone`, `email` — synthetic, generated using deterministic string
  templates (`+1-555-1xxx`, `...@synthetic-ibz.example.com`)
- `national_id` — synthetic format (`SYN-900-xx-xxxx`), does not resemble
  any real country's national ID scheme
- `name` — synthetic, selected deterministically from fixed name lists
  to ensure reproducible output independent of Faker version changes

These fields appear in the `transactions` and `profile` documents tied to that customer via `customer_id`.

## Other generated files

- `docs/schema.json` — machine-readable JSON Schema for the document shape above, used for validation.
- `data/generated/relevance_fixtures.json` — 20 query/best-document pairs with known ground truth, for sanity-testing the retriever.
- `data/generated/` is gitignored; regenerate it by running `python3 data/generate.py`.

## Reproducibility

The generator uses a fixed seed (SEED = 42 in data/generate.py) for both Faker and Python's random module. Running the script twice produces byte-identical output.
