from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from audio_sources import AudioSource
from duration import Duration
from resource_handler import ResourceHandler


class LocalAudioSource(AudioSource):
    file_path: Path

    def __init__(self, file_path: Path):
        self.file_path = file_path

    async def download(self, resource: ResourceHandler.Resource) -> Path:
        return self.file_path

    @property
    def title(self) -> str:
        return self.file_path.stem or "<Unknown local audio file>"

    @property
    def author_and_author_type(self) -> tuple[str, str]:
        # No metadata available for local files by default
        return "performer", "<Unknown>"

    @property
    def duration(self) -> Duration:
        # TODO: Implement
        return Duration.from_timedelta(timedelta(seconds=0))

    @property
    def url(self) -> None:
        return
