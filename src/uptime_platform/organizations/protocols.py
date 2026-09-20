from typing import Protocol
from uuid import UUID

from uptime_platform.organizations.entities import (
    Membership,
    Organization,
)


class OrganizationRepositoryProtocol(Protocol):
    async def create(
        self,
        organization: Organization,
    ) -> Organization: ...

    async def get_by_id(
        self,
        organization_id: UUID,
    ) -> Organization | None: ...

    async def get_by_id_for_update(
        self,
        organization_id: UUID,
    ) -> Organization | None: ...

    async def update(
        self,
        organization: Organization,
    ) -> Organization: ...


class MembershipRepositoryProtocol(Protocol):
    async def lock_organization(self, organization_id: UUID) -> None: ...

    async def create(
        self,
        membership: Membership,
    ) -> Membership: ...

    async def get_by_user_and_organization(
        self,
        user_id: UUID,
        organization_id: UUID,
    ) -> Membership | None: ...

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> list[Membership]: ...

    async def get_by_organization_id(
        self,
        organization_id: UUID,
    ) -> list[Membership]: ...

    async def update(
        self,
        membership: Membership,
    ) -> Membership | None: ...

    async def delete(
        self,
        membership_id: UUID,
        organization_id: UUID,
    ) -> bool: ...
