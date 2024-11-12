from asyncio import to_thread
from pathlib import Path

import ffmpeg
from ffmpeg import Stream

from audio_processing import AudioProcessingSettings, VLCModificationSettings


def echo_args(in_gain: float, out_gain: float, delays: list[float], decays: list[float]) -> \
        tuple[float, float, str, str]:
    return in_gain, out_gain, "|".join(str(delay) for delay in delays), "|".join(str(decay) for decay in decays)


async def process_audio(source_path: Path, dest_path: Path,
                        settings: AudioProcessingSettings, vlc_settings: VLCModificationSettings) -> None:
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
