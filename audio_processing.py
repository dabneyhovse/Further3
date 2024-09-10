from asyncio import create_subprocess_shell, subprocess
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from sys import stderr

import numpy as np
from librosa.effects import pitch_shift, time_stretch, hpss
from scipy.signal import convolve

from pydub_audio import AudioSegment
from settings import Settings
from util import escape_str


@dataclass
class AudioProcessingSettings:
    pitch_shift: float = 0
    tempo_scale: float = 1
    percussive_harmonic_balance: float = 0
    echo: tuple[float, float, float] = (0, 0, 0)

    def __bool__(self) -> bool:
        return self.pitch_shift != 0 or self.tempo_scale != 1 or self.percussive_harmonic_balance != 0

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
        out += " \u2192 Out"
        return out

    @property
    def pitch_scale(self) -> float:
        return 2 ** (self.pitch_shift / 12)


def audio_transform(audio: AudioSegment, settings: AudioProcessingSettings) -> AudioSegment:
    assert -1 <= settings.percussive_harmonic_balance <= 1

    data: np.array = audio.to_np().transpose()
    frame_rate: int = audio.wrapped.frame_rate
    # Adjust percussive-harmonic balance
    if settings.percussive_harmonic_balance:
        harmonic, percussive = hpss(data)
        data: np.array = (harmonic * min(1.0, 1.0 - settings.percussive_harmonic_balance) +
                          percussive * min(1.0, 1.0 + settings.percussive_harmonic_balance))
    # Shift frequency (by # of semitones)
    if settings.pitch_shift:
        data: np.array = pitch_shift(data, sr=frame_rate, n_steps=settings.pitch_shift)
    # Stretch / compress time
    if settings.tempo_scale != 1:
        data: np.array = time_stretch(data, rate=settings.tempo_scale)
    # Echo
    if all(settings.echo):
        drop_off: int = 512
        repetitions: int = round(settings.echo[0] * np.log(drop_off * settings.echo[2]) / settings.echo[1]) + 1
        sparse: dict[int, float] = {
            round(i * frame_rate * settings.echo[1]):
                np.exp(-i * settings.echo[1] / settings.echo[0]) * settings.echo[2] if i else 1
            for i in range(repetitions)
        }
        kernel: np.array = np.array([[sparse[i] if i in sparse else 0 for i in range(max(sparse.keys()))]])
        data: np.array = convolve(data, kernel)
    # Renormalize
    max_norm = abs(data).max()
    if max_norm > 1:
        data: np.array = data / max_norm
    return AudioSegment.from_np(data.transpose(), frame_rate)


async def ffmpeg_pitch_shift(scale: float, source_path: Path, dest_path: Path):
    clean_source: str = escape_str(source_path.absolute().as_posix(), "\"")
    clean_dest: str = escape_str(dest_path.absolute().as_posix(), "\"")
    proc = await create_subprocess_shell(
        f"ffmpeg -i \"{clean_source}\" -af asetrate=44100*{scale},aresample=44100,atempo=1/{scale} \"{clean_dest}\"",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout_result, stderr_result = (bytes_str.decode() for bytes_str in await proc.communicate())
    if Settings.debug and stderr_result:
        print(f"FFMPEG STDErr:\n{stderr_result}\n", file=stderr)
        print(f"FFMPEG STDOut:\n{stdout_result}\n", file=stderr)
