"""RBAC utilities for role and permission resolution."""

from typing import Dict, List, Set

DEFAULT_ROLE_PERMISSION_MAPPING: Dict[str, List[str]] = {
    "admin": ["*"],
    "user": [],
}


def get_effective_permissions(
    user_roles: List[str],
    user_permissions: List[str],
    role_permission_mapping: Dict[str, List[str]],
) -> Set[str]:
    """Compute effective permissions from roles and direct permissions.

    Union of (a) user's direct permissions, (b) permissions from all user's
    roles via the mapping. Wildcard "*" grants all permissions.

    Args:
        user_roles: Roles assigned to the user
        user_permissions: Direct permissions on the user
        role_permission_mapping: Maps role name -> list of permissions

    Returns:
        Set of effective permission strings
    """
    effective: Set[str] = set()

    # Add direct permissions
    effective.update(user_permissions or [])

    # Add permissions from roles
    mapping = role_permission_mapping or DEFAULT_ROLE_PERMISSION_MAPPING
    for role in user_roles or []:
        role_perms = mapping.get(role, [])
        effective.update(role_perms)

    return effective


def has_required_permissions(
    user_permissions: Set[str],
    required_permissions: List[str],
) -> bool:
    """Check if user has all required permissions.

    If user has "*" in their permissions, they have all permissions.

    Args:
        user_permissions: User's effective permissions
        required_permissions: Permissions required by the endpoint

    Returns:
        True if user has all required permissions
    """
    if not required_permissions:
        return True
    if "*" in user_permissions:
        return True
    return all(p in user_permissions for p in required_permissions)


def has_required_roles(user_roles: List[str], required_roles: List[str]) -> bool:
    """Check if user has any of the required roles.

    Args:
        user_roles: User's roles
        required_roles: Roles required by the endpoint (any of)

    Returns:
        True if user has at least one required role
    """
    if not required_roles:
        return True
    user_roles_set = set(user_roles or [])
    return any(r in user_roles_set for r in required_roles)


__all__ = [
    "DEFAULT_ROLE_PERMISSION_MAPPING",
    "get_effective_permissions",
    "has_required_permissions",
    "has_required_roles",
]
