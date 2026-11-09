"""
Token-to-user/role resolution.

Role is derived ONLY from the token mapping, never from request body or
query text. This is a security invariant (see docs/security-model.md).

Tokens come from AUTH_TOKENS_JSON if set, otherwise from AUTH_TOKENS_FILE.
See app/auth_tokens.example.json for the expected shape.
"""
import json
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

ROLES = ("support_agent", "fraud_analyst", "compliance_officer")

_tokens: dict | None = None


class AuthError(Exception):
    pass


def load_tokens() -> dict:
    settings = get_settings()
    if settings.auth_tokens_json:
        tokens = json.loads(settings.auth_tokens_json)
    elif settings.auth_tokens_file.exists():
        with open(settings.auth_tokens_file) as f:
            tokens = json.load(f)
    else:
        tokens = {}
    for token, identity in tokens.items():
        if identity.get("role") not in ROLES:
            raise ValueError(f"Token {token!r} has unknown role {identity.get('role')!r}")
    if not tokens:
        logger.warning("No auth tokens configured; every request will be rejected.")
    return tokens


def init_tokens() -> None:
    """(Re)load tokens from the current settings."""
    global _tokens
    _tokens = load_tokens()


def resolve_token(token: str) -> dict:
    """
    Resolve a raw token string to {"user_id": ..., "role": ...}.
    Raises AuthError if the token is missing or unknown.
    """
    if _tokens is None:
        init_tokens()
    if not token:
        raise AuthError("missing token")
    identity = _tokens.get(token)
    if identity is None:
        raise AuthError("invalid token")
    return identity
