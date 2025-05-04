from pathlib import Path

from persistent_singleton import persistent_singleton, PersistenceSource


@persistent_singleton(PersistenceSource.JSON, Path("store/admin_settings.json"))
class Settings:
    debug: bool = False

    # Bot config paths
    further_bot_token_path: str = "sensitive/further_bot_token.txt"
    supervisor_bot_token_path: str = "sensitive/supervisor_bot_token.txt"

    # User and chat registration
    registered_primary_chat_id: int
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

    # Hampter
    hampter_path: str | None = "audio_files/hampter.wav"

    # Amogus
    amogus_ban_id: int

    # Yt-dlp
    # TODO: Set type to save
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
        'postprocessors': [{  # Extract audio using ffmpeg
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }]
    }

    telegram_time_out_buffer_time: float = 1
    max_telegram_time_out_retries: int = 4
