import argparse
import asyncio
import sys

from pydantic import ValidationError
from sqlalchemy import select, text

from uptime_platform.auth.schemas import RegisterRequest
from uptime_platform.auth.service import AuthService
from uptime_platform.db.session import SessionFactory
from uptime_platform.organizations.entities import OrganizationRole
from uptime_platform.organizations.models import MembershipModel, OrganizationModel
from uptime_platform.organizations.sqlalchemy_repository import (
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
)
from uptime_platform.users.models import UserModel
from uptime_platform.users.sqlalchemy_repository import SqlAlchemyUserRepository


async def bootstrap_admin(data: RegisterRequest) -> int:
    async with SessionFactory() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(731042, 1)"))

        existing_user_id = await session.scalar(select(UserModel.id).limit(1))

        if existing_user_id is not None:
            owner_id = await session.scalar(
                select(UserModel.id)
                .join(
                    MembershipModel,
                    MembershipModel.user_id == UserModel.id,
                )
                .join(
                    OrganizationModel,
                    OrganizationModel.id == MembershipModel.organization_id,
                )
                .where(
                    UserModel.email == str(data.email).lower(),
                    MembershipModel.role == OrganizationRole.OWNER,
                    OrganizationModel.name == data.organization_name,
                )
                .limit(1)
            )

            if owner_id is None:
                print(
                    "Database already contains users; refusing to "
                    "create another bootstrap administrator.",
                    file=sys.stderr,
                )
                return 1

            print("Administrator already exists; password was not changed.")
            return 0

        service = AuthService(
            user_repository=SqlAlchemyUserRepository(session),
            organization_repository=SqlAlchemyOrganizationRepository(session),
            membership_repository=SqlAlchemyMembershipRepository(session),
        )

        result = await service.register(data)

    print(f"Created organization owner: {result.user.email}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Uptime Platform administrative CLI")

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    bootstrap = subparsers.add_parser("bootstrap-admin")

    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--organization", required=True)

    args = parser.parse_args()

    if sys.stdin.isatty():
        parser.error("Supply the password on stdin, not as a command argument.")

    password = sys.stdin.readline().removesuffix("\n")

    if not password:
        parser.error("Administrator password is missing from stdin.")

    try:
        data = RegisterRequest(
            email=args.email,
            password=password,
            organization_name=args.organization,
        )
    except ValidationError:
        print(
            "Invalid email, password (8-128 chars), or organization name.",
            file=sys.stderr,
        )
        return 2

    try:
        return asyncio.run(bootstrap_admin(data))
    except Exception as exc:  # noqa: BLE001
        print(
            f"Bootstrap failed ({type(exc).__name__}); check DB and migrations.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
