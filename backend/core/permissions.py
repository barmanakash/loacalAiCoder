"""
LocalCoder — Permission & approval system.

Level 0: Read and search
Level 1: Edit files (with approval)
Level 2: Delete / install actions (with confirmation)
Level 3: Restricted system actions
"""

from __future__ import annotations

import asyncio
from typing import Callable, Awaitable

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.types import ApprovalRequest, ApprovalResponse, PermissionLevel

log = get_logger(__name__)

# Pluggable approval callback — can be replaced by API/UI handler
_approval_callback: Callable[[ApprovalRequest], Awaitable[ApprovalResponse]] | None = None


def set_approval_callback(cb: Callable[[ApprovalRequest], Awaitable[ApprovalResponse]]) -> None:
    global _approval_callback
    _approval_callback = cb


async def default_approval(req: ApprovalRequest) -> ApprovalResponse:
    """
    Default: auto-approve level 0-1, require explicit confirmation for 2+.
    In a real deployment this is wired to the UI or CLI prompt.
    """
    if req.permission_level <= PermissionLevel.EDIT:
        log.info(
            "permission.auto_approved",
            action=req.action,
            level=req.permission_level,
        )
        return ApprovalResponse(approved=True)

    # For higher levels we auto-deny in headless mode unless overridden
    log.warning(
        "permission.denied_requires_ui",
        action=req.action,
        level=req.permission_level,
    )
    return ApprovalResponse(
        approved=False,
        reason="Interactive approval required for this permission level.",
    )


async def request_approval(
    action: str,
    details: str,
    required_level: PermissionLevel,
    task_id: str,
    current_level: PermissionLevel,
) -> bool:
    """
    Check whether the task's permission level covers `required_level`.
    If it does, approve automatically (subject to REQUIRE_APPROVAL flag).
    """
    if required_level > current_level:
        log.warning(
            "permission.insufficient",
            required=required_level,
            granted=current_level,
            action=action,
        )
        return False

    req = ApprovalRequest(
        action=action,
        details=details,
        permission_level=required_level,
        task_id=task_id,
    )

    callback = _approval_callback or default_approval
    resp = await callback(req)

    log.info(
        "permission.decision",
        action=action,
        approved=resp.approved,
        reason=resp.reason,
    )
    return resp.approved
