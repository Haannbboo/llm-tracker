"""Auth package: sign-in providers (local, Google), session tokens, and the /auth/* routes.

Narrow public surface — only what the rest of the codebase actually imports.
"""

from .routes import (
    _require_local_owner,
    _resolve_request_user,
    auth_provider,
    get_current_user,
    is_direct_loopback,
    local_owner_allowed,
    router,
)
from .tokens import (
    get_local_owner,
    list_user_tokens,
    mint_token,
    resolve_token,
    revoke_token,
    update_user_name,
)

__all__ = [
    "_require_local_owner",
    "_resolve_request_user",
    "auth_provider",
    "get_current_user",
    "get_local_owner",
    "is_direct_loopback",
    "list_user_tokens",
    "local_owner_allowed",
    "mint_token",
    "resolve_token",
    "revoke_token",
    "router",
    "update_user_name",
]
