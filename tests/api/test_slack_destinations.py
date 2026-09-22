from dataclasses import replace
from uuid import UUID, uuid4

import httpx2
import pytest

from uptime_platform.auth.dependencies import get_organization_context
from uptime_platform.main import app
from uptime_platform.notifications.destination_dependencies import (
    get_notification_destination_repository,
)
from uptime_platform.notifications.in_memory_repository import (
    InMemoryNotificationDestinationRepository,
)
from uptime_platform.organizations.entities import OrganizationRole

pytestmark = pytest.mark.anyio
ENDPOINT = "/api/v1/notification-destinations"
HOOK = "https://hooks.slack.com/services/T0123/B0456/secret-hook-value"
ROTATED_HOOK = "https://hooks.slack.com/services/T0123/B0456/rotated-hook-value"


def payload(webhook_url=HOOK):
    return {
        "name": "Production Slack",
        "destination_type": "slack",
        "config": {"webhook_url": webhook_url},
    }


@pytest.fixture
def repository():
    return InMemoryNotificationDestinationRepository()


@pytest.fixture
async def client(repository, organization_context):
    app.dependency_overrides[get_organization_context] = lambda: organization_context
    app.dependency_overrides[get_notification_destination_repository] = lambda: (
        repository
    )
    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_slack_crud_hides_secret_and_preserves_or_rotates_webhook(
    client, repository, organization_context
):
    created = await client.post(ENDPOINT, json=payload())
    assert created.status_code == 201
    data = created.json()
    assert data["name"] == "Production Slack"
    assert data["destination_type"] == "slack"
    assert data["config"] == {}
    assert HOOK not in created.text
    endpoint = f"{ENDPOINT}/{data['id']}"
    for response in (await client.get(endpoint), await client.get(ENDPOINT)):
        assert response.status_code == 200
        assert "secret-hook-value" not in response.text

    for update in ({"name": "Renamed", "enabled": False}, {"config": {}}):
        response = await client.patch(endpoint, json=update)
        assert response.status_code == 200
        assert response.json()["config"] == {}
        stored = await repository.get_by_id(
            UUID(data["id"]), organization_context.organization.id
        )
        assert stored.config.webhook_url == HOOK

    response = await client.patch(
        endpoint, json={"config": {"webhook_url": ROTATED_HOOK}}
    )
    assert response.status_code == 200
    assert response.json()["config"] == {}
    stored = await repository.get_by_id(
        UUID(data["id"]), organization_context.organization.id
    )
    assert stored.config.webhook_url == ROTATED_HOOK
    assert stored.enabled is False
    assert (await client.delete(endpoint)).status_code == 204
    assert (await client.get(endpoint)).status_code == 404


@pytest.mark.parametrize("host", ["hooks.slack.com", "hooks.slack-gov.com"])
async def test_slack_accepts_official_webhook_hosts(client, host):
    response = await client.post(
        ENDPOINT, json=payload(f"https://{host}/services/T01/B02/valid-secret")
    )
    assert response.status_code == 201
    assert response.json()["config"] == {}


@pytest.mark.parametrize(
    "webhook_url",
    [
        "http://hooks.slack.com/services/T01/B02/private-hook",
        "https://hooks.slack.com.evil.example/services/T01/B02/private-hook",
        "https://evil.example/services/T01/B02/private-hook",
        "https://hooks.slack.com@evil.example/services/T01/B02/private-hook",
        "https://user:pass@hooks.slack.com/services/T01/B02/private-hook",
        "https://hooks.slack.com:8443/services/T01/B02/private-hook",
        "https://hooks.slack.com/services/T01/B02/private-hook?token=secret",
        "https://hooks.slack.com/services/T01/B02/private-hook#fragment",
        "https://hooks.slack.com/services/T01/B02/private-hook/extra",
        "https://hooks.slack.com/services/T01/B02",
        "https://hooks.slack.com/services/T01/B02/%2fsecret",
        "https://hooks.slack.com/api/chat.postMessage",
        "",
        None,
    ],
)
async def test_slack_rejects_invalid_webhook(client, webhook_url):
    response = await client.post(ENDPOINT, json=payload(webhook_url))
    assert response.status_code == 422
    assert "private-hook" not in response.text
    assert (await client.get(ENDPOINT)).json() == []


@pytest.mark.parametrize(
    "config", [{"webhook_url": None}, {"webhook_url": ""}, {"chat_id": "123"}]
)
async def test_slack_invalid_patch_does_not_replace_existing_secret(
    client, repository, organization_context, config
):
    created = await client.post(ENDPOINT, json=payload())
    destination_id = UUID(created.json()["id"])
    response = await client.patch(
        f"{ENDPOINT}/{destination_id}", json={"config": config}
    )
    assert response.status_code == 422
    stored = await repository.get_by_id(
        destination_id, organization_context.organization.id
    )
    assert stored.config.webhook_url == HOOK


async def test_slack_destination_is_inaccessible_from_other_organization(
    client, organization_context
):
    created = await client.post(ENDPOINT, json=payload())
    endpoint = f"{ENDPOINT}/{created.json()['id']}"
    other_id = uuid4()
    other_context = replace(
        organization_context,
        organization=replace(organization_context.organization, id=other_id),
        membership=replace(organization_context.membership, organization_id=other_id),
    )
    app.dependency_overrides[get_organization_context] = lambda: other_context
    assert (await client.get(ENDPOINT)).json() == []
    assert (await client.get(endpoint)).status_code == 404
    assert (await client.patch(endpoint, json={"name": "Stolen"})).status_code == 404
    assert (await client.delete(endpoint)).status_code == 404


@pytest.mark.parametrize("role", [OrganizationRole.MEMBER, OrganizationRole.VIEWER])
async def test_slack_write_operations_require_admin(client, organization_context, role):
    created = await client.post(ENDPOINT, json=payload())
    endpoint = f"{ENDPOINT}/{created.json()['id']}"
    context = replace(
        organization_context,
        membership=replace(organization_context.membership, role=role),
    )
    app.dependency_overrides[get_organization_context] = lambda: context
    assert (await client.get(endpoint)).status_code == 200
    assert (await client.post(ENDPOINT, json=payload())).status_code == 403
    assert (await client.patch(endpoint, json={"enabled": False})).status_code == 403
    assert (await client.delete(endpoint)).status_code == 403
