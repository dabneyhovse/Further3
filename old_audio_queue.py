import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum
from time import time
from typing import Any

from applescript import AppleScript, AEType
from pytubefix import Stream, YouTube
from simpleaudio import PlayObject
from telegram.ext import Application

from async_multiprocessing import await_process
from audio_processing import audio_transform
from bot_config import BotConfig
from resource_handler import ResourceHandler

from audio import AudioSegment


class QueueElement:
    def __init__(self, audio_queue: "AudioQueue", video: YouTube, resource: ResourceHandler.Resource,
                 message_status_setter: Callable[[str, int | None], Coroutine[Any, Any, None]],
                 index: int, postprocessing: "AudioQueue.PostProcessing"):
        self.audio_queue = audio_queue
        self.video: YouTube = video
        self.resource: ResourceHandler.Resource = resource
        self.playback: PlayObject | None = None
        self.play_time = 0
        self.start_time: float | None = None
        self.timer_handle: asyncio.TimerHandle | None = None
        self.message_status_setter: Callable[
            [str, int | None], Coroutine[Any, Any, None]] = message_status_setter
        self.index: int = index
        self.postprocessing: AudioQueue.PostProcessing = postprocessing
        self.audio: AudioSegment | None = None
        self.path: str | None = None
        self.downloaded_event: asyncio.Event = asyncio.Event()

    @staticmethod
    def download_audio(stream: Stream, resource_path: str) -> str:
        return stream.download(mp3=True, output_path=resource_path)

    async def download_and_process_audio(self) -> None:
        await self.audio_queue.application.create_task(self.message_status_setter("Downloading", self.index))

        stream: Stream = self.video.streams.get_audio_only()
        self.path = await await_process(self.download_audio, args=(stream, self.resource.path))

        await self.audio_queue.application.create_task(self.message_status_setter("Processing", self.index))

        # self.audio = await await_process(
        #     audio_transform,
        #     args=(
        #         AudioSegment.from_file(self.path),
        #     ),
        #     kwargs={
        #         "t_scale": self.postprocessing.time_stretch,
        #         "f_shift": self.postprocessing.pitch_shift,
        #         "percussive_harmonic_balance": self.postprocessing.percussive_harmonic_balance,
        #         "echo": self.postprocessing.echo
        #     }
        # )
        await self.audio_queue.application.create_task(self.message_status_setter("Queued", self.index))
        self.downloaded_event.set()

    def play(self, callback: Callable[[], Coroutine[Any, Any, None]], update_message: bool = True) -> bool:
        if self.playback is not None:
            return False
        sliced_audio: AudioSegment = self.audio[self.play_time * 1000:] * (self.audio_queue.digital_volume / 100)
        self.playback = sliced_audio.play()
        self.start_time = time()

        event_loop = asyncio.get_running_loop()
        self.timer_handle = event_loop.call_later(self.audio.duration_seconds - self.play_time, self.playback_waiter,
                                                  callback)
        if update_message:
            self.audio_queue.application.create_task(self.message_status_setter("Playing", self.index))
        return True

    async def pause(self, update_message: bool = True) -> bool:
        if self.playback is None:
            return False
        if not self.playback.is_playing():
            self.playback = None
            return False
        if self.timer_handle is None:
            return False
        self.timer_handle.cancel()
        stop_time = time()
        self.playback.stop()
        self.play_time += stop_time - self.start_time
        self.playback = None
        if update_message:
            self.audio_queue.application.create_task(self.message_status_setter("Paused", self.index))
        return True

    def stop(self, message: str) -> bool:
        out = not self.freed
        if self.timer_handle is not None:
            self.timer_handle.cancel()
            self.timer_handle = None
        if self.playback is not None:
            self.playback.stop()
            self.playback = None
        self.audio_queue.application.create_task(self.message_status_setter(message, None))
        if out:
            self.free()
        return out

    def free(self):
        self.playback = None
        self.resource.close()

    @property
    def active(self) -> bool:
        return self.playback is not None and self.playback.is_playing()

    @property
    def freed(self) -> bool:
        return not self.resource.is_open

    def playback_waiter(self, callback: Callable[[], Coroutine[Any, Any, None]]):
        if self.playback is not None and self.playback.is_playing():
            event_loop = asyncio.get_running_loop()
            event_loop.call_later(0.25, self.playback_waiter,
                                  callback)
        else:
            self.timer_handle = None
            self.stop("Played")
            self.audio_queue.application.create_task(callback())


