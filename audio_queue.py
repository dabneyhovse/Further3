from asyncio import sleep, get_event_loop, Future, CancelledError, Task, create_task, to_thread
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from enum import Enum
from os import PathLike
from pathlib import Path

from vlc import Instance, MediaPlayer, Media
from vlc import State as VLCState

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
    message_setter: Callable[[str, int], Coroutine[None, None, None]]
    path: Future[PathLike | None]
    download_task: Future[Task]
    active: bool = False
    skipped: bool = False

    @property
    def freed(self) -> bool:
        return not self.resource.is_open

    @staticmethod
    def _download_audio(stream: Stream, resource_path: str) -> Path:
        out = Path(stream.download(mp3=True, output_path=resource_path))
        return out

    async def set_message(self, message: str, skippable: bool = True) -> None:
        await self.message_setter(message, self.id if skippable else None)

    async def download(self):
        try:
            await self.set_message("Downloading")
            stream: Stream = self.video.streams.get_audio_only()
            path: PathLike = await to_thread(self._download_audio, stream, self.resource.path)
            await self.set_message("Processing")
            # TODO: Process audio
            await self.set_message("Queued")
        except CancelledError:
            assert self.skipped
            self.path.set_result(None)
            raise
        self.path.set_result(path)

    async def skip(self, username: str) -> bool:
        if self.skipped or self.freed:
            return False
        self.skipped = True
        self.active = False
        if not self.active:
            download_task = await self.download_task
            download_task.cancel()
        self.resource.close()
        await self.set_message(f"Skipped by {username}", skippable=False)

    async def finish(self):
        if not self.freed:
            self.resource.close()
        self.active = False
        if not self.skipped:
            await self.set_message(f"Played", skippable=False)


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

    async def add(self, element: AudioQueueElement):
        await self.queue.append(element)
        download_task = get_event_loop().create_task(element.download())
        element.download_task.set_result(download_task)

    async def play_queue(self) -> None:
        async with self.queue.async_iter() as async_iterator:
            async for element in async_iterator:
                if element.skipped:
                    continue
                self.current = element
                path: str = await element.path
                if path is None:
                    assert element.skipped
                    continue
                media: Media = self.instance.media_new_path(path)
                self.player.set_media(media)

                await element.set_message("Playing")

                self.player.play()
                element.active = True

                while self.player.get_state() not in (VLCState.Ended, VLCState.Stopped) and not element.skipped:
                    # TODO: Wait for the duration or skip (whichever first)
                    await sleep(Settings.async_sleep_refresh_rate)

                if self.player.get_state() not in (VLCState.Ended, VLCState.Stopped):
                    self.player.stop()

                # TODO: release() media if needed
                await element.finish()
                self.current = None

    async def skip(self, username: str) -> bool:
        if self.current is None:
            return False
        await self.current.skip(username)
        return True

    async def skip_all(self, username: str) -> bool:
        if self.state == AudioQueue.State.EMPTY:
            return False
        for element in self.queue.reverse_destructive_iter:
            await element.skip(username)
        await self.current.skip(username)

    async def skip_specific(self, username: str, id: int) -> bool:
        if self.current is not None and self.current.id == id:
            return await self.skip(username)
        for element in self.queue:
            if element.id == id:
                await element.skip(username)
                return True
        return False

    async def pause(self) -> None:
        self.player.set_pause(True)

    async def resume(self) -> None:

        self.player.set_pause(False)

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
            case (player_state, queue_nonempty, current_set):
                print(f"Unknown audio queue state error:\n"
                      f"\tself.player.get_state(): {player_state}\n"
                      f"\tbool(self.queue): {queue_nonempty}\n"
                      f"\tself.current is not None: {current_set}"
                      f"\tself.queue: {self.queue}"
                      f"\tself.current: {self.current}")
                return AudioQueue.State.UNKNOWN_ERROR

    def get_id(self) -> int:
        out: int = self._next_id
        self._next_id += 1
        return out

    def __iter__(self):
        return iter(self.queue)
