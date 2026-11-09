"""
Text normalisation used by the output guard to see through obfuscation
(spacing, separators, spelled-out digits, base64). The red-team scorer keeps
its own copy of these rules on purpose (redteam/score.py).
"""
import base64
import re
import unicodedata

_DIGIT_WORDS = {
    "ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4",
    "FIVE": "5", "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9",
}
_DIGIT_WORD_RE = re.compile(r"\b(" + "|".join(_DIGIT_WORDS) + r")\b")
_SEPARATORS_RE = re.compile(r"(?<=[A-Z0-9])[\s\-._]+(?=[A-Z0-9])")
_BASE64_RUN_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


def _decode_base64_runs(text: str) -> list[str]:
    decoded = []
    for run in _BASE64_RUN_RE.findall(text):
        padded = run + "=" * (-len(run) % 4)
        try:
            raw = base64.b64decode(padded, validate=True)
            candidate = raw.decode("ascii")
        except (ValueError, UnicodeDecodeError):
            continue
        if candidate and candidate.isprintable():
            decoded.append(candidate)
    return decoded


def normalize(text: str) -> str:
    """NFKC, uppercase, spelled-out digits to digits, separators between
    alphanumerics removed, and any base64-decoded text appended."""
    text = unicodedata.normalize("NFKC", text)
    text = " ".join([text, *_decode_base64_runs(text)])
    text = text.upper()
    text = _DIGIT_WORD_RE.sub(lambda m: _DIGIT_WORDS[m.group(1)], text)
    return _SEPARATORS_RE.sub("", text)
