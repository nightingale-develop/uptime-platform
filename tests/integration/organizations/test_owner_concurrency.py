import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from uptime_platform.organizations.entities import OrganizationRole
from uptime_platform.organizations.exceptions import LastOrganizationOwnerError
from uptime_platform.organizations.member_service import OrganizationMemberService
from uptime_platform.organizations.models import MembershipModel, OrganizationModel
from uptime_platform.organizations.sqlalchemy_repository import (
    SqlAlchemyMembershipRepository,
)
from uptime_platform.users.models import UserModel
from uptime_platform.users.sqlalchemy_repository import SqlAlchemyUserRepository

pytestmark = pytest.mark.anyio


@pytest.fixture
async def owners(session_factory):
    organization_id = uuid4()
    user_ids = [uuid4(), uuid4()]
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        session.add(
            OrganizationModel(id=organization_id, name="Owner race", created_at=now)
        )
        session.add_all(
            UserModel(
                id=user_id,
                email=f"{user_id}@example.com",
                password_hash="not-used",
                created_at=now,
            )
            for user_id in user_ids
        )
        await session.flush()
        session.add_all(
            MembershipModel(
                id=uuid4(),
                organization_id=organization_id,
                user_id=user_id,
                role=OrganizationRole.OWNER,
                created_at=now,
            )
            for user_id in user_ids
        )
    try:
        yield organization_id, user_ids
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(OrganizationModel).where(OrganizationModel.id == organization_id)
            )
            await session.execute(delete(UserModel).where(UserModel.id.in_(user_ids)))


@pytest.mark.parametrize(
    "actions", [("delete", "delete"), ("demote", "demote"), ("delete", "demote")]
)
async def test_concurrent_owner_changes_preserve_last_owner(
    session_factory, owners, actions
):
    organization_id, user_ids = owners
    counted = asyncio.Event()
    resume_first = asyncio.Event()
    second_started = asyncio.Event()
    second_pid = None

    class PausedCountRepository(SqlAlchemyMembershipRepository):
        async def get_by_organization_id(self, organization_id):
            memberships = await super().get_by_organization_id(organization_id)
            counted.set()
            await resume_first.wait()
            return memberships

    async def change(index):
        nonlocal second_pid
        try:
            async with session_factory() as session, session.begin():
                repository_type = (
                    PausedCountRepository
                    if index == 0
                    else SqlAlchemyMembershipRepository
                )
                service = OrganizationMemberService(
                    repository_type(session),
                    SqlAlchemyUserRepository(session),
                    organization_id,
                    user_ids[index],
                    OrganizationRole.OWNER,
                )
                if index == 1:
                    second_pid = await session.scalar(select(func.pg_backend_pid()))
                    second_started.set()
                if actions[index] == "delete":
                    await service.delete(user_ids[index])
                else:
                    await service.update_role(user_ids[index], OrganizationRole.ADMIN)
            return True
        except LastOrganizationOwnerError:
            return False

    async with asyncio.timeout(10), asyncio.TaskGroup() as group:
        first = group.create_task(change(0))
        await counted.wait()
        second = group.create_task(change(1))
        try:
            await second_started.wait()
            async with session_factory() as observer:
                while not second.done():
                    if await observer.scalar(select(func.pg_blocking_pids(second_pid))):
                        break
                    await asyncio.sleep(0.01)
        finally:
            resume_first.set()

    assert first.result() is True
    assert second.result() is False
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MembershipModel)
                .where(
                    MembershipModel.organization_id == organization_id,
                    MembershipModel.role == OrganizationRole.OWNER,
                )
            )
            == 1
        )
