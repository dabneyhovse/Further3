from asyncio import sleep, get_event_loop, Future
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from enum import Enum
from os import PathLike
from pathlib import Path

from vlc import Instance, MediaPlayer, Media
from vlc import State as VLCState

from async_multiprocessing import await_process
from async_queue import AsyncQueue
from audio_processing import AudioProcessingSettings
from pytubefix import YouTube, Stream
from resource_handler import ResourceHandler
from settings import Settings


@dataclass
class AudioQueueElement:
    id: int
    resource: ResourceHandler.Resource
    video: YouTube
    processing: AudioProcessingSettings
    set_message: Callable[[str, int], Coroutine[None, None, None]]
    path: Future[PathLike]
    active: bool = False
    skipped: bool = False

    @property
    def freed(self) -> bool:
        return not self.resource.is_open

    @staticmethod
    def _download_audio(stream: Stream, resource_path: str) -> Path:
        out = Path(stream.download(mp3=True, output_path=resource_path))
        print("Downloaded")
        return out

    async def download(self):
        await self.set_message("Downloading", self.id)
        stream: Stream = self.video.streams.get_audio_only()
        self.path.set_result(await await_process(self._download_audio, args=(stream, self.resource.path)))
        print("Download process await complete")
        await self.set_message("Processing", self.id)
        # TODO: Process audio
        await self.set_message("Queued", self.id)
        print("Download function complete")


class AudioQueue(Iterable[AudioQueueElement]):
    class State(Enum):
        LOADING = 0
        EMPTY = 1
        PAUSED = 2
        PLAYING = 3
        UNKNOWN_ERROR = 4
        VLC_ERROR = 5

        def __str__(self):
            match self:
                case AudioQueue.State.LOADING:
                    return "Loading"
                case AudioQueue.State.EMPTY:
                    return "Empty"
                case AudioQueue.State.PAUSED:
                    return "Paused"
                case AudioQueue.State.PLAYING:
                    return "Playing"
                case AudioQueue.State.UNKNOWN_ERROR:
                    return "Unknown Error"
                case AudioQueue.State.VLC_ERROR:
                    return "VLC Error"

    queue: AsyncQueue[AudioQueueElement]
    instance: Instance
    player: MediaPlayer
    current: AudioQueueElement | None = None
    _next_id: int = 0

    def __init__(self):
        self.queue = AsyncQueue()
        self.instance = Instance()
        self.player = self.instance.media_player_new()
        get_event_loop().create_task(self.play_queue())

    @property
    def is_playing(self) -> bool:
        return self.player.is_playing()

    async def add(self, element: AudioQueueElement):
        print("Adding element to queue")
        await self.queue.append(element)
        print("Append complete")
        await element.download()
        print("Download await received")

    async def play_queue(self) -> None:
        async with self.queue.async_iter() as async_iterator:
            async for element in async_iterator:
                self.current = element
                print("Waiting for path")
                path: str = await element.path
                print("Acquired path")
                media: Media = self.instance.media_new_path(path)
                self.player.set_media(media)

                self.player.play()
                element.active = True

                while self.is_playing:  # TODO: Check for skip?
                    # TODO: Wait for the duration or skip (whichever first)
                    await sleep(Settings.async_sleep_refresh_rate)

                # TODO: release() media if needed
                element.active = False
                element.resource.close()
                self.current = None

    async def skip_all(self) -> bool:
        if not self.is_playing and not self.queue:
            return False
        for element in self.queue.destructive_iter:
            element.skipped = True
        self.player.stop()

    async def pause(self) -> None:
        self.player.set_pause(True)

    async def resume(self) -> None:

        self.player.set_pause(False)

    async def skip(self) -> bool:
        if not self.is_playing and not self.queue:
            return False
        for element in self.queue.destructive_iter:
            element.skipped = True
            element.active = False
        self.player.stop()
        return True

    async def set_digital_volume(self, volume: float) -> bool:
        absolute_volume: float = volume * Settings.hundred_percent_volume_value
        if 0 <= absolute_volume <= Settings.max_absolute_volume * 100:
            return self.player.audio_set_volume(round(absolute_volume)) + 1
        else:
            return False

    async def set_clamped_digital_volume(self, volume: float) -> bool:
        absolute_volume: float = volume * Settings.hundred_percent_volume_value
        absolute_volume = min(max(absolute_volume, 0), Settings.max_absolute_volume * 100)
        return self.player.audio_set_volume(round(absolute_volume)) + 1

    async def get_digital_volume(self) -> float:
        scaled_volume = self.player.audio_get_volume()
        return scaled_volume / Settings.hundred_percent_volume_value

    @property
    def state(self) -> State:
        print(f"Current state:"
              f"\n\tself.player.get_state(): {self.player.get_state()}"
              f"\n\tself.queue: {self.queue}"
              f"\n\tself.current: {self.current}")
        match (self.player.get_state(), bool(self.queue), self.current is not None):
            case (VLCState.Playing, _, True):
                return AudioQueue.State.PLAYING
            case (VLCState.Paused, _, True):
                return AudioQueue.State.PAUSED
            case (VLCState.Ended | VLCState.Stopped | VLCState.NothingSpecial, False, False):
                return AudioQueue.State.EMPTY
            case (VLCState.Error, _, _):
                return AudioQueue.State.VLC_ERROR
            case (_, True, False):
                return AudioQueue.State.LOADING
            case (VLCState.Ended | VLCState.Stopped | VLCState.NothingSpecial, _, True):
                return AudioQueue.State.LOADING
            case (VLCState.Opening | VLCState.Buffering, _, True):
                return AudioQueue.State.LOADING
            case _:
                print(f"Unknown state:"
                      f"\n\tself.player.get_state(): {self.player.get_state()}"
                      f"\n\tself.queue: {self.queue}"
                      f"\n\tself.current: {self.current}")
                return AudioQueue.State.UNKNOWN_ERROR

    def get_id(self) -> int:
        out: int = self._next_id
        self._next_id += 1
        return out

    def __iter__(self):
        return iter(self.queue)