# class QueueElement:
#     def __init__(self, audio_queue: "AudioQueue", video: YouTube, resource: ResourceHandler.Resource,
#                  message_status_setter: Callable[[str, int | None], Coroutine[Any, Any, None]],
#                  index: int, postprocessing: "AudioQueue.PostProcessing"):
#         self.audio_queue = audio_queue
#         self.video: YouTube = video
#         self.resource: ResourceHandler.Resource = resource
#         self.playback: PlayObject | None = None
#         self.play_time = 0
#         self.start_time: float | None = None
#         self.timer_handle: asyncio.TimerHandle | None = None
#         self.message_status_setter: Callable[
#             [str, int | None], Coroutine[Any, Any, None]] = message_status_setter
#         self.index: int = index
#         self.postprocessing: AudioQueue.PostProcessing = postprocessing
#         self.audio: AudioSegment | None = None
#         self.path: str | None = None
#         self.downloaded_event: asyncio.Event = asyncio.Event()
#
#     @staticmethod
#     def download_audio(stream: Stream, resource_path: str) -> str:
#         return stream.download(mp3=True, output_path=resource_path)
#
#     async def download_and_process_audio(self) -> None:
#         await self.audio_queue.application.create_task(self.message_status_setter("Downloading", self.index))
#
#         stream: Stream = self.video.streams.get_audio_only()
#         self.path = await await_process(self.download_audio, args=(stream, self.resource.path))
#
#         await self.audio_queue.application.create_task(self.message_status_setter("Processing", self.index))
#
#         self.audio = await await_process(
#             audio_transform,
#             args=(
#                 AudioSegment.from_file(self.path),
#             ),
#             kwargs={
#                 "t_scale": self.postprocessing.time_stretch,
#                 "f_shift": self.postprocessing.pitch_shift,
#                 "percussive_harmonic_balance": self.postprocessing.percussive_harmonic_balance,
#                 "echo": self.postprocessing.echo
#             }
#         )
#         await self.audio_queue.application.create_task(self.message_status_setter("Queued", self.index))
#         self.downloaded_event.set()
#
#     def play(self, callback: Callable[[], Coroutine[Any, Any, None]], update_message: bool = True) -> bool:
#         if self.playback is not None:
#             return False
#         sliced_audio: AudioSegment = self.audio[self.play_time * 1000:] * (self.audio_queue.digital_volume / 100)
#         self.playback = sliced_audio.play()
#         self.start_time = time()
#
#         event_loop = asyncio.get_running_loop()
#         self.timer_handle = event_loop.call_later(self.audio.duration_seconds - self.play_time, self.playback_waiter,
#                                                   callback)
#         if update_message:
#             self.audio_queue.application.create_task(self.message_status_setter("Playing", self.index))
#         return True
#
#     async def pause(self, update_message: bool = True) -> bool:
#         if self.playback is None:
#             return False
#         if not self.playback.is_playing():
#             self.playback = None
#             return False
#         if self.timer_handle is None:
#             return False
#         self.timer_handle.cancel()
#         stop_time = time()
#         self.playback.stop()
#         self.play_time += stop_time - self.start_time
#         self.playback = None
#         if update_message:
#             self.audio_queue.application.create_task(self.message_status_setter("Paused", self.index))
#         return True
#
#     def stop(self, message: str) -> bool:
#         out = not self.freed
#         if self.timer_handle is not None:
#             self.timer_handle.cancel()
#             self.timer_handle = None
#         if self.playback is not None:
#             self.playback.stop()
#             self.playback = None
#         self.audio_queue.application.create_task(self.message_status_setter(message, None))
#         if out:
#             self.free()
#         return out
#
#     def free(self):
#         self.playback = None
#         self.resource.close()
#
#     @property
#     def active(self) -> bool:
#         return self.playback is not None and self.playback.is_playing()
#
#     @property
#     def freed(self) -> bool:
#         return not self.resource.is_open
#
#     def playback_waiter(self, callback: Callable[[], Coroutine[Any, Any, None]]):
#         if self.playback is not None and self.playback.is_playing():
#             event_loop = asyncio.get_running_loop()
#             event_loop.call_later(0.25, self.playback_waiter,
#                                   callback)
#         else:
#             self.timer_handle = None
#             self.stop("Played")
#             self.audio_queue.application.create_task(callback())


