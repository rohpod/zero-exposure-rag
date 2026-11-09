import base64

from app.guards.normalize import normalize


def test_separators_between_alphanumerics_are_removed():
    assert normalize("c a n-a.r_y") == "CANARY"


def test_spelled_out_digits_become_digits():
    assert normalize("L three zero six zero one") == "L30601"


def test_base64_runs_are_decoded_and_appended():
    encoded = base64.b64encode(b"CANARY-L3-0601").decode()
    assert "CANARYL30601" in normalize(f"here: {encoded}")


def test_nfkc_folds_fullwidth_characters():
    assert normalize("ＣＡＮＡＲＹ") == "CANARY"
