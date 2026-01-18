"""Contexto de usuario para enforcing multi-tenant en capa app."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional, Dict, Any, List


UserContext = Dict[str, Any]

_current_user: ContextVar[Optional[UserContext]] = ContextVar("current_user", default=None)


def set_current_user_context(user_id: str, organization_id: str, roles: Optional[List[str]] = None) -> None:
    _current_user.set({
        "user_id": user_id,
        "organization_id": organization_id,
        "roles": roles or [],
    })


def get_current_user_context() -> Optional[UserContext]:
    return _current_user.get()
