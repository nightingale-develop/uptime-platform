from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx2
import pytest

from uptime_platform.auth.dependencies import get_organization_context
from uptime_platform.auth.entities import OrganizationContext
from uptime_platform.main import app
from uptime_platform.monitors.entities import (
    HttpMonitorConfig,
    Monitor,
    MonitorStatus,
    MonitorType,
)
from uptime_platform.monitors.in_memory_repository import (
    InMemoryMonitorRepository,
)
from uptime_platform.organizations.constants import (
    DEFAULT_ORGANIZATION_ID,
)
from uptime_platform.status_pages.dependencies import (
    get_public_status_page_service,
    get_status_page_service,
)
from uptime_platform.status_pages.in_memory_repository import (
    InMemoryStatusPageRepository,
)
from uptime_platform.status_pages.service import (
    PublicStatusPageService,
    StatusPageService,
)

pytestmark = pytest.mark.anyio


def make_monitor(
    status: MonitorStatus = MonitorStatus.UP,
    name: str = "Production API",
    organization_id: UUID = DEFAULT_ORGANIZATION_ID,
) -> Monitor:
    now = datetime.now(UTC)

    return Monitor(
        id=uuid4(),
        organization_id=organization_id,
        name=name,
        monitor_type=MonitorType.HTTP,
        config=HttpMonitorConfig(
            url="https://example.com",
        ),
        interval_seconds=60,
        timeout_seconds=5,
        status=status,
        created_at=now,
        next_check_at=now,
    )


@pytest.fixture
def status_page_repository() -> InMemoryStatusPageRepository:
    return InMemoryStatusPageRepository()


@pytest.fixture
def monitor_repository() -> InMemoryMonitorRepository:
    return InMemoryMonitorRepository()


@pytest.fixture
async def client(
    status_page_repository: InMemoryStatusPageRepository,
    monitor_repository: InMemoryMonitorRepository,
    organization_context: OrganizationContext,
) -> AsyncIterator[httpx2.AsyncClient]:
    app.dependency_overrides[get_organization_context] = lambda: organization_context

    def override_status_page_service() -> StatusPageService:
        return StatusPageService(
            repository=status_page_repository,
            monitor_repository=monitor_repository,
            organization_id=organization_context.organization.id,
        )

    def override_public_status_page_service() -> PublicStatusPageService:
        return PublicStatusPageService(
            repository=status_page_repository,
            monitor_repository=monitor_repository,
        )

    app.dependency_overrides[get_status_page_service] = override_status_page_service

    app.dependency_overrides[get_public_status_page_service] = (
        override_public_status_page_service
    )

    transport = httpx2.ASGITransport(app=app)

    async with httpx2.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


async def test_create_status_page(
    client: httpx2.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production Status",
            "slug": "production",
            "published": True,
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert UUID(data["id"])
    assert data["name"] == "Production Status"
    assert data["slug"] == "production"
    assert data["published"] is True


async def test_duplicate_status_page_slug_returns_conflict(
    client: httpx2.AsyncClient,
) -> None:
    payload = {
        "name": "Production",
        "slug": "production",
        "published": True,
    }

    first_response = await client.post(
        "/api/v1/status-pages",
        json=payload,
    )

    second_response = await client.post(
        "/api/v1/status-pages",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


async def test_invalid_status_page_slug_returns_validation_error(
    client: httpx2.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production",
            "slug": "Production Status",
            "published": True,
        },
    )

    assert response.status_code == 422


async def test_get_status_pages(
    client: httpx2.AsyncClient,
) -> None:
    await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production",
            "slug": "production",
        },
    )

    await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Internal",
            "slug": "internal",
        },
    )

    response = await client.get("/api/v1/status-pages")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2

    slugs = {page["slug"] for page in data}

    assert slugs == {
        "production",
        "internal",
    }


