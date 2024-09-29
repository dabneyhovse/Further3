from asyncio import create_subprocess_shell, subprocess
from asyncio.subprocess import Process
from dataclasses import dataclass
from pathlib import Path
from sys import stderr

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


async def ffmpeg_pitch_shift(scale: float, source_path: Path, dest_path: Path):
    clean_source: str = escape_str(source_path.absolute().as_posix(), "\"")
    clean_dest: str = escape_str(dest_path.absolute().as_posix(), "\"")
    proc: Process = await create_subprocess_shell(
        f"ffmpeg -i \"{clean_source}\" -af asetrate=44100*{scale},aresample=44100,atempo=1/{scale} \"{clean_dest}\"",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout_result, stderr_result = (bytes_str.decode() for bytes_str in await proc.communicate())
    if Settings.debug and stderr_result:
        print(f"FFMPEG STDErr:\n{stderr_result}\n", file=stderr)
        print(f"FFMPEG STDOut:\n{stdout_result}\n", file=stderr)
