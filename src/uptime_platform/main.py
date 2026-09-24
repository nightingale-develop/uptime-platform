from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from uptime_platform.api_keys.router import (
    router as api_keys_router,
)
from uptime_platform.auth.router import (
    router as auth_router,
)
from uptime_platform.checks.router import (
    router as checks_router,
)
from uptime_platform.core.metrics_router import router as metrics_router
from uptime_platform.core.web_config import (
    get_web_settings,
)
from uptime_platform.incidents.router import (
    router as incidents_router,
)
from uptime_platform.maintenance.router import (
    router as maintenance_router,
)
from uptime_platform.monitors.router import (
    router as monitors_router,
)
from uptime_platform.notifications.router import (
    router as notifications_router,
)
from uptime_platform.organizations.member_router import (
    router as organization_members_router,
)
from uptime_platform.organizations.router import (
    router as organizations_router,
)
from uptime_platform.statistics.router import (
    router as statistics_router,
)
from uptime_platform.status_pages.router import (
    router as status_pages_router,
)

app = FastAPI(
    title="Uptime Platform API",
    version="1.3.10",
)

web_settings = get_web_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=web_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    include_in_schema=False,
)
async def health() -> dict[str, str]:
    return {
        "status": "ok",
    }


app.include_router(auth_router)
app.include_router(monitors_router)
app.include_router(checks_router)
app.include_router(incidents_router)
app.include_router(notifications_router)
app.include_router(maintenance_router)
app.include_router(status_pages_router)
app.include_router(statistics_router)
app.include_router(organizations_router)
app.include_router(api_keys_router)
app.include_router(organization_members_router)

app.include_router(metrics_router)
