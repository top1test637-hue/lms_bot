"""
╔══════════════════════════════════════════════════════════════════════╗
║  services/auth_service.py — خدمة المصادقة والصلاحيات               ║
║  Single Responsibility: كل قرار أذونات يمر من هنا فقط              ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import FrozenSet

from database.repositories import AdminRepository, OwnerRepository, VipRepository

logger = logging.getLogger(__name__)


class AuthService:
    """
    Centralizes all permission checks in a single, testable service.

    Permission hierarchy (highest → lowest):
        Owner > Admin > VIP > Regular User

    Args:
        owner_ids: Frozen set of hardcoded owner IDs (from config).
        owner_repo: Repository for dynamic DB-stored owners.
        admin_repo: Repository for admin records.
        vip_repo: Repository for VIP membership.

    Examples:
        >>> svc = AuthService(frozenset({123}), owner_repo, admin_repo, vip_repo)
        >>> svc.is_owner(123)
        True
    """

    def __init__(
        self,
        owner_ids: FrozenSet[int],
        owner_repo: OwnerRepository,
        admin_repo: AdminRepository,
        vip_repo: VipRepository,
    ) -> None:
        self._owner_ids  = owner_ids
        self._owner_repo = owner_repo
        self._admin_repo = admin_repo
        self._vip_repo   = vip_repo

    def is_owner(self, user_id: int) -> bool:
        """
        Return True if user is a hardcoded or DB-stored owner.

        Args:
            user_id: Telegram user ID to check.
        """
        return user_id in self._owner_ids or self._owner_repo.exists(user_id)

    def is_admin(self, user_id: int) -> bool:
        """
        Return True if user has admin or higher privileges.
        Owners are implicitly admins.
        """
        return self.is_owner(user_id) or self._admin_repo.exists(user_id)

    def is_vip(self, user_id: int) -> bool:
        """
        Return True if user has VIP or higher access.
        Admins implicitly have VIP access.
        """
        return self.is_admin(user_id) or self._vip_repo.exists(user_id)

    def add_owner(self, user_id: int, added_by: int) -> None:
        """Grant owner privileges to a user."""
        if not self.is_owner(user_id):
            self._owner_repo.add(user_id, added_by)
            logger.info("Owner added: %d (by %d)", user_id, added_by)

    def remove_owner(self, user_id: int) -> None:
        """Revoke dynamic owner privileges (cannot remove hardcoded owners)."""
        if user_id in self._owner_ids:
            raise PermissionError("Cannot remove a hardcoded owner.")
        self._owner_repo.remove(user_id)
        logger.info("Owner removed: %d", user_id)

    def add_admin(self, user_id: int) -> None:
        """Grant admin privileges."""
        self._admin_repo.add(user_id)
        logger.info("Admin added: %d", user_id)

    def add_vip(self, user_id: int, added_by: int) -> None:
        """Grant VIP membership."""
        self._vip_repo.add(user_id, added_by)
        logger.info("VIP added: %d (by %d)", user_id, added_by)

    def remove_vip(self, user_id: int) -> None:
        """Revoke VIP membership."""
        self._vip_repo.remove(user_id)
        logger.info("VIP removed: %d", user_id)
