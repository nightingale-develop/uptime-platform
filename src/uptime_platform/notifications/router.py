from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from uptime_platform.auth.dependencies import (
    require_admin,
)
from uptime_platform.auth.entities import (
    OrganizationContext,
)
from uptime_platform.notifications.destination_dependencies import (
    get_notification_destination_service,
)
from uptime_platform.notifications.destination_service import (
    NotificationDestinationService,
)
from uptime_platform.notifications.entities import (
    NotificationDestination,
)
from uptime_platform.notifications.schemas import (
    NotificationDestinationCreate,
    NotificationDestinationResponse,
    NotificationDestinationUpdate,
)


class NotificationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=[
                        {key: error[key] for key in ("type", "loc", "msg")}
                        for error in exc.errors()
                    ],
                ) from None

        return handle


router = APIRouter(
    prefix="/api/v1/notification-destinations",
    tags=["notification destinations"],
    route_class=NotificationRoute,
)


@router.post(
    "",
    response_model=NotificationDestinationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_destination(
    data: NotificationDestinationCreate,
    service: Annotated[
        NotificationDestinationService,
        Depends(get_notification_destination_service),
    ],
    _context: Annotated[
        OrganizationContext,
        Depends(require_admin),
    ],
) -> NotificationDestination:
    return await service.create(data)


@router.get(
    "",
    response_model=list[NotificationDestinationResponse],
)
async def list_destinations(
    service: Annotated[
        NotificationDestinationService,
        Depends(get_notification_destination_service),
    ],
) -> list[NotificationDestination]:
    return await service.get_all()


@router.get(
    "/{destination_id}",
    response_model=NotificationDestinationResponse,
)
async def get_destination(
    destination_id: UUID,
    service: Annotated[
        NotificationDestinationService,
        Depends(get_notification_destination_service),
    ],
) -> NotificationDestination:
    destination = await service.get_by_id(destination_id)

    if destination is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification destination not found",
        )

    return destination


@router.patch(
    "/{destination_id}",
    response_model=NotificationDestinationResponse,
)
async def update_destination(
    destination_id: UUID,
    data: NotificationDestinationUpdate,
    service: Annotated[
        NotificationDestinationService,
        Depends(get_notification_destination_service),
    ],
    _context: Annotated[
        OrganizationContext,
        Depends(require_admin),
    ],
) -> NotificationDestination:
    try:
        destination = await service.update(destination_id, data)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Destination config type does not match destination type",
        ) from None

    if destination is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification destination not found",
        )

    return destination


@router.delete(
    "/{destination_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_destination(
    destination_id: UUID,
    service: Annotated[
        NotificationDestinationService,
        Depends(get_notification_destination_service),
    ],
    _context: Annotated[
        OrganizationContext,
        Depends(require_admin),
    ],
) -> Response:
    deleted = await service.delete(destination_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification destination not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
