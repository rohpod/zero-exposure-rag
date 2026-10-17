"""
Central configuration for the platform.

STUB_MODE: when true, retrieval and guards return canned values so the
pipeline can be tested end to end before real components are integrated.

EVAL_MODE: when set to "1" via environment variable, the server honours the
X-Guards header from the red-team harness, allowing guards to be switched
off for evaluation runs. Must be "0" (or unset) for the demo and submission.
"""
import os

STUB_MODE = os.getenv("STUB_MODE", "1") == "1"
EVAL_MODE = os.getenv("EVAL_MODE", "0") == "1"
