"""
╔══════════════════════════════════════════════════════════════════════╗
║  tests/test_suite.py — مجموعة الاختبارات الشاملة                   ║
║  Unit Tests + Integration Tests باستخدام pytest + In-Memory SQLite  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import ContentType
from database.connection import get_db, init_db
from database.repositories import (
    AdminRepository, CategoryRepository, ChannelRepository,
    ContentGroupRepository, ContentRepository, OwnerRepository,
    PointsRepository, UserRepository, VipRepository,
)
from services.auth_service import AuthService
from services.broadcast_service import BroadcastService, BroadcastResult
from services.subscription_service import SubscriptionService


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path) -> Path:
    """Provide an isolated in-memory-like SQLite database for each test."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def user_repo(db_path):    return UserRepository(db_path)
@pytest.fixture
def owner_repo(db_path):   return OwnerRepository(db_path)
@pytest.fixture
def admin_repo(db_path):   return AdminRepository(db_path)
@pytest.fixture
def vip_repo(db_path):     return VipRepository(db_path)
@pytest.fixture
def points_repo(db_path):  return PointsRepository(db_path)
@pytest.fixture
def channel_repo(db_path): return ChannelRepository(db_path)
@pytest.fixture
def cat_repo(db_path):     return CategoryRepository(db_path)
@pytest.fixture
def cont_repo(db_path):    return ContentRepository(db_path)
@pytest.fixture
def group_repo(db_path):   return ContentGroupRepository(db_path)


