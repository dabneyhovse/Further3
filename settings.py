from pathlib import Path

from persistent_singleton import persistent_singleton, PersistenceSource


@persistent_singleton(PersistenceSource.JSON, Path("store/admin_settings.json"))
class Settings:
    async_sleep_refresh_rate: float = 0.25
    max_absolute_volume: float = 1
