"""
Unit tests for PII detection and redaction guard.

Zero-Exposure RAG | IBM Z Datathon 2026
NOTE: All test data is strictly synthetic/fake. No real personal data is used,
per project contributing guidelines.
"""
import pytest

from app.guards.pii import detect, luhn_checksum, redact


# ===========================================================================
# 1. Luhn Checksum Tests
# ===========================================================================
def test_luhn_checksum_valid_synthetic_cards():
    """Valid synthetic card numbers must pass Luhn verification."""
    # Standard synthetic test cards
    assert luhn_checksum("4532015112830366") is True
    assert luhn_checksum("4111111111111111") is True
    assert luhn_checksum("378282246310005") is True  # 15-digit Amex test


def test_luhn_checksum_invalid_synthetic_cards():
    """Invalid card numbers or failed check digits must be rejected."""
    # Checksum altered by 1
    assert luhn_checksum("4532015112830367") is False
    assert luhn_checksum("4111111111111112") is False
    # All zeros
    assert luhn_checksum("0000000000000000") is False
    # Too short or too long
    assert luhn_checksum("12345") is False
    assert luhn_checksum("123456789012345678901") is False
    # Non-digit
    assert luhn_checksum("411111111111111A") is False


# ===========================================================================
# 2. Individual PII Type Detection & Offset Tests
# ===========================================================================
def test_detect_card_number_valid():
    """Valid Luhn card numbers (formatted or plain) must be detected as card_number."""
    text = "Payment received from card 4532-0151-1283-0366 via terminal."
    found = detect(text)
    assert len(found) == 1
    item = found[0]
    assert item["type"] == "card_number"
    assert item["text"] == "4532-0151-1283-0366"
    assert text[item["start"]:item["end"]] == item["text"]


def test_detect_card_number_invalid_rejected():
    """Numbers that fail the Luhn checksum must NOT be flagged as card_number."""
    text = "Invalid card candidate 4532-0151-1283-0367 was declined."
    found = detect(text)
    # The invalid card number must not be detected as card_number
    card_detections = [d for d in found if d["type"] == "card_number"]
    assert len(card_detections) == 0


def test_detect_account_number():
    """Account numbers with explicit prefix or contextual label must be detected."""
    text1 = "Customer account ACC-98765432 was updated."
    found1 = detect(text1)
    acc1 = [d for d in found1 if d["type"] == "account_number"]
    assert len(acc1) == 1
    assert acc1[0]["text"] == "ACC-98765432"
    assert text1[acc1[0]["start"]:acc1[0]["end"]] == acc1[0]["text"]

    text2 = "Please verify account number 987654321 for the caller."
    found2 = detect(text2)
    acc2 = [d for d in found2 if d["type"] == "account_number"]
    assert len(acc2) == 1
    assert acc2[0]["text"] == "987654321"
    assert text2[acc2[0]["start"]:acc2[0]["end"]] == acc2[0]["text"]


def test_detect_phone():
    """Phone numbers in standard formats must be detected with exact offsets."""
    text = "Direct inquiries to +1-555-123-4567 or (555) 987-6543 during hours."
    found = detect(text)
    phone_items = [d for d in found if d["type"] == "phone"]
    assert len(phone_items) == 2

    assert phone_items[0]["text"] == "+1-555-123-4567"
    assert text[phone_items[0]["start"]:phone_items[0]["end"]] == phone_items[0]["text"]

    assert phone_items[1]["text"] == "(555) 987-6543"
    assert text[phone_items[1]["start"]:phone_items[1]["end"]] == phone_items[1]["text"]


def test_detect_email():
    """Email addresses must be detected with exact offsets."""
    text = "Send reports to audit.officer+sec@ibm-datathon.example.org immediately."
    found = detect(text)
    assert len(found) == 1
    item = found[0]
    assert item["type"] == "email"
    assert item["text"] == "audit.officer+sec@ibm-datathon.example.org"
    assert text[item["start"]:item["end"]] == item["text"]


def test_detect_national_id():
    """National IDs (SSN pattern and labeled IDs) must be detected with exact offsets."""
    text1 = "Client identity verified with SSN 123-45-6789."
    found1 = detect(text1)
    nid1 = [d for d in found1 if d["type"] == "national_id"]
    assert len(nid1) == 1
    assert nid1[0]["text"] == "123-45-6789"
    assert text1[nid1[0]["start"]:nid1[0]["end"]] == nid1[0]["text"]

    text2 = "Reference National ID: US88776655 in the file."
    found2 = detect(text2)
    nid2 = [d for d in found2 if d["type"] == "national_id"]
    assert len(nid2) == 1
    assert nid2[0]["text"] == "US88776655"
    assert text2[nid2[0]["start"]:nid2[0]["end"]] == nid2[0]["text"]


def test_detect_first_name():
    """First names from word-list and title context must be detected without NER."""
    text1 = "Alice reviewed the system alert."
    found1 = detect(text1)
    names1 = [d for d in found1 if d["type"] == "first_name"]
    assert len(names1) == 1
    assert names1[0]["text"] == "Alice"
    assert text1[names1[0]["start"]:names1[0]["end"]] == names1[0]["text"]

    text2 = "The support ticket was assigned to Mr. Robert for investigation."
    found2 = detect(text2)
    names2 = [d for d in found2 if d["type"] == "first_name"]
    assert len(names2) == 1
    assert names2[0]["text"] == "Robert"
    assert text2[names2[0]["start"]:names2[0]["end"]] == names2[0]["text"]


