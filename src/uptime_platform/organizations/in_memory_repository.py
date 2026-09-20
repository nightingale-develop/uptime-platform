from uuid import UUID

from uptime_platform.organizations.entities import (
    Membership,
    Organization,
)


class InMemoryOrganizationRepository:
    def __init__(self) -> None:
        self._organizations: dict[
            UUID,
            Organization,
        ] = {}

    async def create(
        self,
        organization: Organization,
    ) -> Organization:
        self._organizations[organization.id] = organization

        return organization

    async def get_by_id(
        self,
        organization_id: UUID,
    ) -> Organization | None:
        return self._organizations.get(organization_id)

    async def get_by_id_for_update(
        self,
        organization_id: UUID,
    ) -> Organization | None:
        return self._organizations.get(organization_id)

    async def update(
        self,
        organization: Organization,
    ) -> Organization:
        self._organizations[organization.id] = organization

        return organization


class InMemoryMembershipRepository:
    async def lock_organization(self, organization_id: UUID) -> None:
        return None

    def __init__(self) -> None:
        self._memberships: dict[
            UUID,
            Membership,
        ] = {}

    async def create(
        self,
        membership: Membership,
    ) -> Membership:
        self._memberships[membership.id] = membership

        return membership

    async def get_by_user_and_organization(
        self,
        user_id: UUID,
        organization_id: UUID,
    ) -> Membership | None:
        for membership in self._memberships.values():
            if (
                membership.user_id == user_id
                and membership.organization_id == organization_id
            ):
                return membership

        return None

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> list[Membership]:
        return [
            membership
            for membership in self._memberships.values()
            if membership.user_id == user_id
        ]

    async def get_by_organization_id(
        self,
        organization_id: UUID,
    ) -> list[Membership]:
        return [
            membership
            for membership in self._memberships.values()
            if membership.organization_id == organization_id
        ]

    async def update(
        self,
        membership: Membership,
    ) -> Membership | None:
        existing = self._memberships.get(membership.id)

        if existing is None:
            return None

        if existing.organization_id != membership.organization_id:
            return None

        self._memberships[membership.id] = membership

        return membership

    async def delete(
        self,
        membership_id: UUID,
        organization_id: UUID,
    ) -> bool:
        membership = self._memberships.get(membership_id)

        if membership is None:
            return False

        if membership.organization_id != organization_id:
            return False

        del self._memberships[membership_id]

        return True
