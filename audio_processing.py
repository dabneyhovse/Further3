import numpy as np
from librosa.effects import pitch_shift, time_stretch, preemphasis, deemphasis, hpss
from scipy.signal import convolve

from audio import AudioSegment


def audio_transform(audio: AudioSegment, t_scale: float = 1, f_shift: float = 0,
                    percussive_harmonic_balance: float = 0,
                    echo: tuple[float, float, float] = (0, 0, 0)) -> AudioSegment:
    assert -1 <= percussive_harmonic_balance <= 1

    data: np.array = audio.to_np().transpose()
    frame_rate: int = audio.wrapped.frame_rate
    # Adjust percussive-harmonic balance
    if percussive_harmonic_balance:
        harmonic, percussive = hpss(data)
        data: np.array = (harmonic * min(1.0, 1.0 - percussive_harmonic_balance) +
                          percussive * min(1.0, 1.0 + percussive_harmonic_balance))
    # Shift frequency (by # of semitones)
    if f_shift:
        data: np.array = pitch_shift(data, sr=frame_rate, n_steps=f_shift)
    # Stretch / compress time
    if t_scale != 1:
        data: np.array = time_stretch(data, rate=t_scale)
    # Echo
    if all(echo):
        drop_off: int = 512
        repetitions: int = round(echo[0] * np.log(drop_off * echo[2]) / echo[1]) + 1
        sparse: dict[int, float] = {
            round(i * frame_rate * echo[1]): np.exp(-i * echo[1] / echo[0]) * echo[2] if i else 1
            for i in range(repetitions)
        }
        kernel: np.array = np.array([[sparse[i] if i in sparse else 0 for i in range(max(sparse.keys()))]])
        data: np.array = convolve(data, kernel)
    # Renormalize
    max_norm = abs(data).max()
    if max_norm > 1:
        data: np.array = data / max_norm
    return AudioSegment.from_np(data.transpose(), frame_rate)
