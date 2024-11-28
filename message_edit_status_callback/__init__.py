from abc import ABC, abstractmethod

from telegram import User

from audio_processing import AudioProcessingSettings
from audio_sources import AudioSource
from tree_message import TreeMessage


def format_add_video_status(audio_source: AudioSource | None, user: User | None,
                            postprocessing: AudioProcessingSettings | None,
                            status: str | None) -> TreeMessage:
    return TreeMessage.Sequence([
        TreeMessage.Named("Queued song", TreeMessage.InlineCode(audio_source.title)) @ audio_source,
        TreeMessage.Named(
            audio_source.author_and_author_type[0].title(),
            TreeMessage.InlineCode(audio_source.author_and_author_type[1])
        ) @ audio_source,
        TreeMessage.Named("Queued by", TreeMessage.Text(user.name if user is not None else "")) @ user,
        TreeMessage.Named("Duration", TreeMessage.Text(str(audio_source.duration))) @ audio_source,
        TreeMessage.Named("Post-processing", TreeMessage.Text(str(postprocessing))) @ postprocessing,
        TreeMessage.Named("Status", TreeMessage.Text(status)) @ status
    ])


class MessageEditStatusCallback(ABC):
    @abstractmethod
    async def __call__(self, status: str, skip_index: int | None, url: str | None) -> None: ...
