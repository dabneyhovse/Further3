from datetime import datetime, timedelta

from settings import Settings


def is_quiet_hours() -> bool:
    now: datetime = datetime.now()
    weekend: bool = (now + timedelta(hours=9)).weekday() >= 5
    start_hour: float = Settings.weekend_quiet_hours_start_time if weekend else Settings.normal_quiet_hours_start_time
    end_hour: float = Settings.quiet_hours_end_time
    current_hour: float = now.hour + now.minute / 60 + now.second / 3600
    return 0 <= (current_hour - start_hour) % 24 <= (end_hour - start_hour) % 24