@pytest.fixture
def auth_service(owner_repo, admin_repo, vip_repo):
    return AuthService(
        owner_ids=frozenset({1000}),
        owner_repo=owner_repo,
        admin_repo=admin_repo,
        vip_repo=vip_repo,
    )


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: UserRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestUserRepository:
    def test_upsert_and_count(self, user_repo):
        assert user_repo.count() == 0
        user_repo.upsert(1, "Alice", "alice_tg")
        assert user_repo.count() == 1

    def test_upsert_is_idempotent(self, user_repo):
        user_repo.upsert(1, "Alice", "alice_tg")
        user_repo.upsert(1, "Alice Updated", None)
        assert user_repo.count() == 1

    def test_get_all_ids(self, user_repo):
        user_repo.upsert(1, "Alice", None)
        user_repo.upsert(2, "Bob",   None)
        ids = user_repo.get_all_ids()
        assert set(ids) == {1, 2}

    def test_count_zero_initially(self, user_repo):
        assert user_repo.count() == 0


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: AuthService
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthService:
    def test_hardcoded_owner_is_owner(self, auth_service):
        assert auth_service.is_owner(1000) is True

    def test_unknown_user_is_not_owner(self, auth_service):
        assert auth_service.is_owner(9999) is False

    def test_add_and_check_owner(self, auth_service):
        auth_service.add_owner(2000, added_by=1000)
        assert auth_service.is_owner(2000) is True

    def test_remove_dynamic_owner(self, auth_service):
        auth_service.add_owner(2000, added_by=1000)
        auth_service.remove_owner(2000)
        assert auth_service.is_owner(2000) is False

    def test_cannot_remove_hardcoded_owner(self, auth_service):
        with pytest.raises(PermissionError):
            auth_service.remove_owner(1000)

    def test_owner_is_admin(self, auth_service):
        assert auth_service.is_admin(1000) is True

    def test_add_admin(self, auth_service):
        auth_service.add_admin(3000)
        assert auth_service.is_admin(3000) is True

    def test_admin_is_vip(self, auth_service):
        auth_service.add_admin(3000)
        assert auth_service.is_vip(3000) is True

    def test_add_vip(self, auth_service):
        auth_service.add_vip(4000, added_by=1000)
        assert auth_service.is_vip(4000) is True

    def test_remove_vip(self, auth_service):
        auth_service.add_vip(4000, added_by=1000)
        auth_service.remove_vip(4000)
        assert auth_service.is_vip(4000) is False


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: PointsRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestPointsRepository:
    def test_first_visit(self, points_repo):
        assert points_repo.is_first_visit(99) is True

    def test_not_first_visit_after_add(self, points_repo):
        points_repo.add(99, 5)
        assert points_repo.is_first_visit(99) is False

    def test_add_points(self, points_repo):
        total = points_repo.add(99, 10)
        assert total == 10

    def test_accumulate_points(self, points_repo):
        points_repo.add(99, 5)
        total = points_repo.add(99, 3)
        assert total == 8

    def test_get_default_zero(self, points_repo):
        assert points_repo.get(999) == 0


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: CategoryRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestCategoryRepository:
    def test_add_root_category(self, cat_repo):
        new_id = cat_repo.add(parent_id=None, name="Math")
        assert new_id is not None
        cat = cat_repo.get_by_id(new_id)
        assert cat.name == "Math"
        assert cat.parent_id is None

    def test_add_subcategory(self, cat_repo):
        root_id = cat_repo.add(parent_id=None, name="Science")
        child_id = cat_repo.add(parent_id=root_id, name="Physics")
        child = cat_repo.get_by_id(child_id)
        assert child.parent_id == root_id

    def test_get_children(self, cat_repo):
        root_id = cat_repo.add(None, "Root")
        cat_repo.add(root_id, "Child A")
        cat_repo.add(root_id, "Child B")
        children = cat_repo.get_children(root_id)
        assert len(children) == 2

    def test_update_name(self, cat_repo):
        cat_id = cat_repo.add(None, "Old Name")
        cat_repo.update_name(cat_id, "New Name")
        assert cat_repo.get_by_id(cat_id).name == "New Name"

    def test_delete_category(self, cat_repo):
        cat_id = cat_repo.add(None, "Temp")
        cat_repo.delete(cat_id)
        assert cat_repo.get_by_id(cat_id) is None

    def test_count(self, cat_repo):
        cat_repo.add(None, "A")
        cat_repo.add(None, "B")
        assert cat_repo.count() == 2


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: ContentRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestContentRepository:
    def test_add_and_retrieve(self, cat_repo, cont_repo):
        cat_id = cat_repo.add(None, "Category")
        cont_id = cont_repo.add(cat_id, ContentType.TEXT, "Hello World", "Greeting")
        content = cont_repo.get_by_id(cont_id)
        assert content.name == "Greeting"
        assert content.content_type == ContentType.TEXT

    def test_get_by_category(self, cat_repo, cont_repo):
        cat_id = cat_repo.add(None, "Category")
        cont_repo.add(cat_id, ContentType.TEXT, "data1", "Item 1")
        cont_repo.add(cat_id, ContentType.PHOTO, "file_id", "Item 2")
        items = cont_repo.get_by_category(cat_id)
        assert len(items) == 2

    def test_update_name(self, cat_repo, cont_repo):
        cat_id  = cat_repo.add(None, "Category")
        cont_id = cont_repo.add(cat_id, ContentType.TEXT, "data", "Old")
        cont_repo.update_name(cont_id, "New")
        assert cont_repo.get_by_id(cont_id).name == "New"

    def test_delete(self, cat_repo, cont_repo):
        cat_id  = cat_repo.add(None, "Category")
        cont_id = cont_repo.add(cat_id, ContentType.TEXT, "data", "Item")
        cont_repo.delete(cont_id)
        assert cont_repo.get_by_id(cont_id) is None

    def test_content_type_enum(self, cat_repo, cont_repo):
        cat_id  = cat_repo.add(None, "Category")
        cont_id = cont_repo.add(cat_id, ContentType.VIDEO, "video_file_id", "Video")
        content = cont_repo.get_by_id(cont_id)
        assert content.content_type == ContentType.VIDEO
        assert content.content_type.emoji == "🎥"


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: ContentGroupRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestContentGroupRepository:
    def test_add_group(self, cat_repo, group_repo):
        cat_id   = cat_repo.add(None, "Category")
        group_id = group_repo.add(cat_id, "My Group")
        group    = group_repo.get_by_id(group_id)
        assert group.name == "My Group"

    def test_add_and_count_items(self, cat_repo, group_repo):
        cat_id   = cat_repo.add(None, "Category")
        group_id = group_repo.add(cat_id, "Group")
        group_repo.add_item(group_id, ContentType.PHOTO, "file1", "Caption 1")
        group_repo.add_item(group_id, ContentType.VIDEO, "file2", "")
        assert group_repo.count_items(group_id) == 2

    def test_get_items(self, cat_repo, group_repo):
        cat_id   = cat_repo.add(None, "Category")
        group_id = group_repo.add(cat_id, "Group")
        group_repo.add_item(group_id, ContentType.PHOTO, "photo_id", "cap")
        items = group_repo.get_items(group_id)
        assert len(items) == 1
        assert items[0].content_type == ContentType.PHOTO

    def test_delete_group_cascades_items(self, cat_repo, group_repo):
        cat_id   = cat_repo.add(None, "Category")
        group_id = group_repo.add(cat_id, "Group")
        group_repo.add_item(group_id, ContentType.DOCUMENT, "doc_id", "")
        group_repo.delete(group_id)
        assert group_repo.get_by_id(group_id) is None
        assert group_repo.count_items(group_id) == 0


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: ChannelRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestChannelRepository:
    def test_add_and_get(self, channel_repo):
        channel_repo.add("mychannel", "My Channel", "https://t.me/mychannel")
        channels = channel_repo.get_all()
        assert len(channels) == 1
        assert channels[0].channel_title == "My Channel"

    def test_remove(self, channel_repo):
        channel_repo.add("ch1", "Channel 1", "https://t.me/ch1")
        channel_repo.remove("ch1")
        assert channel_repo.get_all() == []

    def test_count(self, channel_repo):
        channel_repo.add("c1", "C1", "https://t.me/c1")
        channel_repo.add("c2", "C2", "https://t.me/c2")
        assert channel_repo.count() == 2


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: ContentType Model
# ─────────────────────────────────────────────────────────────────────────────

