"""Auth package: Google OAuth web login, session tokens, and the /auth/* routes.

Narrow public surface — only what the rest of the codebase actually imports.
"""

from .routes import _auth_enabled, _resolve_request_user, get_current_user, router
from .tokens import (
    list_user_tokens,
    mint_token,
    resolve_token,
    revoke_token,
    update_user_name,
)

__all__ = [
    "_auth_enabled",
    "_resolve_request_user",
    "get_current_user",
    "list_user_tokens",
    "mint_token",
    "resolve_token",
    "revoke_token",
    "router",
    "update_user_name",
]
