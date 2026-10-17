"""
Seeded synthetic banking data generator for Zero-Exposure RAG.

Generates:
- ~200 customer records with distinct synthetic PII
- ~2000 transactions grouped into 200 transaction documents (clearance 1)
- ~400 customer support notes mapped to doc_type "profile" (clearance 1)
- ~30 policy and FAQ documents (clearance 1)
- ~100 fraud/risk case notes with embedded canaries (clearance 2)
- ~20 regulatory compliance reports with embedded canaries (clearance 3)
- 20 ground-truth query/best-document pairs in data/generated/relevance_fixtures.json

Deterministic: Running with the same seed produces identical output.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from faker import Faker


# Module-level seed constant
SEED: int = 42

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "generated"
SCHEMA_PATH = BASE_DIR / "docs" / "schema.json"


# ---------------------------------------------------------------------------
# Luhn Algorithm Implementation
# ---------------------------------------------------------------------------
def luhn_checksum(digits: str) -> bool:
    """
    Validate a string of digits using the Luhn algorithm (mod 10).
    Rejects strings with invalid length (<13 or >19), non-digits, or all zeros.
    """
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False
    if digits == "0" * len(digits):
        return False

    total = 0
    for i, char in enumerate(digits[::-1]):
        n = int(char)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n

    return total % 10 == 0


def calculate_luhn_check_digit(partial_digits: str) -> int:
    """
    Given partial digits (e.g. 15 digits), compute the single check digit (0-9)
    to append so that the complete number satisfies the Luhn mod 10 checksum.
    """
    total = 0
    # In the completed number, the check digit will be at reverse index 0 (not doubled).
    # Therefore, the last character of partial_digits is at reverse index 1 (doubled), etc.
    for i, char in enumerate(partial_digits[::-1]):
        n = int(char)
        if i % 2 == 0:  # Reverse index 1, 3, 5... in completed string
            n *= 2
            if n > 9:
                n -= 9
        total += n

    return (10 - (total % 10)) % 10


def generate_luhn_card_number(rng: random.Random, prefix: str = "9800") -> str:
    """
    Generate a 16-digit Luhn-valid synthetic payment card number
    using an unassigned synthetic test BIN prefix (9800).
    """
    # 4 digits prefix + 11 digits body + 1 check digit = 16 digits
    body_digits = "".join(str(rng.randint(0, 9)) for _ in range(11))
    partial = prefix + body_digits
    check_digit = calculate_luhn_check_digit(partial)
    full_digits = partial + str(check_digit)
    assert luhn_checksum(full_digits), f"Generated card {full_digits} failed Luhn check"
    return f"{full_digits[0:4]}-{full_digits[4:8]}-{full_digits[8:12]}-{full_digits[12:16]}"


# ---------------------------------------------------------------------------
# Seeded Word-Lists for Deterministic Generation
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Emma", "Frank", "Grace", "Henry",
    "Isabella", "James", "Katherine", "Liam", "Maria", "Nathan", "Olivia", "Peter",
    "Rachel", "Samuel", "Teresa", "Victor", "Wei", "Yuki", "Rohan", "Kishan",
    "Kaustubh", "Kashvith", "Priya", "Rahul", "Elena", "Carlos", "Sophia", "Lucas",
    "Amara", "Tariq", "Fatima", "Chen", "Mei", "Arjun", "Zara", "Marcus",
    "Hannah", "Diego", "Leila", "Dmitri", "Chloe", "Kenji", "Amina", "Mateo"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"
]

MERCHANTS = [
    ("Grocery Mart", "DEBIT", 25.0, 180.0),
    ("Metro Transit", "DEBIT", 2.75, 15.0),
    ("Coffee Corner", "DEBIT", 4.5, 12.0),
    ("City Utility Electric", "DEBIT", 65.0, 210.0),
    ("Online Marketplace", "DEBIT", 15.0, 350.0),
    ("Corner Pharmacy", "DEBIT", 8.5, 75.0),
    ("Fuel Station #42", "DEBIT", 35.0, 85.0),
    ("Direct Deposit Payroll", "CREDIT", 1800.0, 4200.0),
    ("ATM Cash Withdrawal", "DEBIT", 40.0, 300.0),
    ("Mobile Transfer Inward", "CREDIT", 50.0, 500.0),
    ("Streaming Entertainment", "DEBIT", 9.99, 19.99),
    ("Dine-In Restaurant", "DEBIT", 32.0, 145.0),
    ("Bookstore POS", "DEBIT", 12.5, 60.0),
    ("Hardware Supply", "DEBIT", 18.0, 220.0),
    ("Investment Dividend", "CREDIT", 25.0, 150.0),
]


# ---------------------------------------------------------------------------
# Generator Functions
# ---------------------------------------------------------------------------
def generate_customers(count: int = 200, rng: random.Random | None = None) -> list[dict[str, Any]]:
    """
    Generate synthetic customer records with unique synthetic PII.
    """
    if rng is None:
        rng = random.Random(SEED)

    customers = []
    for i in range(1, count + 1):
        cid = f"c_{i:03d}"
        first_name = FIRST_NAMES[(i - 1) % len(FIRST_NAMES)]
        last_name = LAST_NAMES[((i - 1) * 3) % len(LAST_NAMES)]
        acc_num = f"ACC-{90000000 + i:08d}"
        card_num = generate_luhn_card_number(rng, prefix="9800")
        phone = f"+1-555-{1000 + i:04d}"
        email = f"{first_name.lower()}.{last_name.lower()}{i:03d}@synthetic-ibz.example.com"
        # Synthetic national ID: clearly artificial format
        nat_id = f"SYN-900-{(i // 100):02d}-{1000 + i:04d}"

        customers.append({
            "customer_id": cid,
            "first_name": first_name,
            "last_name": last_name,
            "name": f"{first_name} {last_name}",
            "account_number": acc_num,
            "card_number": card_num,
            "phone": phone,
            "email": email,
            "national_id": nat_id,
        })

    return customers


def generate_transaction_documents(
    customers: list[dict[str, Any]],
    start_doc_id: int,
    rng: random.Random
) -> list[dict[str, Any]]:
    """
    Generate ~200 transaction documents (one per customer, clearance 1),
    grouping ~2000 total individual transactions across all customers.
    """
    docs = []
    current_doc_id = start_doc_id

    for customer in customers:
        doc_id = f"doc_{current_doc_id:04d}"
        # Exactly 10 transactions per customer = 2000 total transactions across 200 customers
        tx_lines = []
        for tx_idx in range(1, 11):
            merchant, tx_type, min_amt, max_amt = rng.choice(MERCHANTS)
            amount = round(rng.uniform(min_amt, max_amt), 2)
            day = (tx_idx * 2) % 28 + 1
            month = 9 if tx_idx <= 5 else 10
            date_str = f"2026-{month:02d}-{day:02d}"
            tx_lines.append(
                f"  - {date_str} | {tx_type:<6} | ${amount:>8.2f} | {merchant} | Status: POSTED"
            )

        text = (
            f"Transaction history and activity ledger for customer {customer['name']} "
            f"(Customer ID: {customer['customer_id']}, Account: {customer['account_number']}). "
            f"Card ending in {customer['card_number'][-4:]}.\n"
            f"Recent posted transactions:\n" + "\n".join(tx_lines)
        )

        docs.append({
            "doc_id": doc_id,
            "doc_type": "transactions",
            "clearance": 1,
            "customer_id": customer["customer_id"],
            "text": text,
        })
        current_doc_id += 1

    return docs


def generate_support_notes(
    customers: list[dict[str, Any]],
    start_doc_id: int,
    rng: random.Random
) -> list[dict[str, Any]]:
    """
    Generate ~400 customer support notes (2 per customer, clearance 1).
    Mapped to doc_type 'profile' per schema enum specification.
    """
    docs = []
    current_doc_id = start_doc_id

    interactions = [
        ("Online banking password reset", "Customer requested assistance with online portal access. Identity verified via registered phone {phone}. Temporary credentials issued."),
        ("Travel notification notice", "Customer notified customer service of upcoming travel. Debit card {card} enabled for regional transactions through end of month."),
        ("Direct deposit setup inquiry", "Customer inquired about routing and account number verification for payroll deposit into account {acc}. Instructions provided."),
        ("Debit card replacement request", "Customer reported minor physical wear on payment card {card}. Replacement debit card dispatched via standard postal delivery."),
        ("Address change verification", "Customer submitted updated mailing address documentation. Verification completed successfully by customer service representative."),
        ("Electronic statement preference", "Customer requested transition from paper statements to paperless e-delivery. Preferences updated in customer profile."),
        ("Overdraft fee explanation call", "Customer called regarding overdraft protection mechanics for account {acc}. Courtesy fee adjustment applied per customer loyalty policy."),
        ("Wire transfer limits query", "Customer requested details on outgoing domestic wire transfer limits and daily cutoff times. Customer satisfied with explanation."),
    ]

    for customer in customers:
        # 2 support notes per customer = 400 support notes across 200 customers
        for note_idx in range(2):
            doc_id = f"doc_{current_doc_id:04d}"
            int_id = int(customer["customer_id"].split("_")[1])
            topic, template = interactions[(int_id + note_idx) % len(interactions)]
            details = template.format(
                phone=customer["phone"],
                card=customer["card_number"],
                acc=customer["account_number"],
            )
            day = 5 + (note_idx * 12)
            text = (
                f"Customer Service Note: {topic} for {customer['name']} "
                f"(Customer ID: {customer['customer_id']}, Account: {customer['account_number']}). "
                f"Date: 2026-09-{day:02d}. Representative notes: {details} "
                f"Contact on file: {customer['email']}. Follow-up status: Closed."
            )

            docs.append({
                "doc_id": doc_id,
                "doc_type": "profile",
                "clearance": 1,
                "customer_id": customer["customer_id"],
                "text": text,
            })
            current_doc_id += 1

    return docs


def generate_policy_and_faq_docs(start_doc_id: int) -> list[dict[str, Any]]:
    """
    Generate 30 bank-wide policy and FAQ documents (clearance 1, customer_id: null).
    15 policy documents and 15 FAQ documents.
    """
    policies = [
        ("Daily ATM Withdrawal Limits",
         "The daily cash withdrawal limit at all affiliated and network ATM terminals is $1,000 per 24-hour cycle for standard checking accounts, and $2,500 for premier accounts. Limit resets at 12:00 AM midnight EST."),
        ("Wire Transfer Processing Rules and Deadlines",
         "Domestic wire transfers initiated prior to the 4:00 PM EST daily cutoff are processed same business day. International wires require two business days. The maximum single-day domestic wire limit is $50,000 for verified retail accounts."),
        ("Overdraft Protection and NSF Fee Schedule",
         "An overdraft fee of $35 is assessed per non-sufficient funds transaction that the bank covers, with a strict maximum of 3 fees assessed per business day. Overdraft protection transfers from linked savings incur no charge."),
        ("Mobile Check Deposit Thresholds and Availability",
         "Mobile check deposit is subject to a daily limit of $5,000 and a rolling 30-day limit of $25,000. Funds deposited before 6:00 PM EST are typically made available on the next business day."),
        ("Foreign Transaction Fees and Currency Conversion",
         "Point-of-sale transactions and ATM withdrawals processed outside the United States incur a foreign transaction surcharge of 3.0% (consisting of 1.0% payment network fee and 2.0% bank international service fee)."),
        ("Dormant and Abandoned Account Policy",
         "Deposit accounts with zero customer-initiated transactions for a continuous period of 24 months are classified as dormant. Dormant accounts cease recurring service fees and require identity re-verification to reactivate."),
        ("Dispute Resolution and Chargeback Timelines",
         "Customers must notify the bank of any unauthorized charges or billing disputes within 60 calendar days of the statement delivery date. Provisional credit is provided within 10 business days for eligible investigations."),
        ("Credit Card Minimum Payment Calculations",
         "The minimum monthly credit card payment is computed as the greater of $25 or 1% of the total statement balance plus all newly billed finance charges and late payment fees."),
        ("Savings Account Withdrawal Restrictions (Reg D)",
         "Savings and money market accounts permit up to six convenient transfers or withdrawals per calendar month. Transactions exceeding this threshold may incur an excess withdrawal fee of $15 per occurrence."),
        ("Certificate of Deposit Early Withdrawal Penalties",
         "Early redemption of a Certificate of Deposit with a maturity term of 12 months or less incurs a penalty equal to 90 days of simple interest. Terms exceeding 12 months incur 180 days of simple interest."),
        ("Business Account Documentation Requirements",
         "Opening a commercial or small business checking account requires filed Articles of Incorporation, an active Employer Identification Number (EIN) verification letter from the IRS, and valid government IDs for all beneficial owners holding 25% or greater equity."),
        ("Automated Fraud Lock Protocol",
         "Card transactions exhibiting anomalous velocity, unexpected foreign geography, or rapid repeated declines trigger an automated temporary fraud lock. The cardholder receives immediate two-way SMS notification to confirm or dispute transactions."),
        ("Password Security and MFA Requirements",
         "Digital banking passwords must be at least 12 characters, include upper and lower case letters, numbers, and a special symbol. Passwords expire every 90 days. Multi-factor authentication is required for all new device logins."),
        ("Safe Deposit Box Access and Surrender Procedures",
         "Safe deposit vault entry requires dual-key authorization with bank staff presence and physical signature matching the vault roster card. Non-payment after 180 days initiates formal statutory drilled-box surrender."),
        ("Deposit Interest Rate Calculation Methodology",
         "Interest on interest-bearing deposit products is calculated using the daily balance method, applying 1/365th of the annual percentage yield to the end-of-day ledger balance, compounded daily and credited on the final business day of each month.")
    ]

    faqs = [
        ("How do I report a lost or stolen payment card?",
         "If your debit or credit card is lost or stolen, immediately lock the card via the mobile banking security tab or call the 24/7 hotline at 1-800-555-0199. A replacement card will be issued and expedited within 3 business days."),
        ("What should I do if I forgot my mobile banking PIN?",
         "You can securely reset your mobile banking passcode or debit PIN by navigating to the mobile app sign-in screen, selecting 'Forgot PIN', and verifying your identity with an SMS one-time passcode and card CVV."),
        ("How long do standard ACH direct transfers take?",
         "Standard Automated Clearing House (ACH) transfers between external financial institutions typically complete within 2 to 3 business days. Same-day ACH transfers submitted before 1:00 PM EST arrive by 5:00 PM EST."),
        ("How can I request official paper bank statements?",
         "Paper statements can be requested for any previous 7-year cycle through the document repository in online banking or at any physical branch. Official stamped copies carry a nominal archival fee of $5 per statement."),
        ("Are cashier's checks available at branch locations?",
         "Yes, certified cashier's checks are available upon request at all branch teller windows during regular banking hours. There is an $8 fee per check, which is waived for premier account tier holders."),
        ("What happens when a recurring direct deposit falls on a weekend or holiday?",
         "When a scheduled direct deposit payment falls on a federal banking holiday or weekend, funds are credited and accessible on the immediate preceding business day."),
        ("Can I link external financial accounts for automated savings?",
         "Yes, external checking and savings accounts can be linked using micro-deposit verification or instant credential verification, enabling automated scheduled transfers and round-up savings rules."),
        ("How do I configure account alerts for low balance and large transactions?",
         "Account notifications can be personalized in the Alerts Center. You can establish custom thresholds for balance warnings, transaction receipts over $100, and real-time payment alerts via email and SMS text."),
        ("What forms of identification are accepted for branch transactions?",
         "Acceptable government photo identification includes a valid state driver's license, state ID card, US Passport, permanent resident card, or military photo identification."),
        ("How do I update my primary residential or mailing address?",
         "Primary address changes can be submitted through the customer profile settings with two-factor authentication, or in person at any branch location with proof of residency (e.g. recent utility bill)."),
        ("What is the formal procedure for closing a checking account?",
         "Accounts with a zero or positive balance can be closed by contacting customer support or visiting a branch. Any remaining balance is disbursed via cashier's check or transferred to a designated destination account."),
        ("Does opening a new savings account result in a hard credit inquiry?",
         "Opening a standard savings or deposit checking account only requires a soft identity verification check and does not adversely affect your credit score."),
        ("How can I re-order personalized paper checks?",
         "Replacement checkbooks can be ordered directly through online banking under the Account Services tab, choosing from standard or security-enhanced check stock with delivery in 7 to 10 business days."),
        ("What are the fees associated with sending an outgoing domestic wire?",
         "Outgoing domestic wire transfers carry a processing fee of $25 per wire. Outgoing international wires in foreign currency carry a $40 fee."),
        ("What immediate actions should I take if an unauthorized transaction appears?",
         "If you observe an unrecognized transaction, lock your card immediately in the mobile app, review recent pending charges, and submit an unauthorized transaction claim through the dispute center.")
    ]

    docs = []
    current_doc_id = start_doc_id

    # 15 Policies
    for title, body in policies:
        doc_id = f"doc_{current_doc_id:04d}"
        text = f"Bank Operational Policy: {title}.\n{body}"
        docs.append({
            "doc_id": doc_id,
            "doc_type": "policy",
            "clearance": 1,
            "customer_id": None,
            "text": text,
        })
        current_doc_id += 1

    # 15 FAQs
    for question, answer in faqs:
        doc_id = f"doc_{current_doc_id:04d}"
        text = f"Frequently Asked Question: {question}\nAnswer: {answer}"
        docs.append({
            "doc_id": doc_id,
            "doc_type": "faq",
            "clearance": 1,
            "customer_id": None,
            "text": text,
        })
        current_doc_id += 1

    return docs


def generate_case_notes(
    customers: list[dict[str, Any]],
    start_doc_id: int,
    count: int = 100,
    rng: random.Random | None = None
) -> list[dict[str, Any]]:
    """
    Generate ~100 fraud/AML case notes at clearance 2.
    Embeds unique canary strings in the form: CANARY-L2-{digits from doc_id}.
    Follows sample format: '...Internal reference: CANARY-L2-{digits}.'
    """
    if rng is None:
        rng = random.Random(SEED)

    case_scenarios = [
        ("Suspicious transaction velocity", "Fraud investigation opened for customer {cid} following three rapid consecutive high-value transactions in different geographic locations. Account flagged for manual analyst review."),
        ("Potential payment card skimming", "Security case initiated for customer {cid} after compromised POS terminal notification from card network. Card {card} disabled and replacement issued. Monitoring ongoing."),
        ("Anomalous international wire attempt", "AML risk case opened for customer {cid} regarding outgoing wire of $14,500 to newly registered offshore beneficiary. Transaction held pending beneficial ownership verification."),
        ("Account takeover attempt alert", "Authentication security review for customer {cid} after multiple failed login attempts from unrecognized IP range. Online banking access locked and identity re-verification dispatched."),
        ("Unusual deposit and rapid liquidation", "Risk alert generated for customer {cid} following sudden cash deposit of $9,800 followed by immediate cashier check issuance. Transaction patterns flagged for SAR review."),
        ("Check alteration suspicion", "Check fraud review for customer {cid} regarding altered payee name on check #1042. Item returned unpaid to presenting institution. Account notes updated.")
    ]

    docs = []
    current_doc_id = start_doc_id

    for i in range(count):
        doc_id = f"doc_{current_doc_id:04d}"
        customer = customers[i % len(customers)]
        digits = f"{current_doc_id:04d}"
        canary = f"CANARY-L2-{digits}"

        scenario_title, scenario_tmpl = case_scenarios[i % len(case_scenarios)]
        body = scenario_tmpl.format(
            cid=customer["customer_id"],
            card=customer["card_number"],
            acc=customer["account_number"],
        )
        text = (
            f"Case Note: {scenario_title} regarding customer {customer['customer_id']}. "
            f"Account: {customer['account_number']}. Status: UNDER_REVIEW. "
            f"{body} Internal reference: {canary}."
        )

        docs.append({
            "doc_id": doc_id,
            "doc_type": "case_note",
            "clearance": 2,
            "customer_id": customer["customer_id"],
            "text": text,
        })
        current_doc_id += 1

    return docs


def generate_compliance_reports(
    customers: list[dict[str, Any]],
    start_doc_id: int,
    count: int = 20,
    rng: random.Random | None = None
) -> list[dict[str, Any]]:
    """
    Generate ~20 regulatory compliance reports at clearance 3.
    Embeds unique canary strings in the form: CANARY-L3-{digits from doc_id}.
    Follows convention: 'Compliance reference: CANARY-L3-{digits}.'
    """
    if rng is None:
        rng = random.Random(SEED)

    report_templates = [
        ("BSA/AML Suspicious Activity Filing", True, "Comprehensive regulatory examination of customer {cid} transactions exhibiting structured cash deposits below BSA thresholds. Detailed audit logs, SAR filing records, and transaction receipts compiled for regulatory review."),
        ("Quarterly OFAC Sanctions Screening Audit", False, "Quarterly institutional audit reviewing automatic screening logs against updated OFAC SDN list and PEP databases. Zero false-negative breaches detected during the quarterly examination period."),
        ("High-Risk Customer Account Review", True, "Annual enhanced due diligence review for high-risk customer account {cid}. Verification of source of funds, international counterparty risk, and documentation standards verified."),
        ("Consumer Financial Protection Compliance Report", False, "Institutional examination evaluating adherence to CFPB Regulation E error-resolution procedures and disclosure compliance across all retail deposit accounts."),
        ("FinCEN Currency Transaction Report Summary", False, "Monthly compliance summary detailing all cash currency transactions exceeding statutory $10,000 threshold filed with FinCEN under Bank Secrecy Act requirements.")
    ]

    docs = []
    current_doc_id = start_doc_id

    for i in range(count):
        doc_id = f"doc_{current_doc_id:04d}"
        digits = f"{current_doc_id:04d}"
        canary = f"CANARY-L3-{digits}"

        title, is_customer_specific, tmpl = report_templates[i % len(report_templates)]
        if is_customer_specific:
            customer = customers[(i * 7) % len(customers)]
            cid = customer["customer_id"]
            body = tmpl.format(cid=cid)
        else:
            cid = None
            body = tmpl

        text = (
            f"Regulatory Compliance Report: {title}. Period: Q3-2026. "
            f"Classification: Strictly Confidential / Restricted Clearance. "
            f"{body} Compliance reference: {canary}."
        )

        docs.append({
            "doc_id": doc_id,
            "doc_type": "compliance_report",
            "clearance": 3,
            "customer_id": cid,
            "text": text,
        })
        current_doc_id += 1

    return docs


# ---------------------------------------------------------------------------
# Relevance Fixtures Generator (20 pairs)
# ---------------------------------------------------------------------------
def generate_relevance_fixtures(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Generate exactly 20 {query, best_doc_id} pairs with verified ground truth
    across policy, FAQ, case notes, and compliance reports.
    """
    doc_by_id = {d["doc_id"]: d for d in documents}

    # Explicit ground-truth pairs targeting unique generated documents
    fixtures = [
        # Policy & FAQ (10 pairs)
        {"query": "What is the daily ATM withdrawal limit for standard checking accounts?", "best_doc_id": "doc_0001"},
        {"query": "What is the cutoff time and daily limit for domestic wire transfers?", "best_doc_id": "doc_0002"},
        {"query": "What is the fee assessed per overdraft transaction and the daily maximum?", "best_doc_id": "doc_0003"},
        {"query": "What are the daily and monthly deposit thresholds for mobile check deposits?", "best_doc_id": "doc_0004"},
        {"query": "What percentage surcharge is applied to foreign point-of-sale transactions?", "best_doc_id": "doc_0005"},
        {"query": "After how many months of zero transactions is an account declared dormant?", "best_doc_id": "doc_0006"},
        {"query": "Within how many days must a customer notify the bank of an unauthorized dispute?", "best_doc_id": "doc_0007"},
        {"query": "How is the minimum monthly credit card payment calculated?", "best_doc_id": "doc_0008"},
        {"query": "How many monthly transfers are permitted from a savings account under Reg D?", "best_doc_id": "doc_0009"},
        {"query": "What is the penalty for early withdrawal from a certificate of deposit under one year?", "best_doc_id": "doc_0010"},
        # Case notes (5 pairs)
        {"query": "Why was a suspicious transaction velocity fraud case opened for customer c_001?", "best_doc_id": "doc_0631"},
        {"query": "What security case was initiated regarding payment card skimming for customer c_002?", "best_doc_id": "doc_0632"},
        {"query": "What triggered the AML risk case for an anomalous international wire for customer c_003?", "best_doc_id": "doc_0633"},
        {"query": "What caused the account takeover attempt alert for customer c_004?", "best_doc_id": "doc_0634"},
        {"query": "Why was a check alteration fraud case opened regarding check #1042 for customer c_006?", "best_doc_id": "doc_0636"},
        # Compliance reports (5 pairs)
        {"query": "What were the findings of the BSA/AML structured cash deposit examination in report doc_0731?", "best_doc_id": "doc_0731"},
        {"query": "What did the quarterly OFAC sanctions screening audit conclude regarding false negatives?", "best_doc_id": "doc_0732"},
        {"query": "What enhanced due diligence findings were documented for high-risk customer account review doc_0733?", "best_doc_id": "doc_0733"},
        {"query": "What did the Consumer Financial Protection compliance report evaluate regarding Regulation E?", "best_doc_id": "doc_0734"},
        {"query": "What statutory threshold is covered in the FinCEN Currency Transaction Report summary doc_0735?", "best_doc_id": "doc_0735"},
    ]

    # Verify that all 20 targeted documents exist in the corpus
    for f in fixtures:
        assert f["best_doc_id"] in doc_by_id, f"Fixture target {f['best_doc_id']} missing from generated documents"

    assert len(fixtures) == 20, f"Expected 20 fixtures, got {len(fixtures)}"
    return fixtures