class TestContentTypeModel:
    @pytest.mark.parametrize("ctype,expected_emoji", [
        (ContentType.TEXT,     "📝"),
        (ContentType.PHOTO,    "🖼️"),
        (ContentType.VIDEO,    "🎥"),
        (ContentType.DOCUMENT, "📄"),
        (ContentType.LINK,     "🔗"),
    ])
    def test_emoji(self, ctype, expected_emoji):
        assert ctype.emoji == expected_emoji

    @pytest.mark.parametrize("ctype,expected_ar", [
        (ContentType.TEXT,     "نص"),
        (ContentType.PHOTO,    "صورة"),
        (ContentType.VIDEO,    "فيديو"),
        (ContentType.DOCUMENT, "ملف"),
        (ContentType.LINK,     "رابط"),
    ])
    def test_arabic_name(self, ctype, expected_ar):
        assert ctype.arabic_name == expected_ar


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: BroadcastService
# ─────────────────────────────────────────────────────────────────────────────

class TestBroadcastService:
    @pytest.mark.asyncio
    async def test_success_count(self, user_repo):
        user_repo.upsert(1, "A", None)
        user_repo.upsert(2, "B", None)

        bot = AsyncMock()
        bot.copy_message = AsyncMock(return_value=None)

        svc    = BroadcastService(user_repo, rate_limit_delay=0)
        result = await svc.send_to_all(bot, from_chat_id=99, message_id=1)

        assert result.success == 2
        assert result.failed  == 0
        assert result.total   == 2

    @pytest.mark.asyncio
    async def test_handles_forbidden(self, user_repo):
        from telegram.error import Forbidden
        user_repo.upsert(1, "A", None)

        bot = AsyncMock()
        bot.copy_message = AsyncMock(side_effect=Forbidden("blocked"))

        svc    = BroadcastService(user_repo, rate_limit_delay=0)
        result = await svc.send_to_all(bot, from_chat_id=99, message_id=1)

        assert result.success == 0
        assert result.failed  == 1

    def test_success_rate(self):
        result = BroadcastResult(total=10, success=8, failed=2)
        assert result.success_rate == 80.0

    def test_success_rate_zero_total(self):
        result = BroadcastResult(total=0, success=0, failed=0)
        assert result.success_rate == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION TESTS: Category cascade delete
# ─────────────────────────────────────────────────────────────────────────────

class TestCascadeDelete:
    def test_delete_category_cascades_contents(self, cat_repo, cont_repo):
        cat_id  = cat_repo.add(None, "Parent")
        cont_id = cont_repo.add(cat_id, ContentType.TEXT, "data", "Item")
        cat_repo.delete(cat_id)
        assert cont_repo.get_by_id(cont_id) is None

    def test_delete_category_cascades_groups(self, cat_repo, group_repo):
        cat_id   = cat_repo.add(None, "Parent")
        group_id = group_repo.add(cat_id, "Group")
        group_repo.add_item(group_id, ContentType.PHOTO, "photo", "")
        cat_repo.delete(cat_id)
        assert group_repo.get_by_id(group_id) is None
        assert group_repo.count_items(group_id) == 0

    def test_delete_subcategory_does_not_affect_parent(self, cat_repo):
        root_id  = cat_repo.add(None, "Root")
        child_id = cat_repo.add(root_id, "Child")
        cat_repo.delete(child_id)
        assert cat_repo.get_by_id(root_id) is not None


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION TESTS: AuthService + DB
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthServiceIntegration:
    def test_full_permission_chain(self, db_path):
        owner_repo = OwnerRepository(db_path)
        admin_repo = AdminRepository(db_path)
        vip_repo   = VipRepository(db_path)
        svc = AuthService(frozenset({1}), owner_repo, admin_repo, vip_repo)

        # Owner → admin → vip chain
        assert svc.is_owner(1)
        assert svc.is_admin(1)
        assert svc.is_vip(1)

        # Regular user has none
        assert not svc.is_owner(999)
        assert not svc.is_admin(999)
        assert not svc.is_vip(999)

        # Grant each level independently
        svc.add_admin(100)
        assert svc.is_admin(100)
        assert not svc.is_owner(100)

        svc.add_vip(200, added_by=1)
        assert svc.is_vip(200)
        assert not svc.is_admin(200)
