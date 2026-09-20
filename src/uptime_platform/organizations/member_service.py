from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from uptime_platform.organizations.entities import (
    Membership,
    OrganizationRole,
)
from uptime_platform.organizations.exceptions import (
    LastOrganizationOwnerError,
    OrganizationMemberAlreadyExistsError,
    OrganizationMemberNotFoundError,
    OrganizationMemberPermissionError,
    OrganizationUserNotFoundError,
)
from uptime_platform.organizations.protocols import (
    MembershipRepositoryProtocol,
)
from uptime_platform.users.entities import User
from uptime_platform.users.protocols import (
    UserRepositoryProtocol,
)


@dataclass(frozen=True, slots=True)
class OrganizationMemberResult:
    user: User
    membership: Membership


class OrganizationMemberService:
    def __init__(
        self,
        membership_repository: MembershipRepositoryProtocol,
        user_repository: UserRepositoryProtocol,
        organization_id: UUID,
        actor_user_id: UUID | None,
        actor_role: OrganizationRole,
    ) -> None:
        self._membership_repository = membership_repository
        self._user_repository = user_repository
        self._organization_id = organization_id
        self._actor_user_id = actor_user_id
        self._actor_role = actor_role

    async def get_all(
        self,
    ) -> list[OrganizationMemberResult]:
        memberships = await self._membership_repository.get_by_organization_id(
            self._organization_id
        )

        result: list[OrganizationMemberResult] = []

        for membership in memberships:
            user = await self._user_repository.get_by_id(membership.user_id)

            if user is None:
                continue

            result.append(
                OrganizationMemberResult(
                    user=user,
                    membership=membership,
                )
            )

        result.sort(key=lambda item: item.membership.created_at)

        return result

    async def add(
        self,
        email: str,
        role: OrganizationRole,
    ) -> OrganizationMemberResult:
        self._ensure_role_can_be_assigned(role)

        user = await self._user_repository.get_by_email(email.lower())

        if user is None:
            raise OrganizationUserNotFoundError

        existing = await self._membership_repository.get_by_user_and_organization(
            user_id=user.id,
            organization_id=(self._organization_id),
        )

        if existing is not None:
            raise OrganizationMemberAlreadyExistsError

        membership = Membership(
            id=uuid4(),
            organization_id=self._organization_id,
            user_id=user.id,
            role=role,
            created_at=datetime.now(UTC),
        )

        membership = await self._membership_repository.create(membership)

        return OrganizationMemberResult(
            user=user,
            membership=membership,
        )

    async def update_role(
        self,
        user_id: UUID,
        role: OrganizationRole,
    ) -> OrganizationMemberResult:
        membership = await self._get_membership(user_id)

        self._ensure_can_manage(membership)

        self._ensure_role_can_be_assigned(role)

        if (
            membership.role is OrganizationRole.OWNER
            and role is not OrganizationRole.OWNER
        ):
            await self._ensure_not_last_owner()

        updated = replace(
            membership,
            role=role,
        )

        updated = await self._membership_repository.update(updated)

        if updated is None:
            raise OrganizationMemberNotFoundError

        user = await self._user_repository.get_by_id(user_id)

        if user is None:
            raise OrganizationUserNotFoundError

        return OrganizationMemberResult(
            user=user,
            membership=updated,
        )

    async def delete(
        self,
        user_id: UUID,
    ) -> None:
        membership = await self._get_membership(user_id)

        self._ensure_can_manage(membership)

        if membership.role is OrganizationRole.OWNER:
            await self._ensure_not_last_owner()

        deleted = await self._membership_repository.delete(
            membership.id,
            self._organization_id,
        )

        if not deleted:
            raise OrganizationMemberNotFoundError

    async def _get_membership(
        self,
        user_id: UUID,
    ) -> Membership:
        await self._membership_repository.lock_organization(self._organization_id)
        membership = await self._membership_repository.get_by_user_and_organization(
            user_id=user_id,
            organization_id=(self._organization_id),
        )

        if membership is None:
            raise OrganizationMemberNotFoundError

        return membership

    def _ensure_role_can_be_assigned(
        self,
        role: OrganizationRole,
    ) -> None:
        if self._actor_role is OrganizationRole.OWNER:
            return

        if self._actor_role is OrganizationRole.ADMIN and role in {
            OrganizationRole.MEMBER,
            OrganizationRole.VIEWER,
        }:
            return

        raise OrganizationMemberPermissionError

    def _ensure_can_manage(
        self,
        membership: Membership,
    ) -> None:
        if self._actor_role is OrganizationRole.OWNER:
            return

        if self._actor_role is OrganizationRole.ADMIN and membership.role in {
            OrganizationRole.MEMBER,
            OrganizationRole.VIEWER,
        }:
            return

        raise OrganizationMemberPermissionError

    async def _ensure_not_last_owner(
        self,
    ) -> None:
        memberships = await self._membership_repository.get_by_organization_id(
            self._organization_id
        )

        owner_count = sum(
            membership.role is OrganizationRole.OWNER for membership in memberships
        )

        if owner_count <= 1:
            raise LastOrganizationOwnerError
