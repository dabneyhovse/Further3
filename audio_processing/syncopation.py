from collections.abc import Iterable, Sequence
from itertools import accumulate
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from pyrubberband.pyrb import timemap_stretch

from audio_processing import AudioProcessingSettings, VLCModificationSettings
from util import interpolate_index


def even_syncopation(beats: list[float], num_samples: int, pattern: Iterable[float] = (2, 1)) -> \
        list[tuple[float, float]]:
    pattern_integral: list[float] = list(accumulate(pattern))
    pattern_len: int = len(pattern_integral)
    pattern_sum = pattern_integral[-1]
    pattern_integral.insert(0, 0)

    beat_start = beats[0]
    beat_duration = beats[-1] - beats[0]

    syncopation: list[float] = [
        pattern_sum * (i // pattern_len) + pattern_integral[i % pattern_len]
        for i in range(len(beats))
    ]

    max_syncopation_space_value = max(syncopation)

    return (
            [(0, 0)] +
            [(round(beats[n]), round(syncopation[n] * beat_duration / max_syncopation_space_value + beat_start))
             for n in range(len(beats))] +
            [(num_samples, num_samples)]
    )


def flexible_syncopation(beats: list[float], num_samples: int, pattern: Sequence[float] = (2, 1)) -> \
        list[tuple[float, float]]:
    pattern_len: int = len(pattern)
    pattern_integral: list[float] = [0] + list(x / sum(pattern) for x in accumulate(pattern))

    time_map = [(0, 0)]
    for measure in range(len(beats) // pattern_len):
        measure_start: float = beats[measure * pattern_len]

        measure_duration: float = (
            beats[(measure + 1) * pattern_len] - beats[measure * pattern_len]
            if (measure + 1) * pattern_len < len(beats) else
            beats[measure * pattern_len] - beats[(measure - 1) * pattern_len]
        )

        for i in range(pattern_len):
            time_map.append((
                round(beats[measure * pattern_len + i]),
                round(measure_start + measure_duration * pattern_integral[i])
            ))
    time_map.append((num_samples, num_samples))
    return time_map


async def process_audio(source_path: Path, dest_path: Path,
                        settings: AudioProcessingSettings, _: VLCModificationSettings) -> None:
    y, sr = librosa.load(source_path, duration=20)

    quantization_scale = settings.syncopation.quantization_scale
    pattern = settings.syncopation.pattern

    tempo, frame_space_beats = librosa.beat.beat_track(y=y, sr=sr)
    sample_space_beats = librosa.frames_to_samples(frame_space_beats)

    rescaled_beats: list[float] = [
        float(interpolate_index(sample_space_beats, x))
        for x in np.linspace(0, len(sample_space_beats) - 1, len(sample_space_beats) * quantization_scale)
    ]

    syncopation_generator = flexible_syncopation if settings.syncopation.flexible else even_syncopation

    y_stretched = timemap_stretch(y, sr, syncopation_generator(rescaled_beats, len(y), pattern))

    sf.write(dest_path, y_stretched, sr)
