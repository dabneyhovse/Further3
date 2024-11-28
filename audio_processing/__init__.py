from dataclasses import dataclass
from pathlib import Path


@dataclass
class SyncopationSettings:
    flexible: bool = False
    quantization_scale: int = 1
    pattern: tuple[float, ...] = (2, 1)


@dataclass
class AudioProcessingSettings:
    pitch_shift: float = 0
    tempo_scale: float = 1
    echo: bool = False
    metal: bool = False
    reverb: bool = False
    loop: bool = False
    syncopation: SyncopationSettings | None = None

    @property
    def requires_ffmpeg_processing(self) -> bool:
        return (self.pitch_shift != 0 or self.tempo_scale != 1 or
                self.echo or self.metal or self.reverb)

    @property
    def requires_syncopation_processing(self) -> bool:
        return self.syncopation is not None

    def __bool__(self) -> bool:
        return (self.pitch_shift != 0 or self.tempo_scale != 1 or
                self.echo or self.metal or self.reverb or
                self.syncopation is not None or
                self.loop)

    def __str__(self) -> str:
        out: str = "In"
        if self.syncopation is not None:
            out += (f" \u2192 Syncopation("
                    f"flexible = {self.syncopation.flexible}, "
                    f"quantization scale = {self.syncopation.quantization_scale}, "
                    f"pattern = {self.syncopation.pattern})")
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


async def process_audio(source_path: Path, dest_path: Path,
                        settings: AudioProcessingSettings) -> VLCModificationSettings:
    import audio_processing.ffmpeg
    import audio_processing.syncopation

    vlc_settings = VLCModificationSettings()
    if settings.requires_syncopation_processing:
        await audio_processing.syncopation.process_audio(source_path, source_path, settings, vlc_settings)
    if settings.requires_ffmpeg_processing:
        await audio_processing.ffmpeg.process_audio(source_path, dest_path, settings, vlc_settings)
    return vlc_settings
