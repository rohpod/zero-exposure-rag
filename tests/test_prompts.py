from app.prompts import CANARY_STRING, SYSTEM_PROMPT


def test_system_prompt_is_nonempty():
    assert SYSTEM_PROMPT.strip()


def test_system_prompt_contains_expected_security_rules():
    prompt = SYSTEM_PROMPT.lower()

    assert "untrusted" in prompt
    assert "retrieved documents" in prompt
    assert "access controls" in prompt
    assert "system instructions" in prompt


def test_system_prompt_contains_exact_redteam_canary():
    assert CANARY_STRING == "CANARY-SYSPROMPT"
    assert CANARY_STRING in SYSTEM_PROMPT


def test_prompt_does_not_use_document_canaries():
    assert "CANARY-L2-0501" not in SYSTEM_PROMPT
    assert "CANARY-L3-0601" not in SYSTEM_PROMPT
