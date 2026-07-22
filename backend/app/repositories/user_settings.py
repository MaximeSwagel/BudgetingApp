from sqlalchemy import select

from app.models import UserSettings
from app.repositories.base import BaseRepository


class UserSettingsRepository(BaseRepository[UserSettings]):
    model = UserSettings

    async def get_by_key(self, key: str) -> UserSettings | None:
        result = await self.db.execute(select(UserSettings).where(UserSettings.key == key))
        return result.scalar_one_or_none()

    async def upsert(self, key: str, value: str) -> UserSettings:
        row = await self.get_by_key(key)
        if row:
            row.value = value
            return row
        row = UserSettings(key=key, value=value)
        self.add(row)
        return row

    async def all_dict(self) -> dict[str, str]:
        result = await self.db.execute(select(UserSettings))
        return {row.key: row.value for row in result.scalars().all()}