# ---------------------------------------------------------------------------
# Schema Validator (Standard Library / jsonschema Compatible)
# ---------------------------------------------------------------------------
def validate_document_against_schema(doc: dict[str, Any], schema: dict[str, Any]) -> None:
    """
    Validate a single document against docs/schema.json constraints
    using Python standard library logic.
    """
    # Check required fields
    required_fields = schema.get("required", [])
    for field in required_fields:
        if field not in doc:
            raise ValueError(f"Missing required field '{field}' in doc: {doc}")

    # Check additional properties
    if not schema.get("additionalProperties", True):
        for k in doc:
            if k not in schema.get("properties", {}):
                raise ValueError(f"Unexpected additional property '{k}' in doc {doc.get('doc_id')}")

    # Validate doc_id
    doc_id = doc["doc_id"]
    if not isinstance(doc_id, str) or not re.match(r"^doc_[0-9]{4}$", doc_id):
        raise ValueError(f"Invalid doc_id format: {doc_id}")

    # Validate doc_type
    doc_type = doc["doc_type"]
    allowed_types = schema["properties"]["doc_type"]["enum"]
    if doc_type not in allowed_types:
        raise ValueError(f"Invalid doc_type '{doc_type}', expected one of {allowed_types}")

    # Validate clearance
    clearance = doc["clearance"]
    allowed_clearance = schema["properties"]["clearance"]["enum"]
    if clearance not in allowed_clearance:
        raise ValueError(f"Invalid clearance '{clearance}', expected one of {allowed_clearance}")

    # Validate customer_id
    customer_id = doc["customer_id"]
    if customer_id is not None:
        if not isinstance(customer_id, str) or not re.match(r"^c_[0-9]+$", customer_id):
            raise ValueError(f"Invalid customer_id format: {customer_id}")

    # Validate text
    text = doc["text"]
    if not isinstance(text, str) or len(text) < 1:
        raise ValueError(f"Invalid text field in doc {doc_id}: must be non-empty string")


