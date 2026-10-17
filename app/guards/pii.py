"""
PII Detection and Redaction Guard for Zero-Exposure RAG.

This module implements deterministic, regex and checksum-based PII detection
and role-based redaction with zero external machine learning dependencies,
ensuring 100% portability across architectures (including s390x / LinuxONE).

Interface contract:
    detect(text: str) -> list[dict]
        Each dict: {"type": str, "start": int, "end": int, "text": str}
    redact(text: str, role: str) -> dict
        Returns {"text": str, "found": list}
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Default location for the policy file
DEFAULT_POLICY_PATH = Path(__file__).parent / "policy.json"

_cached_policy: dict[str, dict[str, str]] | None = None


# ---------------------------------------------------------------------------
# Luhn Checksum for Card Numbers
# ---------------------------------------------------------------------------
def luhn_checksum(digits: str) -> bool:
    """
    Validate a string of digits using the Luhn algorithm (mod 10).
    Only returns True for digit strings of valid length (13 to 19 digits)
    with a valid checksum. Rejects all-zero sequences.
    """
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False
    if digits == "0" * len(digits):
        return False

    total = 0
    # Process digits right-to-left
    for i, char in enumerate(digits[::-1]):
        n = int(char)
        # Double every second digit (1st, 3rd, 5th in 0-indexed reverse)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n

    return total % 10 == 0


# ---------------------------------------------------------------------------
# Name Word-List & Context Configuration
# ---------------------------------------------------------------------------
# Comprehensive list of common first names across Western, Latin, Asian,
# Indian, and team domains to allow zero-dependency NER fallback.
FIRST_NAMES: set[str] = {
    # Top Western male names
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Christopher", "Daniel", "Matthew", "Anthony", "Mark",
    "Donald", "Steven", "Paul", "Andrew", "Joshua", "Kenneth", "Kevin", "Brian",
    "George", "Timothy", "Ronald", "Edward", "Jason", "Jeffrey", "Ryan", "Jacob",
    "Gary", "Nicholas", "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott",
    "Brandon", "Benjamin", "Samuel", "Gregory", "Alexander", "Frank", "Patrick",
    "Raymond", "Jack", "Dennis", "Jerry", "Tyler", "Aaron", "Jose", "Adam",
    "Nathan", "Henry", "Douglas", "Zachary", "Peter", "Kyle", "Walter", "Harold",
    "Jeremy", "Ethan", "Carl", "Keith", "Roger", "Gerald", "Christian", "Terry",
    "Sean", "Arthur", "Austin", "Noah", "Lawrence", "Jesse", "Joe", "Bryan",
    "Billy", "Jordan", "Albert", "Dylan", "Bruce", "Willie", "Gabriel", "Alan",
    "Juan", "Logan", "Wayne", "Ralph", "Roy", "Eugene", "Randy", "Vincent",
    "Russell", "Louis", "Philip", "Bobby", "Johnny", "Bradley", "Liam", "Oliver",
    "Lucas", "Elijah", "Mason", "Carter", "Luke", "Henry", "Jack", "Owen",
    # Top Western female names
    "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan",
    "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra",
    "Ashley", "Kimberly", "Emily", "Donna", "Michelle", "Carol", "Amanda",
    "Melissa", "Deborah", "Stephanie", "Rebecca", "Sharon", "Laura", "Cynthia",
    "Kathleen", "Amy", "Angela", "Shirley", "Anna", "Brenda", "Pamela", "Emma",
    "Nicole", "Helen", "Samantha", "Katherine", "Christine", "Debra", "Rachel",
    "Carolyn", "Janet", "Catherine", "Maria", "Heather", "Diane", "Ruth",
    "Julie", "Olivia", "Joyce", "Virginia", "Victoria", "Kelly", "Lauren",
    "Christina", "Joan", "Evelyn", "Judith", "Megan", "Andrea", "Cheryl",
    "Hannah", "Jacqueline", "Martha", "Gloria", "Teresa", "Ann", "Sara",
    "Madison", "Frances", "Kathryn", "Janice", "Jean", "Abigail", "Alice",
    "Julia", "Judy", "Sophia", "Grace", "Denise", "Amber", "Doris", "Marilyn",
    "Danielle", "Beverly", "Isabella", "Theresa", "Diana", "Natalie", "Brittany",
    "Charlotte", "Marie", "Kayla", "Alexis", "Lori", "Mia", "Harper", "Ava",
    "Ella", "Chloe", "Penelope", "Layla", "Nora", "Zoey", "Mila", "Audrey",
    # Diverse & team names
    "Rohan", "Kishan", "Kaustubh", "Kashvith", "Priya", "Rahul", "Amit",
    "Sneha", "Ananya", "Arjun", "Vikram", "Sunil", "Pooja", "Deepak",
    "Carlos", "Elena", "Mateo", "Sofia", "Lucia", "Diego", "Alejandro",
    "Fatima", "Ahmed", "Mohamed", "Ali", "Hassan", "Aisha", "Omar",
    "Wei", "Chen", "Ming", "Yuki", "Kenji", "Hiroshi", "Sakura",
}

# English homonyms that could appear as common verbs/nouns;
# only match them when preceded by an explicit title/context label.
AMBIGUOUS_NAMES: set[str] = {
    "May", "Will", "Mark", "Bill", "Frank", "Grant", "Rose", "Grace", "Jack"
}


# ---------------------------------------------------------------------------
# Regular Expression Patterns
# ---------------------------------------------------------------------------
CARD_CANDIDATE_REGEX = re.compile(
    r'\b(?:\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,7}|\d{4}[ -]\d{6}[ -]\d{4,5}|\d{13,19})\b'
)

EMAIL_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
)

SSN_STANDALONE_REGEX = re.compile(
    r'\b\d{3}-\d{2}-\d{4}\b'
)

NATIONAL_ID_CONTEXT_REGEX = re.compile(
    r'(?i:\b(?:SSN|Social\s*Security(?:\s*Number)?|National[_\s]*ID|NID|SIN|Tax[_\s]*ID)\s*(?:is\s*)?[:#]?\s*)([A-Za-z0-9-]{8,15})\b'
)

PHONE_REGEX = re.compile(
    r'(?<!\d)(?:(?:\+\d{1,3}[-.\s]?)?(?:\(\d{3}\)|\b\d{3})[-.\s]\d{3}[-.\s]\d{4}\b|\+\d{1,3}[-.\s]\d{2,4}[-.\s]\d{3,4}[-.\s]\d{3,4}\b)(?!\d)'
)

ACCOUNT_CONTEXT_REGEX = re.compile(
    r'(?i:\b(?:account(?:[_\s]+(?:number|no\.?|#))?|acct(?:[_\s]*(?:no\.?|#))?)\s*(?:is\s*)?[:#]?\s*)([A-Za-z0-9-]{6,16})\b'
)

ACCOUNT_PREFIX_REGEX = re.compile(
    r'\b(?:ACC|ACCT|ACT)-?[0-9]{6,12}\b',
    re.IGNORECASE
)

TITLE_NAME_REGEX = re.compile(
    r'\b(?:Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.|Customer|Patient|User|Agent|Name:?|Dear)\s+([A-Z][a-z]+)\b'
)

WORD_NAME_REGEX = re.compile(
    r'\b[A-Z][a-z]+\b'
)

# Priority order when resolving overlapping candidate spans.
# More specific / structured types take precedence over broader types.
TYPE_PRIORITY: dict[str, int] = {
    "card_number": 1,
    "email": 2,
    "national_id": 3,
    "phone": 4,
    "account_number": 5,
    "first_name": 6,
}


# ---------------------------------------------------------------------------
# Core Policy Loader
# ---------------------------------------------------------------------------
def load_policy(policy_path: Path | str | None = None) -> dict[str, dict[str, str]]:
    """
    Load the guard policy JSON configuration.
    Defaults to app/guards/policy.json.
    """
    global _cached_policy
    if policy_path is not None:
        path = Path(policy_path)
        if not path.exists():
            raise FileNotFoundError(f"Policy file not found at {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if _cached_policy is None:
        if not DEFAULT_POLICY_PATH.exists():
            raise FileNotFoundError(f"Policy file not found at {DEFAULT_POLICY_PATH}")
        with open(DEFAULT_POLICY_PATH, "r", encoding="utf-8") as f:
            _cached_policy = json.load(f)

    return _cached_policy


# ---------------------------------------------------------------------------
# Detection Engine
# ---------------------------------------------------------------------------
def detect(text: str) -> list[dict[str, Any]]:
    """
    Detect PII entities in the provided text.

    Supported types:
        - card_number   (validated by Luhn checksum)
        - account_number
        - phone
        - email
        - national_id
        - first_name    (regex/word-list fallback)

    Returns:
        List of dicts: [{"type": str, "start": int, "end": int, "text": str}, ...]
        sorted ascending by start offset, with all overlaps resolved.
    """
    if not text:
        return []

    candidates: list[dict[str, Any]] = []

    # 1. card_number: must match structure AND pass Luhn checksum
    for match in CARD_CANDIDATE_REGEX.finditer(text):
        raw_match = match.group(0)
        digits_only = re.sub(r'\D', '', raw_match)
        if luhn_checksum(digits_only):
            candidates.append({
                "type": "card_number",
                "start": match.start(),
                "end": match.end(),
                "text": raw_match,
            })

    # 2. email
    for match in EMAIL_REGEX.finditer(text):
        candidates.append({
            "type": "email",
            "start": match.start(),
            "end": match.end(),
            "text": match.group(0),
        })

    # 3. national_id (SSN and labeled national IDs)
    for match in SSN_STANDALONE_REGEX.finditer(text):
        candidates.append({
            "type": "national_id",
            "start": match.start(),
            "end": match.end(),
            "text": match.group(0),
        })

    for match in NATIONAL_ID_CONTEXT_REGEX.finditer(text):
        candidates.append({
            "type": "national_id",
            "start": match.start(1),
            "end": match.end(1),
            "text": match.group(1),
        })

    # 4. phone
    for match in PHONE_REGEX.finditer(text):
        candidates.append({
            "type": "phone",
            "start": match.start(),
            "end": match.end(),
            "text": match.group(0),
        })

    # 5. account_number (labeled or explicit ACC/ACCT prefix)
    for match in ACCOUNT_CONTEXT_REGEX.finditer(text):
        candidates.append({
            "type": "account_number",
            "start": match.start(1),
            "end": match.end(1),
            "text": match.group(1),
        })

    for match in ACCOUNT_PREFIX_REGEX.finditer(text):
        candidates.append({
            "type": "account_number",
            "start": match.start(),
            "end": match.end(),
            "text": match.group(0),
        })

    # 6. first_name (contextual titles & word-list fallback)
    for match in TITLE_NAME_REGEX.finditer(text):
        name = match.group(1)
        candidates.append({
            "type": "first_name",
            "start": match.start(1),
            "end": match.end(1),
            "text": name,
        })

    for match in WORD_NAME_REGEX.finditer(text):
        word = match.group(0)
        if word in FIRST_NAMES and word not in AMBIGUOUS_NAMES:
            candidates.append({
                "type": "first_name",
                "start": match.start(),
                "end": match.end(),
                "text": word,
            })

    # Resolve overlapping spans:
    # Sort candidates by start ascending, priority rank ascending, length descending
    candidates.sort(key=lambda c: (
        c["start"],
        TYPE_PRIORITY.get(c["type"], 99),
        -(c["end"] - c["start"])
    ))

    filtered: list[dict[str, Any]] = []
    for cand in candidates:
        overlap = False
        for accepted in filtered:
            # Overlap occurs when start of one is before end of other and vice versa
            if max(cand["start"], accepted["start"]) < min(cand["end"], accepted["end"]):
                overlap = True
                break
        if not overlap:
            filtered.append(cand)

    # Sort final detections in strict start offset order
    filtered.sort(key=lambda c: c["start"])
    return filtered


# ---------------------------------------------------------------------------
# Redaction Engine
# ---------------------------------------------------------------------------
def _format_replacement(item: dict[str, Any], action: str) -> str:
    """
    Format the replacement string for a detected entity based on policy action.

    Actions:
        - "show"      -> leave as-is
        - "mask"      -> placeholder [MASKED_<TYPE>]
        - "last_four" -> only last 4 characters visible, earlier characters masked with '*'
        - "remove"    -> strip entirely (empty string)
    """
    raw_text = item["text"]
    pii_type = item["type"]

    if action == "show":
        return raw_text
    elif action == "mask":
        return f"[MASKED_{pii_type.upper()}]"
    elif action == "last_four":
        if len(raw_text) <= 4:
            return raw_text
        return ("*" * (len(raw_text) - 4)) + raw_text[-4:]
    elif action == "remove":
        return ""
    else:
        raise ValueError(f"Unknown redaction action '{action}' for type '{pii_type}'")


def redact(
    text: str,
    role: str,
    policy: dict[str, dict[str, str]] | None = None,
    policy_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Redact PII in text based on role policy from app/guards/policy.json.

    Hard safety rule:
        card_number must always be masked regardless of role policy value,
        even if policy.json specifies otherwise.

    Args:
        text: Input text to redact
        role: One of 'support_agent', 'fraud_analyst', 'compliance_officer'
        policy: Optional override policy dict (useful for testing)
        policy_path: Optional custom path to policy.json

    Returns:
        dict: {"text": str, "found": list[dict]}
    """
    if policy is None:
        policy = load_policy(policy_path)

    if role not in policy:
        raise ValueError(
            f"Unknown role '{role}'. Expected one of: {list(policy.keys())}"
        )

    role_policy = policy[role]
    found = detect(text)

    # Apply redactions in reverse order of start offset so string modifications
    # do not shift earlier character indices.
    redacted_text = text
    for item in sorted(found, key=lambda x: x["start"], reverse=True):
        pii_type = item["type"]
        action = role_policy.get(pii_type, "mask")

        # Hard safety rule: card_number must always be masked regardless of policy
        if pii_type == "card_number":
            action = "mask"

        replacement = _format_replacement(item, action)
        start, end = item["start"], item["end"]
        redacted_text = redacted_text[:start] + replacement + redacted_text[end:]

    return {
        "text": redacted_text,
        "found": found,
    }