class AudioQueue:
    class State(Enum):
        PAUSED = 0
        PLAYING = 1
        PREPROCESSING = 2

        def __str__(self):
            match self:
                case AudioQueue.State.PAUSED:
                    return "Paused"
                case AudioQueue.State.PLAYING:
                    return "Playing"
                case AudioQueue.State.PREPROCESSING:
                    return "Preprocessing"

    def __init__(self, bot_config: BotConfig, application: Application, volume: float):
        self.queue: list[QueueElement] = []
        self.index: int = 0
        self.bot_config: BotConfig = bot_config
        self.digital_volume: float = volume
        self.resource_handler: ResourceHandler = bot_config.resource_handler
        self.scheduled = None
        self.state = AudioQueue.State.PLAYING
        self.application = application
        self.set_sys_volume_script = AppleScript(path="apple_script/set_volume.scpt")
        self.get_sys_volume_script = AppleScript(path="apple_script/get_volume.scpt")

    @property
    def max_vol(self) -> float:
        return 150

    @property
    def current(self) -> QueueElement:
        return self.queue[self.index]

    @property
    def prev(self) -> QueueElement:
        return self.queue[self.index - 1]

    def add(
        self, stream: Stream, resource: ResourceHandler.Resource,
        message_status_setter: Callable[[str, int | None], Coroutine[Any, Any, None]],
        postprocessing: "AudioQueue.PostProcessing"
    ) -> tuple[int, QueueElement]:
        out = QueueElement(self, stream, resource, message_status_setter, len(self.queue), postprocessing)
        self.queue.append(out)
        download_and_process_awaitable: Coroutine[Any, Any, None] = out.download_and_process_audio()
        self.application.create_task(download_and_process_awaitable)
        self.start()
        return len(self.queue) - 1, out

    async def play_next(self, update_message: bool = True) -> None:
        while self.index < len(self.queue) and self.current.freed:
            self.index += 1
        if self.index < len(self.queue):
            if self.current.audio is None:
                self.state = AudioQueue.State.PREPROCESSING
                assert self.current.downloaded_event is not None
                await self.current.downloaded_event.wait()
            if self.state in [AudioQueue.State.PREPROCESSING, AudioQueue.State.PLAYING]:
                self.state = AudioQueue.State.PLAYING
                self.current.play(self.play_next, update_message)
                self.index += 1

    def start(self) -> None:
        if not (self.index and self.prev.active):
            self.play_next_if_active()

    async def unpause(self, update_message: bool = True) -> bool:
        if self.state == self.State.PAUSED:
            self.state = self.State.PLAYING
            await self.play_next(update_message)
            return True
        else:
            return False

    def pause(self, update_message: bool = True) -> bool:
        self.state = self.State.PAUSED
        out = self.index != 0 and self.prev.active and self.prev.pause(update_message=update_message)
        if out:
            self.index -= 1
        return out

    def play_next_if_active(self) -> None:
        if self.state == AudioQueue.State.PLAYING:
            self.application.create_task(self.play_next())

    async def skip(self, username: str) -> bool:
        if self.state == AudioQueue.State.PLAYING and self.index != 0:
            closed = self.index != 0 and self.prev.stop("Skipped by " + username)
            await self.play_next()
            return closed
        elif self.state == AudioQueue.State.PAUSED and self.index < len(self.queue):
            closed = self.current.stop("Skipped by " + username)
            self.index += 1
            return closed

    async def skip_specific(self, username: str, index: int) -> None:
        queue_element = self.queue[index]
        queue_element.stop("Skipped by " + username)
        if self.state == AudioQueue.State.PLAYING and self.prev == queue_element:
            await self.play_next()

    def skip_all(self, username: str) -> None:
        skip_start_index: int
        if self.state == AudioQueue.State.PAUSED and self.index < len(self.queue):
            skip_start_index = self.index

        elif self.state == AudioQueue.State.PLAYING and self.index != 0:
            skip_start_index = self.index - 1
        else:
            return
        for element in self.queue[skip_start_index:]:
            element.stop("Skipped by " + username)
        self.index = len(self.queue)

    def set_sys_volume(self, volume: float) -> float:
        actual_volume = min(max(volume, 0), 100)
        self.set_sys_volume_script.run(actual_volume)
        return actual_volume

    def get_sys_volume(self) -> float:
        volume_settings = self.get_sys_volume_script.run()
        return volume_settings[AEType(b"ouvl")]

    async def set_digital_volume(self, volume: float) -> float:
        actual_volume = min(max(volume, 0), self.max_vol)
        self.digital_volume = actual_volume
        if self.state == AudioQueue.State.PLAYING and 0 < self.index and self.prev.active:
            self.pause(update_message=False)
            await self.unpause(update_message=False)
        return actual_volume

    def get_digital_volume(self) -> float:
        return self.digital_volume
