import traceback
from asyncio import sleep, get_event_loop, Future, CancelledError, Task, TaskGroup, to_thread
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from enum import Enum
from os import PathLike
from pathlib import Path
from sys import stderr

from vlc import Instance, MediaPlayer, Media
from vlc import State as VLCState

from async_queue import AsyncQueue
from audio_processing import AudioProcessingSettings, process_audio, VLCModificationSettings
from audio_sources import AudioSource
from duration import Duration
from message_edit_status_callback import MessageEditStatusCallback
from quiet_hours import is_quiet_hours
from resource_handler import ResourceHandler
from settings import Settings
from audio_sources.local_audio_source import LocalAudioSource

import os

@dataclass
class AudioQueueElement:
    element_id: int
    resource: ResourceHandler.Resource | None
    audio_source: AudioSource
    processing: AudioProcessingSettings
    message_setter: MessageEditStatusCallback | None
    path: Future[PathLike | None]
    download_task: Future[Task]
    active: bool = False
    skipped: bool = False
    vlc_settings: VLCModificationSettings | None = None

    @property
    def freed(self) -> bool:
        return self.resource is not None and not self.resource.is_open

    async def set_message(self, message: str, skippable: bool = True) -> None:
        if self.message_setter is None:
            return
        try:
            await self.message_setter(message, self.element_id if skippable else None, self.audio_source.url)
        except Exception as e:
            print("Caught exception in audio_queue/set_message")
            traceback.print_exception(type(e), e, e.__traceback__, file=stderr)

    async def download(self):
        try:
            await self.set_message("Downloading")
            path: Path = await self.audio_source.download(self.resource)
            # path: Path = await to_thread(self.audio_source.download, self.resource)
            if self.processing.requires_audio_processing:
                # TODO: Support processing with no source
                if self.resource is None:
                    await self.skip("@WhoopsNoResourceFIXME")
                    raise CancelledError()
                await self.set_message("Processing")  # Can be removed if Telegram throttling is too bad
                processed_path: Path = self.resource.path / "processed.mp3"
                self.vlc_settings = await process_audio(path, processed_path, self.processing)
                path = processed_path
            else:
                self.vlc_settings = VLCModificationSettings()
            await self.set_message("Queued", True)
            self.path.set_result(path)
        except CancelledError:
            assert self.skipped
            self.path.set_result(None)
            raise

    async def skip(self, username: str) -> bool:
        if self.skipped or self.freed:
            return False
        self.skipped = True
        self.active = False
        if not self.active:
            download_task = await self.download_task
            download_task.cancel()
        if self.resource is not None:
            self.resource.close()
        await self.set_message(f"Skipped by {username}", skippable=False)

    async def finish(self):
        if not self.freed and self.resource is not None:
            self.resource.close()
        self.active = False
        if not self.skipped:
            await self.set_message(f"Played", skippable=False)

    @property
    def duration(self) -> Duration:
        return self.audio_source.duration / self.processing.tempo_scale


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
    sfx_queue: AsyncQueue[AudioQueueElement]
    instance: Instance
    main_player: MediaPlayer
    sfx_player: MediaPlayer
    current: AudioQueueElement | None = None
    _next_id: int = 0

    def __init__(self):
        self.queue = AsyncQueue()
        self.sfx_queue = AsyncQueue()
        self.instance = Instance()
        self.main_player = self.instance.media_player_new()
        self.sfx_player = self.instance.media_player_new()
        get_event_loop().create_task(self.play_queue())
        get_event_loop().create_task(self.play_sfx_queue())

    async def add(self, element: AudioQueueElement):
        await self.queue.append(element)
        download_task = get_event_loop().create_task(element.download())
        element.download_task.set_result(download_task)

    async def add_sfx(self, sfx: str):
        path = Path(os.path.join(Settings.sfx_path, sfx))
        if not os.path.exists(path):
            print(f"Sound effect {sfx} not found in {Settings.sfx_path}", file=stderr)
            return None
        media: Media = self.instance.media_new_path(path)
        el = AudioQueueElement(
            element_id=self.get_id(),
            resource=None,
            audio_source=LocalAudioSource(path),
            processing=AudioProcessingSettings(),
            message_setter=None,
            path=Future(),
            download_task=Future()
        )
        await el.download()
        await self.sfx_queue.append(el)

    async def hampter(self) -> None:
        if is_quiet_hours():
            return

        await self.add_sfx("hampter.wav")

    async def play_queue(self) -> None:
        async with self.queue.async_iter() as async_iterator:
            async for element in async_iterator:
                if element.skipped:
                    continue
                self.current = element
                path: Path | None = await element.path
                if path is None:
                    assert element.skipped
                    self.current = None
                    continue

                if is_quiet_hours():
                    await self.skip_all("@GoToBedFroshDitchDayIsTomorrow (quiet hours)")
                    continue

                while not element.skipped:
                    media: Media = self.instance.media_new_path(path)
                    self.main_player.set_media(media)

                    self.main_player.set_rate(element.vlc_settings.tempo_scale)

                    await element.set_message("Playing")

                    self.main_player.play()
                    element.active = True

                    while self.main_player.get_state() not in (VLCState.Ended, VLCState.Stopped) and \
                            not element.skipped and not is_quiet_hours():
                        # TODO: Wait for the duration or skip or quiet hours (whichever first)
                        await sleep(Settings.async_sleep_refresh_rate)

                    if is_quiet_hours():
                        await self.skip_all("@GoToBedFroshDitchDayIsTomorrow (quiet hours)")

                    if self.main_player.get_state() not in (VLCState.Ended, VLCState.Stopped):
                        self.main_player.stop()

                    if not element.processing.loop:
                        break

                # TODO: release() media if needed
                await element.finish()
                self.current = None
    
    async def play_sfx_queue(self) -> None:
        async with self.sfx_queue.async_iter() as async_iterator:
            async for element in async_iterator:
                path: Path | None = await element.path
                if path is None:
                    assert element.skipped
                    continue

                if is_quiet_hours():
                    continue

                media: Media = self.instance.media_new_path(path)
                self.sfx_player.set_media(media)
                self.sfx_player.set_rate(element.vlc_settings.tempo_scale)
                await element.set_message("Playing")
                self.sfx_player.play()
                element.active = True

                while self.sfx_player.get_state() not in (VLCState.Ended, VLCState.Stopped) and not is_quiet_hours():
                    await sleep(Settings.async_sleep_refresh_rate)

                if is_quiet_hours():
                    continue

                if self.sfx_player.get_state() not in (VLCState.Ended, VLCState.Stopped):
                    self.sfx_player.stop()

                await element.finish()

    async def skip(self, username: str) -> bool:
        if self.current is None:
            return False
        await self.current.skip(username)
        return True

    async def skip_all(self, username: str) -> bool:
        if self.state == AudioQueue.State.EMPTY:
            return False
        async with TaskGroup() as skip_tasks:
            for element in self.queue.reverse_destructive_iter:
                skip_tasks.create_task(element.skip(username))
            skip_tasks.create_task(self.current.skip(username))

    async def skip_specific(self, username: str, element_id: int) -> bool:
        if self.current is not None and self.current.element_id == element_id:
            return await self.skip(username)
        for element in self.queue:
            if element.element_id == element_id:
                await element.skip(username)
                return True
        return False

    async def pause(self) -> None:
        self.main_player.set_pause(True)

    async def resume(self) -> None:
        self.main_player.set_pause(False)

    async def set_digital_volume(self, volume: float) -> bool:
        absolute_volume: float = volume * Settings.hundred_percent_volume_value
        if 0 <= absolute_volume <= Settings.max_absolute_volume * 100:
            main_success = self.main_player.audio_set_volume(round(absolute_volume)) == 0
            sfx_success = self.sfx_player.audio_set_volume(round(absolute_volume)) == 0
            return main_success and sfx_success
        else:
            return False

    async def set_clamped_digital_volume(self, volume: float) -> bool:
        absolute_volume: float = volume * Settings.hundred_percent_volume_value
        absolute_volume = min(max(absolute_volume, 0), Settings.max_absolute_volume * 100)
        main_success = self.main_player.audio_set_volume(round(absolute_volume)) == 0
        sfx_success = self.sfx_player.audio_set_volume(round(absolute_volume)) == 0
        return main_success and sfx_success

    async def get_digital_volume(self) -> float:
        scaled_volume = self.sfx_player.audio_get_volume()
        return scaled_volume / Settings.hundred_percent_volume_value

    @property
    def state(self) -> State:
        match (self.main_player.get_state(), bool(self.queue), self.current is not None and not self.current.skipped):
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
                      f"\tself.main_player.get_state(): {player_state}\n"
                      f"\tself.sfx_player.get_state(): {self.sfx_player.get_state()}\n"
                      f"\tbool(self.queue): {queue_nonempty}\n"
                      f"\tbool(self.sfx_queue): {bool(self.sfx_queue)}\n"
                      f"\tself.current is not None: {current_set}\n"
                      f"\tself.queue: {self.queue}\n"
                      f"\tself.sfx_queue: {self.sfx_queue}\n"
                      f"\tself.current: {self.current}\n"
                      f"\tself.current.skipped: {self.current.skipped}")
                return AudioQueue.State.UNKNOWN_ERROR

    def get_id(self) -> int:
        out: int = self._next_id
        self._next_id += 1
        return out

    def __iter__(self):
        return iter(self.queue)
