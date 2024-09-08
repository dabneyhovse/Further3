from asyncio import Queue
from dataclasses import dataclass

from vlc import Instance, MediaPlayer
import asyncio

from audio_processing import AudioProcessingSettings
from resource_handler import ResourceHandler
from settings import Settings


@dataclass
class AudioQueueElement:
    resource: ResourceHandler.Resource
    processing: AudioProcessingSettings


class AudioQueue:
    queue: Queue[AudioQueueElement]
    instance: Instance
    player: MediaPlayer

    def __init__(self):
        self.queue = asyncio.Queue()
        self.instance = Instance()
        self.player = self.instance.media_player_new()

    @property
    def is_playing(self) -> bool:
        return self.player.is_playing()

    async def add_to_queue(self, element: AudioQueueElement):
        await self.queue.put(element)
        if not self.is_playing:
            await self.play_next_in_queue()

    async def play_next_in_queue(self) -> None:
        if not self.queue.empty():
            next_audio: AudioQueueElement = await self.queue.get()
            next_file: str = next_audio.resource.path
            media = self.instance.media_new_path(next_file)
            self.player.set_media(media)
            self.player.play()

            while self.is_playing:
                await asyncio.sleep(Settings.async_sleep_refresh_rate)

            await self.play_next_in_queue()

    async def skip_all(self) -> bool:
        if not self.is_playing and self.queue.empty():
            return False
        self.player.stop()
        while not self.queue.empty():
            self.queue.get_nowait()

    async def pause(self) -> None:
        self.player.set_pause(True)

    async def resume(self) -> None:
        self.player.set_pause(False)

    async def skip(self) -> bool:
        resume_playback = self.is_playing
        if not resume_playback and self.queue.empty():
            return False
        self.player.stop()
        self.queue.get_nowait()
        if resume_playback:
            await self.play_next_in_queue()
        return True

    async def set_volume(self, volume: float) -> bool:
        pass

# Example usage:
# audio_queue = AudioQueue()
# asyncio.run(audio_queue.add_to_queue("path_to_audio_file.mp3"))
