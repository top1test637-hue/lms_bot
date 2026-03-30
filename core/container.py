"""
╔══════════════════════════════════════════════════════════════════════╗
║  core/container.py — حاوية حقن التبعيات (DI Container)              ║
║  Wires all repositories and services together in one place           ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from core.config import BotConfig
from database.repositories import (
    AdminRepository, CategoryRepository, ChannelRepository,
    ContentGroupRepository, ContentRepository, OwnerRepository,
    PointsRepository, UserRepository, VipRepository,
)
from services.auth_service import AuthService
from services.broadcast_service import BroadcastService
from services.content_service import ContentDeliveryService
from services.subscription_service import SubscriptionService


@dataclass
class Container:
    """
    Dependency Injection Container.

    Constructs every repository and service from a single BotConfig.
    All instances are cached via ``cached_property`` — created lazily
    on first access, but only once per Container lifetime.

    Args:
        config: Application configuration object.

    Examples:
        >>> container = Container(config=get_config())
        >>> container.auth_service.is_admin(user_id)
    """

    config: BotConfig

    # ── Repositories ──────────────────────────────────────────────────────

    @cached_property
    def user_repo(self) -> UserRepository:
        return UserRepository(self.config.db_path)

    @cached_property
    def owner_repo(self) -> OwnerRepository:
        return OwnerRepository(self.config.db_path)

    @cached_property
    def admin_repo(self) -> AdminRepository:
        return AdminRepository(self.config.db_path)

    @cached_property
    def vip_repo(self) -> VipRepository:
        return VipRepository(self.config.db_path)

    @cached_property
    def points_repo(self) -> PointsRepository:
        return PointsRepository(self.config.db_path)

    @cached_property
    def channel_repo(self) -> ChannelRepository:
        return ChannelRepository(self.config.db_path)

    @cached_property
    def category_repo(self) -> CategoryRepository:
        return CategoryRepository(self.config.db_path)

    @cached_property
    def content_repo(self) -> ContentRepository:
        return ContentRepository(self.config.db_path)

    @cached_property
    def group_repo(self) -> ContentGroupRepository:
        return ContentGroupRepository(self.config.db_path)

    # ── Services ──────────────────────────────────────────────────────────

    @cached_property
    def auth_service(self) -> AuthService:
        return AuthService(
            owner_ids=self.config.owner_ids,
            owner_repo=self.owner_repo,
            admin_repo=self.admin_repo,
            vip_repo=self.vip_repo,
        )

    @cached_property
    def subscription_service(self) -> SubscriptionService:
        return SubscriptionService(self.channel_repo)

    @cached_property
    def content_delivery_service(self) -> ContentDeliveryService:
        return ContentDeliveryService(
            group_repo=self.group_repo,
            group_page_size=self.config.group_page_size,
        )

    @cached_property
    def broadcast_service(self) -> BroadcastService:
        return BroadcastService(
            user_repo=self.user_repo,
            rate_limit_delay=self.config.rate_limit_delay,
        )