async def test_update_status_page(
    client: httpx2.AsyncClient,
) -> None:
    create_response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production",
            "slug": "production",
            "published": True,
        },
    )

    page_id = create_response.json()["id"]

    response = await client.patch(
        f"/api/v1/status-pages/{page_id}",
        json={
            "name": "Production Services",
            "published": False,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["name"] == "Production Services"
    assert data["slug"] == "production"
    assert data["published"] is False


async def test_add_monitor_to_status_page(
    client: httpx2.AsyncClient,
    monitor_repository: InMemoryMonitorRepository,
) -> None:
    monitor = make_monitor()

    await monitor_repository.create(monitor)

    create_response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production",
            "slug": "production",
        },
    )

    page_id = create_response.json()["id"]

    response = await client.post(
        f"/api/v1/status-pages/{page_id}/monitors/{monitor.id}"
    )

    assert response.status_code == 204


@pytest.mark.parametrize(
    "payload",
    [{"name": None}, {"published": None}, {"name": "Changed", "published": None}],
)
async def test_status_page_patch_rejects_null_without_changing_page(
    client: httpx2.AsyncClient,
    payload: dict[str, str | None],
) -> None:
    created = await client.post(
        "/api/v1/status-pages",
        json={"name": "Production", "slug": "production", "published": True},
    )
    assert created.status_code == 201
    original = created.json()
    url = f"/api/v1/status-pages/{original['id']}"

    response = await client.patch(url, json=payload)

    assert response.status_code == 422
    current = await client.get(url)
    assert current.status_code == 200
    assert current.json() == original


@pytest.mark.parametrize(
    ("payload", "expected_name", "expected_published"),
    [
        ({}, "Production", True),
        ({"published": False}, "Production", False),
        ({"name": "Renamed"}, "Renamed", True),
    ],
)
async def test_status_page_patch_preserves_omitted_fields(
    client: httpx2.AsyncClient,
    payload: dict[str, str | bool],
    expected_name: str,
    expected_published: bool,
) -> None:
    created = await client.post(
        "/api/v1/status-pages",
        json={"name": "Production", "slug": "production", "published": True},
    )
    assert created.status_code == 201
    page_id = created.json()["id"]

    response = await client.patch(f"/api/v1/status-pages/{page_id}", json=payload)

    assert response.status_code == 200
    assert response.json()["name"] == expected_name
    assert response.json()["published"] is expected_published


async def test_add_same_monitor_twice_returns_conflict(
    client: httpx2.AsyncClient,
    monitor_repository: InMemoryMonitorRepository,
) -> None:
    monitor = make_monitor()

    await monitor_repository.create(monitor)

    create_response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production",
            "slug": "production",
        },
    )

    page_id = create_response.json()["id"]

    url = f"/api/v1/status-pages/{page_id}/monitors/{monitor.id}"

    first_response = await client.post(url)
    second_response = await client.post(url)

    assert first_response.status_code == 204
    assert second_response.status_code == 409


async def test_add_nonexistent_monitor_returns_not_found(
    client: httpx2.AsyncClient,
) -> None:
    create_response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production",
            "slug": "production",
        },
    )

    page_id = create_response.json()["id"]

    response = await client.post(f"/api/v1/status-pages/{page_id}/monitors/{uuid4()}")

    assert response.status_code == 404


async def test_public_status_page_returns_aggregate_status(
    client: httpx2.AsyncClient,
    monitor_repository: InMemoryMonitorRepository,
) -> None:
    website = make_monitor(
        status=MonitorStatus.UP,
        name="Website",
    )

    api = make_monitor(
        status=MonitorStatus.DOWN,
        name="API",
    )

    await monitor_repository.create(website)
    await monitor_repository.create(api)

    create_response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production Status",
            "slug": "production",
            "published": True,
        },
    )

    page_id = create_response.json()["id"]

    for monitor in (website, api):
        response = await client.post(
            f"/api/v1/status-pages/{page_id}/monitors/{monitor.id}"
        )

        assert response.status_code == 204

    response = await client.get("/status/production")

    assert response.status_code == 200

    data = response.json()

    assert data["name"] == "Production Status"
    assert data["slug"] == "production"
    assert data["status"] == "partial_outage"

    assert data["monitors"] == [
        {
            "id": str(website.id),
            "name": "Website",
            "status": "up",
        },
        {
            "id": str(api.id),
            "name": "API",
            "status": "down",
        },
    ]