def test_detect_overlap_resolution():
    """Sub-tokens (like a name inside an email or numbers inside a card) must not trigger overlapping detections."""
    text = "Send confirmation to alice@example.com immediately."
    found = detect(text)
    # alice@example.com is an email; 'alice' must not be separately detected as a first_name
    assert len(found) == 1
    assert found[0]["type"] == "email"
    assert found[0]["text"] == "alice@example.com"


# ===========================================================================
# 3. Clean String Tests (No PII)
# ===========================================================================
def test_clean_string_no_detections():
    """A clean string with no PII returns no detections and unmodified text."""
    clean_text = "The system operational metrics remained normal during the quarterly audit."
    found = detect(clean_text)
    assert found == []

    for role in ["support_agent", "fraud_analyst", "compliance_officer"]:
        result = redact(clean_text, role)
        assert result["text"] == clean_text
        assert result["found"] == []


def test_empty_string():
    """Empty strings are handled gracefully."""
    assert detect("") == []
    for role in ["support_agent", "fraud_analyst", "compliance_officer"]:
        result = redact("", role)
        assert result["text"] == ""
        assert result["found"] == []


# ===========================================================================
# 4. Role-based Redaction Tests (Matching policy.json)
# ===========================================================================
@pytest.fixture
def sample_pii_text():
    """Comprehensive synthetic text containing all 6 supported PII types."""
    return (
        "Customer Alice (SSN: 123-45-6789) holds account ACC-98765432 and card "
        "4532-0151-1283-0366. Contact at alice@example.com or +1-555-123-4567."
    )


def test_redact_support_agent(sample_pii_text):
    """
    support_agent policy:
      - first_name: show
      - account_number: last_four
      - card_number: mask
      - phone: remove
      - email: remove
      - national_id: remove
    """
    res = redact(sample_pii_text, role="support_agent")
    redacted = res["text"]

    # first_name: show
    assert "Alice" in redacted

    # account_number: last_four (ACC-98765432 -> ********5432)
    assert "5432" in redacted
    assert "98765432" not in redacted
    assert "ACC-98765432" not in redacted

    # card_number: mask
    assert "[MASKED_CARD_NUMBER]" in redacted
    assert "4532-0151-1283-0366" not in redacted

    # national_id, email, phone: remove entirely
    assert "123-45-6789" not in redacted
    assert "alice@example.com" not in redacted
    assert "+1-555-123-4567" not in redacted

    assert len(res["found"]) == 6


def test_redact_fraud_analyst(sample_pii_text):
    """
    fraud_analyst policy:
      - first_name: show
      - account_number: show
      - card_number: mask
      - phone: mask
      - email: mask
      - national_id: mask
    """
    res = redact(sample_pii_text, role="fraud_analyst")
    redacted = res["text"]

    # first_name & account_number: show
    assert "Alice" in redacted
    assert "ACC-98765432" in redacted

    # card_number, national_id, email, phone: masked
    assert "[MASKED_CARD_NUMBER]" in redacted
    assert "4532-0151-1283-0366" not in redacted

    assert "[MASKED_NATIONAL_ID]" in redacted
    assert "123-45-6789" not in redacted

    assert "[MASKED_EMAIL]" in redacted
    assert "alice@example.com" not in redacted

    assert "[MASKED_PHONE]" in redacted
    assert "+1-555-123-4567" not in redacted

    assert len(res["found"]) == 6


def test_redact_compliance_officer(sample_pii_text):
    """
    compliance_officer policy:
      - first_name: show
      - account_number: show
      - card_number: mask (hard rule + policy)
      - phone: show
      - email: show
      - national_id: show
    """
    res = redact(sample_pii_text, role="compliance_officer")
    redacted = res["text"]

    # Everything shown EXCEPT card_number
    assert "Alice" in redacted
    assert "ACC-98765432" in redacted
    assert "123-45-6789" in redacted
    assert "alice@example.com" in redacted
    assert "+1-555-123-4567" in redacted

    # card_number: must be masked
    assert "[MASKED_CARD_NUMBER]" in redacted
    assert "4532-0151-1283-0366" not in redacted

    assert len(res["found"]) == 6


# ===========================================================================
# 5. Hard Safety Rule: card_number is ALWAYS masked
# ===========================================================================
def test_hard_safety_rule_card_number_always_masked():
    """Even if policy.json erroneously sets card_number to 'show', it MUST be masked."""
    permissive_policy = {
        "admin": {
            "first_name": "show",
            "account_number": "show",
            "card_number": "show",  # Policy says show, but hard rule forbids it!
            "phone": "show",
            "email": "show",
            "national_id": "show",
        }
    }
    text = "Card number 4532-0151-1283-0366 for member."
    res = redact(text, role="admin", policy=permissive_policy)

    assert "4532-0151-1283-0366" not in res["text"]
    assert "[MASKED_CARD_NUMBER]" in res["text"]


# ===========================================================================
# 6. Error Handling
# ===========================================================================
def test_redact_unknown_role_raises_error():
    """An unknown role must raise a ValueError."""
    with pytest.raises(ValueError, match="Unknown role"):
        redact("Customer data", role="unauthorized_guest")
