import json
from pathlib import Path

import pytest

from app.guards.output_guard import scan_output

SAMPLE_DOCS_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "samples" / "sample_canary_docs.json"
)
with open(SAMPLE_DOCS_PATH) as f:
    SAMPLE_DOCS = json.load(f)


def test_clean_answer_not_blocked():
    result = scan_output("The account balance is 500 dollars.", "support_agent", [])
    assert result["blocked"] is False
    assert result["reasons"] == []


def test_system_prompt_canary_blocks():
    result = scan_output("Internal marker: CANARY-SYSPROMPT", "support_agent", [])
    assert result["blocked"] is True
    assert "canary" in result["reasons"][0].lower()
    assert result["text"] == ""


def test_document_canary_blocks():
    result = scan_output("Reference: CANARY-L3-0601", "support_agent", [])
    assert result["blocked"] is True


def test_pii_is_redacted_not_blocked():
    result = scan_output(
        "Customer email is john@example.com, phone 555-123-4567.",
        "support_agent",
        [],
    )
    assert result["blocked"] is False
    assert "john@example.com" not in result["text"]
    assert "555-123-4567" not in result["text"]
    assert result["redaction_count"] == 2


def test_verbatim_restricted_chunk_blocks_for_lower_clearance():
    # doc_0601 is clearance 3; support_agent is clearance 1
    leaked_text = SAMPLE_DOCS[2]["text"][:80]
    result = scan_output(leaked_text, "support_agent", SAMPLE_DOCS)
    assert result["blocked"] is True
    assert "doc_0601" in result["reasons"][0]


def test_verbatim_chunk_allowed_for_sufficient_clearance():
    # Same text, but compliance_officer (clearance 3) is allowed to see
    # clearance-3 documents, so this should NOT be blocked as a leak.
    doc_text = SAMPLE_DOCS[2]["text"][:80]
    result = scan_output(doc_text, "compliance_officer", SAMPLE_DOCS)
    assert result["blocked"] is False


def test_empty_context_docs_does_not_crash():
    result = scan_output("Some ordinary answer text.", "support_agent", None)
    assert result["blocked"] is False


def test_card_number_masked_not_blocked():
    # Real, normally-formatted, Luhn-valid card number must be masked, not blocked
    card_text = "Customer payment card is 9800-8963-8346-5782."
    result = scan_output(card_text, "compliance_officer", [])
    assert result["blocked"] is False
    assert "[MASKED_CARD_NUMBER]" in result["text"]
    assert "9800-8963-8346-5782" not in result["text"]
    assert result["redaction_count"] >= 1


def test_repetitive_digit_sequence_blocks():
    # Observed LLM hallucination: long repetitive single-digit hyphen-separated sequence
    garbage = "9-8-0-8-0-7-6-3-8-2-9-8-0-8-0-7-6-3-8-2-9-8-0-8-0-7-6-3-8-2-9-8-0-8-0-7-6-3-8-2"
    result = scan_output(f"The card number is {garbage}", "compliance_officer", [])
    assert result["blocked"] is True
    assert result["text"] == ""
    assert any("repetitive digit sequence" in r for r in result["reasons"])
    assert result["redaction_count"] == 0


def test_short_digit_sequence_not_blocked():
    # Short legitimate digit sequences (e.g. PIN, reference code) must not be blocked
    text = "Your one-time PIN is 1234 and reference is 1-2-3-4."
    result = scan_output(text, "support_agent", [])
    assert result["blocked"] is False
    assert "1234" in result["text"]


def test_clean_prose_passes_unchanged():
    text = "General overdraft protection policy terms and fee schedules apply."
    result = scan_output(text, "support_agent", [])
    assert result["blocked"] is False
    assert result["text"] == text
    assert result["reasons"] == []
