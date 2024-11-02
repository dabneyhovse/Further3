from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta
from pathlib import Path

from duration import Duration
from resource_handler import ResourceHandler


class AudioSource(ABC):
    @abstractmethod
    async def download(self, resource: ResourceHandler.Resource) -> Path: ...

    @property
    @abstractmethod
    def title(self) -> str: ...

    @property
    @abstractmethod
    def duration(self) -> Duration: ...

    @property
    @abstractmethod
    def author_and_author_type(self) -> tuple[str, str]: ...

    @property
    @abstractmethod
    def url(self) -> str | None: ...
