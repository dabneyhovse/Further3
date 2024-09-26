from __future__ import annotations

from abc import ABC, abstractmethod, abstractproperty
from collections.abc import Callable
from pathlib import Path

from gadt import GADT
from resource_handler import ResourceHandler


class AudioSource(ABC):
    @abstractmethod
    async def download(self, resource: ResourceHandler.Resource) -> Path: ...

    @property
    @abstractmethod
    async def name(self) -> str: ...

    @property
    @abstractmethod
    async def name(self) -> str: ...


class YoutubeDLAudioSource(AudioSource):
    class Query(metaclass=GADT):
        URL: Callable[[str], YoutubeDLAudioSource.Query]
        VideoSearchQuery: Callable[[str], YoutubeDLAudioSource.Query]
        # DabneyVictory: YoutubeDLAudioSource.Query
        # RealDabneyVictory: YoutubeDLAudioSource.Query

    def __init__(self, query: Query):
