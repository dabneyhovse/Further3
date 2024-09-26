import numpy as np
from librosa.effects import hpss, pitch_shift, time_stretch
from scipy.signal import convolve

from audio_processing import AudioProcessingSettings
from pydub_audio import AudioSegment


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