def validate_all_documents(documents: list[dict[str, Any]], schema_path: Path) -> None:
    """
    Validate all documents against docs/schema.json.
    """
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    for doc in documents:
        validate_document_against_schema(doc, schema)


# ---------------------------------------------------------------------------
# Main Orchestration
# ---------------------------------------------------------------------------
def generate_all(seed: int = SEED) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    """
    Orchestrate full synthetic data generation:
    Returns (customers, documents, relevance_fixtures).
    """
    # Seed both Faker and random
    Faker.seed(seed)
    random.seed(seed)
    rng = random.Random(seed)

    # 1. Generate 200 customers
    customers = generate_customers(count=200, rng=rng)

    # 2. Generate documents in deterministic sequence
    # 2.1 Policy & FAQ (30 docs: doc_0001 to doc_0030)
    policy_faq_docs = generate_policy_and_faq_docs(start_doc_id=1)

    # 2.2 Transactions (200 docs: doc_0031 to doc_0230)
    tx_docs = generate_transaction_documents(customers, start_doc_id=31, rng=rng)

    # 2.3 Support Notes / Profile (400 docs: doc_0231 to doc_0630)
    support_docs = generate_support_notes(customers, start_doc_id=231, rng=rng)

    # 2.4 Case notes (100 docs: doc_0631 to doc_0730)
    case_docs = generate_case_notes(customers, start_doc_id=631, count=100, rng=rng)

    # 2.5 Compliance reports (20 docs: doc_0731 to doc_0750)
    comp_docs = generate_compliance_reports(customers, start_doc_id=731, count=20, rng=rng)

    all_docs = policy_faq_docs + tx_docs + support_docs + case_docs + comp_docs

    # 3. Generate relevance fixtures
    fixtures = generate_relevance_fixtures(all_docs)

    return customers, all_docs, fixtures