async def test_unpublished_status_page_is_not_public(
    client: httpx2.AsyncClient,
) -> None:
    create_response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Internal Status",
            "slug": "internal",
            "published": False,
        },
    )

    assert create_response.status_code == 201

    response = await client.get("/status/internal")

    assert response.status_code == 404


async def test_public_status_page_with_unchecked_monitor_is_unknown(
    client: httpx2.AsyncClient,
    monitor_repository: InMemoryMonitorRepository,
) -> None:
    monitor = make_monitor(status=MonitorStatus.PENDING)
    await monitor_repository.create(monitor)
    created = await client.post(
        "/api/v1/status-pages",
        json={"name": "New deployment", "slug": "new-deployment"},
    )
    assert created.status_code == 201
    page_id = created.json()["id"]
    added = await client.post(f"/api/v1/status-pages/{page_id}/monitors/{monitor.id}")
    assert added.status_code == 204

    response = await client.get("/status/new-deployment")

    assert response.status_code == 200
    assert response.json()["status"] == "unknown"
    assert response.json()["monitors"][0]["status"] == "pending"


async def test_remove_monitor_from_status_page(
    client: httpx2.AsyncClient,
    monitor_repository: InMemoryMonitorRepository,
) -> None:
    monitor = make_monitor()

    await monitor_repository.create(monitor)

    create_response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production",
            "slug": "production",
        },
    )

    page_id = create_response.json()["id"]

    url = f"/api/v1/status-pages/{page_id}/monitors/{monitor.id}"

    add_response = await client.post(url)

    assert add_response.status_code == 204

    remove_response = await client.delete(url)

    assert remove_response.status_code == 204

    public_response = await client.get("/status/production")

    assert public_response.status_code == 200
    assert public_response.json()["monitors"] == []
    assert public_response.json()["status"] == "unknown"


async def test_delete_status_page(
    client: httpx2.AsyncClient,
) -> None:
    create_response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production",
            "slug": "production",
        },
    )

    page_id = create_response.json()["id"]

    response = await client.delete(f"/api/v1/status-pages/{page_id}")

    assert response.status_code == 204

    get_response = await client.get(f"/api/v1/status-pages/{page_id}")

    assert get_response.status_code == 404

    public_response = await client.get("/status/production")

    assert public_response.status_code == 404


async def test_cannot_add_monitor_from_another_organization(
    client: httpx2.AsyncClient,
    monitor_repository: InMemoryMonitorRepository,
) -> None:
    monitor = make_monitor(
        organization_id=uuid4(),
    )

    assert monitor.organization_id != DEFAULT_ORGANIZATION_ID

    await monitor_repository.create(monitor)

    create_response = await client.post(
        "/api/v1/status-pages",
        json={
            "name": "Production",
            "slug": "production",
        },
    )

    assert create_response.status_code == 201

    page_id = create_response.json()["id"]

    response = await client.post(
        f"/api/v1/status-pages/{page_id}/monitors/{monitor.id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Status page or monitor not found",
    }

    async def test_get_status_page_monitors(
        client: httpx2.AsyncClient,
        monitor_repository: InMemoryMonitorRepository,
    ) -> None:
        website = make_monitor(
            name="Website",
            status=MonitorStatus.UP,
        )
        api = make_monitor(
            name="API",
            status=MonitorStatus.DOWN,
        )

        await monitor_repository.create(website)
        await monitor_repository.create(api)

        create_response = await client.post(
            "/api/v1/status-pages",
            json={
                "name": "Internal",
                "slug": "internal",
                "published": False,
            },
        )

        page_id = create_response.json()["id"]

        for monitor in (website, api):
            response = await client.post(
                f"/api/v1/status-pages/{page_id}/monitors/{monitor.id}"
            )

            assert response.status_code == 204

        response = await client.get(f"/api/v1/status-pages/{page_id}/monitors")

        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(website.id),
                "name": "Website",
                "status": "up",
            },
            {
                "id": str(api.id),
                "name": "API",
                "status": "down",
            },
        ]
