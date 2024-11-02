from asyncio import to_thread
from dataclasses import dataclass
from pathlib import Path

import ffmpeg
from ffmpeg.nodes import Stream


@dataclass
class AudioProcessingSettings:
    pitch_shift: float = 0
    tempo_scale: float = 1
    percussive_harmonic_balance: float = 0
    echo: bool = False
    metal: bool = False
    reverb: bool = False
    loop: bool = False

    def __bool__(self) -> bool:
        return (self.pitch_shift != 0 or self.tempo_scale != 1 or self.percussive_harmonic_balance != 0 or
                self.echo or self.metal or self.reverb or self.loop)

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
        if self.echo:
            out += f" \u2192 Echo = {self.echo:.2f}"
        if self.metal:
            out += f" \u2192 Metal = {self.metal:.2f}"
        if self.reverb:
            out += f" \u2192 Reverb = {self.reverb:.2f}"
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


def echo_args(in_gain: float, out_gain: float, delays: list[float], decays: list[float]) -> \
        tuple[float, float, str, str]:
    return in_gain, out_gain, "|".join(str(delay) for delay in delays), "|".join(str(decay) for decay in decays)


async def process_audio(source_path: Path, dest_path: Path,
                        settings: AudioProcessingSettings) -> VLCModificationSettings:
    vlc_settings = VLCModificationSettings()

    stream: Stream = ffmpeg.input(source_path)
    if settings.tempo_scale < 0:
        stream = stream.filter("areverse")
    if settings.pitch_shift:
        frame_rate: int = 44100
        stream = stream.filter("asetrate", frame_rate * settings.pitch_scale)
        stream = stream.filter("aresample", frame_rate)
        stream = stream.filter("atempo", abs(settings.tempo_scale) / settings.pitch_scale)
    else:
        vlc_settings.tempo_scale = abs(settings.tempo_scale)
    if settings.echo:
        stream = stream.filter("aecho", *echo_args(
            0.6,
            0.3,
            [100 * i for i in range(1, 4)],
            [0.5 ** i for i in range(1, 4)]
        ))
    if settings.metal:
        stream = stream.filter("aecho", *echo_args(0.8, 0.88, [20, 40], [0.8, 0.4]))
    if settings.reverb:
        stream = stream.filter("aecho", *echo_args(
            0.8,
            0.88,
            [8 * i for i in range(1, 32)],
            [0.95 ** i for i in range(1, 32)]
        ))
    stream = stream.output(str(dest_path))
    await to_thread(stream.run)

    return vlc_settings
