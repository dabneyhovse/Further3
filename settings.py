from pathlib import Path

from persistent_singleton import persistent_singleton, PersistenceSource


@persistent_singleton(PersistenceSource.JSON, Path("store/admin_settings.json"))
class Settings:
    debug: bool = False

    # User and chat registration
    registered_chat_ids: list[int] = []
    owner_id: int
    comptroller_ids: list[int] = []

    # Volume control
    max_absolute_volume: float = 1
    hundred_percent_volume_value: float = 0.75

    # Times expressed as hours since midnight (e.g. 10:45 PM = 22.75)
    normal_quiet_hours_start_time: float = 22
    weekend_quiet_hours_start_time: float = 0
    quiet_hours_end_time: float = 7

    # Waiting refresh rates
    async_sleep_refresh_rate: float = 0.25

    # Automated error recovery
    flood_control_buffer_time: float = 1
    max_telegram_flood_control_retries: int = 4

    telegram_time_out_buffer_time: float = 1
    max_telegram_time_out_retries: int = 4
