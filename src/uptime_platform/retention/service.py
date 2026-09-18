import asyncio
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from uptime_platform.core.config import Settings
from uptime_platform.retention.repository import RetentionRepository

logger = logging.getLogger(__name__)


class RetentionService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    async def run_once(self) -> dict[str, int]:
        if not self._settings.retention_enabled:
            return {}
        async with asyncio.timeout(30):
            async with self._session_factory() as session, session.begin():
                now = await session.scalar(select(func.now()))
                return await RetentionRepository(session).cleanup(
                    settings=self._settings,
                    now=now,
                )

    async def run_forever(self) -> None:
        if not self._settings.retention_enabled:
            return
        while True:
            try:
                counts = await self.run_once()
                if any(counts.values()):
                    logger.info("retention deleted %s", counts)
            except Exception:
                logger.exception("retention cleanup failed; retrying next interval")
            await asyncio.sleep(self._settings.retention_interval_seconds)