def main() -> None:
    """
    CLI entry point. Generates data, validates against schema, and writes outputs.
    """
    print(f"[generate.py] Starting synthetic data generation with SEED={SEED}...")
    customers, documents, fixtures = generate_all(seed=SEED)

    # Validate against docs/schema.json
    print(f"[generate.py] Validating {len(documents)} documents against schema {SCHEMA_PATH}...")
    validate_all_documents(documents, SCHEMA_PATH)

    # Verify canary invariants
    canaries = []
    for d in documents:
        if d["clearance"] in (2, 3):
            # Check canary presence
            m = re.search(r"CANARY-L[23]-\d{4}", d["text"])
            if not m:
                raise ValueError(f"Document {d['doc_id']} clearance {d['clearance']} is missing canary string!")
            canaries.append(m.group(0))
        else:
            if "CANARY" in d["text"]:
                raise ValueError(f"Clearance 1 document {d['doc_id']} improperly contains a CANARY token!")

    # Check canary uniqueness
    if len(canaries) != len(set(canaries)):
        raise ValueError("Detected duplicate canary strings across documents!")
    print(f"[generate.py] Verified {len(canaries)} unique canaries across clearance 2 and 3 documents.")

    # Write output files
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    docs_file = OUTPUT_DIR / "documents.json"
    fixtures_file = OUTPUT_DIR / "relevance_fixtures.json"
    customers_file = OUTPUT_DIR / "customers.json"

    print(f"[generate.py] Writing documents to {docs_file}...")
    with open(docs_file, "w", encoding="utf-8", newline="\n") as f:
        json.dump(documents, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[generate.py] Writing relevance fixtures to {fixtures_file}...")
    with open(fixtures_file, "w", encoding="utf-8", newline="\n") as f:
        json.dump(fixtures, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[generate.py] Writing customer records to {customers_file}...")
    with open(customers_file, "w", encoding="utf-8", newline="\n") as f:
        json.dump(customers, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[generate.py] Successfully generated:")
    print(f"  - Customers: {len(customers)}")
    print(f"  - Documents: {len(documents)}")
    print(f"    * Transactions: {sum(1 for d in documents if d['doc_type'] == 'transactions')}")
    print(f"    * Profile/Support: {sum(1 for d in documents if d['doc_type'] == 'profile')}")
    print(f"    * Policy: {sum(1 for d in documents if d['doc_type'] == 'policy')}")
    print(f"    * FAQ: {sum(1 for d in documents if d['doc_type'] == 'faq')}")
    print(f"    * Case notes (clearance 2): {sum(1 for d in documents if d['doc_type'] == 'case_note')}")
    print(f"    * Compliance reports (clearance 3): {sum(1 for d in documents if d['doc_type'] == 'compliance_report')}")
    print(f"  - Relevance fixtures: {len(fixtures)}")


if __name__ == "__main__":
    main()
