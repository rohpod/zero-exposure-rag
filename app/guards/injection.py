import pickle
import re
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"

_classifier = None
_vectorizer = None


def _load_model():
    global _classifier, _vectorizer
    if _classifier is None:
        with open(MODEL_DIR / "injection_classifier.pkl", "rb") as f:
            _classifier = pickle.load(f)
        with open(MODEL_DIR / "injection_vectorizer.pkl", "rb") as f:
            _vectorizer = pickle.load(f)
    return _classifier, _vectorizer


# Rule layer: phrases that strongly signal an attack regardless of what
# the classifier thinks. Checked case-insensitively. These catch known
# attack patterns the classifier may miss, and also separate out
# "exfil" (trying to extract system/prompt info) as its own label,
# since the trained classifier only distinguishes safe vs injection.

EXFIL_PATTERNS = [
    r"reveal (your|the) (system )?prompt",
    r"show (me )?(your|the) (system )?prompt",
    r"repeat (your|the) (instructions|system prompt)",
    r"output (your|the) (instructions|system prompt)",
    r"what (were|are) you (told|instructed) not to (say|reveal)",
    r"ignore (all )?(previous|prior|earlier) (instructions|rules|orders)",
    r"forget (all )?(previous|prior|earlier) (instructions|rules|tasks)",
]

INJECTION_PATTERNS = [
    r"\bi am the (admin|administrator|compliance officer|fraud analyst)\b",
    r"\bact as\b",
    r"\byou are now\b",
    r"\bpretend (you are|to be)\b",
    r"\bstop,? ignore\b",
    r"\bnew (task|instructions) follow\b",
]

_exfil_re = re.compile("|".join(EXFIL_PATTERNS), re.IGNORECASE)
_injection_re = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def scan_input(text: str) -> dict:
    # Rule layer first — these are high-confidence signals that should
    # override the classifier, since they're near-certain attack phrasing.
    if _exfil_re.search(text):
        return {"label": "exfil", "score": 0.99}

    if _injection_re.search(text):
        return {"label": "injection", "score": 0.95}

    # Fall back to the trained classifier for everything else.
    clf, vectorizer = _load_model()
    vec = vectorizer.transform([text])
    pred_label = clf.predict(vec)[0]
    pred_proba = clf.predict_proba(vec)[0]
    classes = list(clf.classes_)
    score = float(pred_proba[classes.index(pred_label)])

    return {"label": pred_label, "score": score}
