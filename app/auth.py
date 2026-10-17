"""
Token-to-user/role resolution.

Role is derived ONLY from the token mapping below, never from request body
or query text. This is a security invariant (see PLAN.docx).

Tokens are loaded from a git-ignored local file (app/auth_tokens.local.json).
See app/auth_tokens.example.json for the expected shape.
"""
import json
import os
from pathlib import Path

_TOKENS_PATH = Path(__file__).parent / "auth_tokens.local.json"

_tokens: dict = {}
if _TOKENS_PATH.exists():
    with open(_TOKENS_PATH) as f:
        _tokens = json.load(f)


class AuthError(Exception):
    pass


def resolve_token(token: str) -> dict:
    """
    Resolve a raw token string to {"user_id": ..., "role": ...}.
    Raises AuthError if the token is missing or unknown.
    """
    if not token:
        raise AuthError("missing token")
    identity = _tokens.get(token)
    if identity is None:
        raise AuthError("invalid token")
    return identity
