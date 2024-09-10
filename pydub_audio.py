import audioop
from typing import Self

import numpy as np
import pydub
import simpleaudio


class AudioSegment:
    def __init__(self, wrapped: pydub.AudioSegment):
        self.wrapped = wrapped
        self.play_time = 0

    @classmethod
    def from_file(cls, path: str) -> Self:
        return cls(pydub.AudioSegment.from_file(path))

    @classmethod
    def from_np(cls, data: np.array, frame_rate: int, normalized: bool = True) -> Self:
        channels = data.shape[1] if (data.ndim == 2) else 1
        if normalized:  # normalized array - each item should be a float in [-1, 1)
            scaled_data = np.int16(data * 2 ** 15)
        else:
            scaled_data = np.int16(data)
        return AudioSegment(
            pydub.AudioSegment(scaled_data.tobytes(), frame_rate=frame_rate, sample_width=2, channels=channels))

    def to_np(self) -> np.ndarray:
        """
        Converts pydub audio segment into np.float32 of shape [duration_in_seconds*sample_rate, channels],
        where each value is in range [-1.0, 1.0].
        """
        return np.array(self.wrapped.get_array_of_samples(), dtype=np.float32).reshape((-1, self.wrapped.channels)) / (
                1 << (8 * self.wrapped.sample_width - 1))

    def to_file(self, path: str):
        self.wrapped.export(path, format="wav")

    def __getitem__(self, item) -> Self:
        return AudioSegment(self.wrapped.__getitem__(item))

    def play(self):
        sliced_audio = self.wrapped[self.play_time * 1000:]
        return simpleaudio.play_buffer(
            sliced_audio.raw_data,
            num_channels=sliced_audio.channels,
            bytes_per_sample=sliced_audio.sample_width,
            sample_rate=sliced_audio.frame_rate
        )

    def __add__(self, other: "AudioSegment") -> "AudioSegment":
        return AudioSegment(self.wrapped + other.wrapped)

    def __mul__(self, scale: float) -> "AudioSegment":
        return AudioSegment(
            self.wrapped._spawn(data=audioop.mul(self.wrapped.raw_data, self.wrapped.sample_width, scale)))

    @property
    def duration_seconds(self) -> float:
        return self.wrapped.duration_seconds

    @property
    def frame_rate(self) -> float:
        return self.wrapped.frame_rate
