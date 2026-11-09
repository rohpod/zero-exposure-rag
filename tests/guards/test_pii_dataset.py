"""Every generated customer's PII must be detected in full and redacted per role."""
import json
from pathlib import Path

import pytest

from app.guards.pii import detect, redact

CUSTOMERS_PATH = Path(__file__).resolve().parents[2] / "data" / "generated" / "customers.json"
CUSTOMERS = json.loads(CUSTOMERS_PATH.read_text())

FIELD_TYPES = {
    "name": "full_name",
    "phone": "phone",
    "email": "email",
    "account_number": "account_number",
    "card_number": "card_number",
    "national_id": "national_id",
}


def _sentence(c: dict) -> str:
    return (
        f"Customer {c['name']} can be reached on {c['phone']} or {c['email']}; "
        f"account {c['account_number']}, card {c['card_number']}, ID {c['national_id']}."
    )


def test_detect_finds_every_field_with_full_span():
    for c in CUSTOMERS:
        found = {(d["type"], d["text"]) for d in detect(_sentence(c))}
        for field, pii_type in FIELD_TYPES.items():
            assert (pii_type, c[field]) in found, (c["customer_id"], field)


def test_phone_with_dash_country_code_is_detected():
    found = detect("Call +1-555-1001 today")
    assert [(d["type"], d["text"]) for d in found] == [("phone", "+1-555-1001")]


@pytest.mark.parametrize("role", ["support_agent", "fraud_analyst", "compliance_officer"])
def test_redact_applies_role_policy_to_every_customer(role):
    policy = json.loads((Path(__file__).resolve().parents[2] / "app/guards/policy.json").read_text())[role]
    for c in CUSTOMERS:
        out = redact(_sentence(c), role)["text"]
        assert c["card_number"] not in out
        for field, pii_type in FIELD_TYPES.items():
            action = "mask" if pii_type == "card_number" else policy[pii_type]
            if action == "show":
                assert c[field] in out
            else:
                assert c[field] not in out, (role, c["customer_id"], field)
        if role == "support_agent":
            assert "[MASKED_FULL_NAME]" in out
