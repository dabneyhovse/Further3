from telegram import Message, User, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import BadRequest

from audio_processing import AudioProcessingSettings
from audio_sources import AudioSource
from message_edit_status_callback import MessageEditStatusCallback, format_add_video_status


class StandardMessageEditStatusCallback(MessageEditStatusCallback):
    message: Message
    audio_source: AudioSource
    user: User
    postprocessing: AudioProcessingSettings

    def __init__(self, message: Message, audio_source: AudioSource, user: User,
                 postprocessing: AudioProcessingSettings) -> None:
        self.message = message
        self.audio_source = audio_source
        self.user = user
        self.postprocessing = postprocessing

    async def __call__(self, status: str, skip_index: int | None, url: str | None) -> None:
        keyboard = [
            [InlineKeyboardButton("Skip", callback_data=("skip_button", skip_index))]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            # TODO: Protect from timeout - create safe MessageWrapper class
            await self.message.edit_text(
                str(format_add_video_status(self.audio_source, self.user, self.postprocessing, status)),
                parse_mode=ParseMode.HTML,
                reply_markup=(reply_markup if skip_index is not None else None),
                link_preview_options=LinkPreviewOptions(
                    is_disabled=(url is None),
                    url=url,
                    prefer_small_media=True,
                    show_above_text=False
                )
            )
        except BadRequest as e:
            if not e.message.startswith("Message is not modified"):
                raise
