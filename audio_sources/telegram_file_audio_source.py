from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from telegram import Audio, File

from audio_sources import AudioSource
from duration import Duration
from resource_handler import ResourceHandler


class TelegramAudioSource(AudioSource):
    telegram_audio: Audio
    output_path: str | None

    def __init__(self, telegram_audio: Audio):
        self.output_path = None
        self.telegram_audio = telegram_audio

    async def download(self, resource: ResourceHandler.Resource) -> Path:
        file: File = await self.telegram_audio.get_file()
        default_path: Path = Path(file.file_path)
        download_path: Path = resource.path / default_path.name
        await file.download_to_drive(custom_path=download_path)
        return download_path

    @property
    def title(self) -> str:
        return self.telegram_audio.title or self.telegram_audio.file_name or "&lt;Unknown uploaded audio file&gt;"

    @property
    def author_and_author_type(self) -> tuple[str, str]:
        return "performer", self.telegram_audio.performer or "&lt;Unknown&gt;"

    @property
    def duration(self) -> Duration:
        return Duration.from_timedelta(timedelta(seconds=self.telegram_audio.duration))

    @property
    def url(self) -> None:
        return
