"""Role-based access control: fixed permission matrix (no custom roles).

viewer < member < manager < owner. The matrix is a single constant; endpoints
declare their minimum role via require_role(). Write actions beyond daily
sales work (approve prices/sheets, manage suppliers/products) need manager+;
user management and settings need owner.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from .deps import OrgScope, get_current_user, get_db
from .models import User

ROLE_LEVELS = {"viewer": 0, "member": 1, "manager": 2, "owner": 3}

# fixed matrix: minimum role required for each capability
MATRIX: dict[str, str] = {
    "inquiry.read": "viewer",
    "inquiry.write": "member",
    "quote.create": "member",
    "quote.set_price": "manager",
    "quote.approve": "manager",
    "quote_sheet.create": "member",
    "quote_sheet.approve": "manager",
    "product.read": "viewer",
    "product.write": "manager",
    "supplier.write": "manager",
    "import.run": "member",
    "connector.manage": "manager",
    "settings.manage": "owner",
    "user.manage": "owner",
}


def require_role(capability: str):
    """Dependency factory: current user's role must cover the capability."""
    minimum = MATRIX.get(capability)
    if minimum is None:
        raise RuntimeError(f"未知权限项: {capability}")

    def checker(user: User = Depends(get_current_user)) -> OrgScope:
        level = ROLE_LEVELS.get(user.role, 0)
        if level < ROLE_LEVELS[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={
                "code": "forbidden",
                "message": f"需要 {minimum} 及以上角色（当前 {user.role}）",
            })
        return OrgScope(user)

    return checker
