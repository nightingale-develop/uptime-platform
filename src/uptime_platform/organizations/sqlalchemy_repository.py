from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uptime_platform.organizations.entities import (
    Membership,
    Organization,
)
from uptime_platform.organizations.models import (
    MembershipModel,
    OrganizationModel,
)


class SqlAlchemyOrganizationRepository:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        organization: Organization,
    ) -> Organization:
        model = OrganizationModel(
            id=organization.id,
            name=organization.name,
            created_at=organization.created_at,
        )

        self._session.add(model)

        await self._session.flush()
        await self._session.refresh(model)

        return self._to_entity(model)

    async def get_by_id(
        self,
        organization_id: UUID,
    ) -> Organization | None:
        model = await self._session.get(
            OrganizationModel,
            organization_id,
        )

        if model is None:
            return None

        return self._to_entity(model)

    async def get_by_id_for_update(
        self,
        organization_id: UUID,
    ) -> Organization | None:
        statement = (
            select(OrganizationModel)
            .where(OrganizationModel.id == organization_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        result = await self._session.execute(statement)

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_entity(model)

    async def update(
        self,
        organization: Organization,
    ) -> Organization:
        model = await self._session.get(
            OrganizationModel,
            organization.id,
        )

        if model is None:
            raise LookupError(f"Organization {organization.id} not found")

        model.name = organization.name

        await self._session.flush()
        await self._session.refresh(model)

        return self._to_entity(model)

    @staticmethod
    def _to_entity(
        model: OrganizationModel,
    ) -> Organization:
        return Organization(
            id=model.id,
            name=model.name,
            created_at=model.created_at,
        )


class SqlAlchemyMembershipRepository:
    async def lock_organization(self, organization_id: UUID) -> None:
        await self._session.execute(
            select(OrganizationModel.id)
            .where(OrganizationModel.id == organization_id)
            .with_for_update()
        )

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        membership: Membership,
    ) -> Membership:
        model = MembershipModel(
            id=membership.id,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            role=membership.role,
            created_at=membership.created_at,
        )

        self._session.add(model)

        await self._session.flush()
        await self._session.refresh(model)

        return self._to_entity(model)

    async def get_by_user_and_organization(
        self,
        user_id: UUID,
        organization_id: UUID,
    ) -> Membership | None:
        statement = select(MembershipModel).where(
            MembershipModel.user_id == user_id,
            MembershipModel.organization_id == organization_id,
        )

        result = await self._session.execute(statement)

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_entity(model)

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> list[Membership]:
        statement = (
            select(MembershipModel)
            .where(MembershipModel.user_id == user_id)
            .order_by(MembershipModel.created_at)
        )

        result = await self._session.execute(statement)

        return [self._to_entity(model) for model in result.scalars().all()]

    async def get_by_organization_id(
        self,
        organization_id: UUID,
    ) -> list[Membership]:
        statement = (
            select(MembershipModel)
            .where(MembershipModel.organization_id == organization_id)
            .order_by(MembershipModel.created_at)
        )

        result = await self._session.execute(statement)

        return [self._to_entity(model) for model in result.scalars().all()]

    async def update(
        self,
        membership: Membership,
    ) -> Membership | None:
        statement = select(MembershipModel).where(
            MembershipModel.id == membership.id,
            MembershipModel.organization_id == membership.organization_id,
        )

        result = await self._session.execute(statement)

        model = result.scalar_one_or_none()

        if model is None:
            return None

        model.role = membership.role

        await self._session.flush()
        await self._session.refresh(model)

        return self._to_entity(model)

    async def delete(
        self,
        membership_id: UUID,
        organization_id: UUID,
    ) -> bool:
        statement = select(MembershipModel).where(
            MembershipModel.id == membership_id,
            MembershipModel.organization_id == organization_id,
        )

        result = await self._session.execute(statement)

        model = result.scalar_one_or_none()

        if model is None:
            return False

        await self._session.delete(model)
        await self._session.flush()

        return True

    @staticmethod
    def _to_entity(
        model: MembershipModel,
    ) -> Membership:
        return Membership(
            id=model.id,
            organization_id=model.organization_id,
            user_id=model.user_id,
            role=model.role,
            created_at=model.created_at,
        )
