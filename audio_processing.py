from asyncio import create_subprocess_shell, subprocess, to_thread
from dataclasses import dataclass
from pathlib import Path
from sys import stderr

import ffmpeg
from ffmpeg import Stream
from ffmpeg.nodes import FilterableStream

from settings import Settings
from util import escape_str


@dataclass
class AudioProcessingSettings:
    pitch_shift: float = 0
    tempo_scale: float = 1
    percussive_harmonic_balance: float = 0
    echo: tuple[float, float, float] = (0, 0, 0)
    loop: bool = False

    def __bool__(self) -> bool:
        return (self.pitch_shift != 0 or self.tempo_scale != 1 or self.percussive_harmonic_balance != 0 or
                any(self.echo) or self.loop)

    def __str__(self) -> str:
        out: str = "In"
        if self.percussive_harmonic_balance != 0:
            percussion = min(1.0, 1.0 + self.percussive_harmonic_balance) / (
                    2 - abs(self.percussive_harmonic_balance)) * 100
            harmony = min(1.0, 1.0 - self.percussive_harmonic_balance) / (
                    2 - abs(self.percussive_harmonic_balance)) * 100
            out += f" \u2192 Percussion : Harmony = {percussion:.2f}% : {harmony:.2f}%"
        if self.pitch_shift != 0:
            out += f" \u2192 Pitch-Shift = {self.pitch_shift:.2f}"
        if self.tempo_scale != 1:
            out += f" \u2192 Speed = {self.tempo_scale:.2f}"
        if all(self.echo):
            out += f" \u2192 Echo (power, distance, cos) = {self.echo:.2f}"
        if self.loop:
            out += f" \u2192 Loop forever"
        out += " \u2192 Out"
        return out

    @property
    def pitch_scale(self) -> float:
        return 2 ** (self.pitch_shift / 12)


@dataclass
class VLCModificationSettings:
    tempo_scale: float = 1


async def process_audio(source_path: Path, dest_path: Path,
                        settings: AudioProcessingSettings) -> VLCModificationSettings:
    vlc_settings = VLCModificationSettings()

    stream: FilterableStream = ffmpeg.input(source_path)
    if settings.pitch_shift:
        frame_rate: int = 44100
        stream = stream.filter("asetrate", frame_rate * settings.pitch_scale)
        stream = stream.filter("aresample", frame_rate)
        stream = stream.filter("atempo", settings.tempo_scale / settings.pitch_scale)
    else:
        vlc_settings.tempo_scale = settings.tempo_scale
    stream = stream.output(str(dest_path))
    await to_thread(stream.run)

    return vlc_settings
