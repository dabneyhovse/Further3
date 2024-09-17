from pathlib import Path

from persistent_singleton import persistent_singleton, PersistenceSource


@persistent_singleton(PersistenceSource.JSON, Path("store/admin_settings.json"))
class Settings:
    debug: bool = False

    registered_chat_ids: list[int] = []
    owner_id: int
    comptroller_ids: list[int] = []

    async_sleep_refresh_rate: float = 0.25

    max_absolute_volume: float = 1
    hundred_percent_volume_value: float = 0.75
