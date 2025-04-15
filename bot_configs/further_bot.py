from __future__ import annotations

from asyncio import Future
from datetime import timedelta, datetime
from math import log
from typing import cast

from telegram import User, Message, CallbackQuery, ChatPermissions, Audio
from telegram.constants import ParseMode
from telegram.ext import filters

import debugging
import opinions
from audio_processing import AudioProcessingSettings
from audio_queue import AudioQueue, AudioQueueElement
from audio_sources import AudioSource, yt_dlp_audio_source
from audio_sources.telegram_file_audio_source import TelegramAudioSource
from audio_sources.yt_dlp_audio_source import YtDLPAudioSource
from bot_config import BotConfig
from duration import Duration
from handler_context import UpdateHandlerContext, ApplicationHandlerContext
from message_edit_status_callback import format_add_video_status
from message_edit_status_callback.standard import StandardMessageEditStatusCallback
from settings import Settings
from tree_message import TreeMessage
from user_selector import UserSelector, ChatTypeFlag, MembershipStatusFlag

BOT_TOKEN_FILE = Settings.further_bot_token_path

bot_config = BotConfig(
    BOT_TOKEN_FILE,
    persistence_file="store/further_persistence_store",
    resource_dir="downloads"
)


@bot_config.add_post_init_handler
async def post_init(context: ApplicationHandlerContext):
    context.bot_data.defaults.digital_volume = 30.0
    context.run_data.queue = AudioQueue()
    await context.run_data.queue.set_clamped_digital_volume(context.bot_data.digital_volume)

    debugging.listen()
    await bot_config.start_connection_listener()


# def format_add_playlist_status(playlist: Playlist, user: User, postprocessing: AudioProcessingSettings,
#                                status: str) -> TreeMessage:
#     return TreeMessage.Sequence([
#         TreeMessage.Named("Queued playlist", TreeMessage.InlineCode(playlist.title)),
#         TreeMessage.Named("Owner", TreeMessage.InlineCode(playlist.owner)),
#         TreeMessage.Named("Queued by", TreeMessage.Text(user.name)),
#         TreeMessage.Named("Songs", TreeMessage.Text(str(count_iterable(playlist.videos)))),
#         TreeMessage.Named("Post-processing", TreeMessage.Text(str(postprocessing)))
#         if postprocessing else TreeMessage.Skip,
#         TreeMessage.Named("Status", TreeMessage.Text(status))
#     ])


def format_get_queue(queue: AudioQueue) -> TreeMessage:
    songs: list[AudioQueueElement] = [element for element in queue if not element.freed]
    return TreeMessage.Sequence([
        TreeMessage.Sequence([
            TreeMessage.Named("State", TreeMessage.Text(str(queue.state))),
            TreeMessage.Named("Songs", TreeMessage.Text(str(len(songs)))),
            TreeMessage.Named(
                "Remaining play time",
                TreeMessage.Text(str(
                    sum((element.duration for element in songs), start=Duration.zero()) + (
                        (
                                queue.current.duration -
                                Duration.from_timedelta(
                                    timedelta(milliseconds=queue.main_player.get_time())
                                ) / queue.current.processing.tempo_scale
                        )
                        if queue.state in [AudioQueue.State.PLAYING, AudioQueue.State.PAUSED] else
                        Duration.zero()

                    )
                )
                )
            )
        ]),
        TreeMessage.Named(
            "Current",
            format_add_video_status(queue.current.audio_source, None, queue.current.processing, None)
            if queue.current is not None and not queue.current.skipped else
            TreeMessage.Text("&lt;None&gt;")
        ),
        TreeMessage.Named(
            "Queue",
            TreeMessage.Sequence([
                TreeMessage.Sequence([
                    format_add_video_status(element.audio_source, None, element.processing, None)
                ])
                for element in queue if not element.skipped
            ]) if queue.queue else TreeMessage.Text("&lt;Empty&gt;")
        )
    ])


@bot_config.add_command_handler(
    ["help", "further_help"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=False,
    permissions=UserSelector.Or(
        UserSelector.ChatTypeIsIn(ChatTypeFlag.DM),
        UserSelector.MembershipStatusIsIn(MembershipStatusFlag.ADMINISTRATOR | MembershipStatusFlag.OWNER)
    )
)
async def get_help(context: UpdateHandlerContext):
    """Show this help message
    (Only available in DMs to reduce clutter)"""
    query_message_id: int = context.message.message_id

    await context.send_message(
        str(await bot_config.get_help(context)),
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id)


@bot_config.add_command_handler(
    ["q", "queue", "queued"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=False
)
async def get_queue(context: UpdateHandlerContext):
    """Show the queue"""
    query_message: Message = context.message
    query_message_id: int = query_message.message_id
    await context.send_message(
        str(format_get_queue(context.run_data.queue)),
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id)


async def parse_float(s: str, context: UpdateHandlerContext, query_message_id: int) -> float | None:
    try:
        out: float = float(s)
    except ValueError:
        await context.send_message(
            f"Couldn't parse float: \"{s}\"",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id)
        return None
    return out


async def parse_query(context: UpdateHandlerContext, query_message_id: int) -> \
        tuple[AudioSource, AudioProcessingSettings] | None:
    postprocessing: AudioProcessingSettings = AudioProcessingSettings()

    query_text: str = ""
    arg_text: str = ""
    for arg in context.args if context.args is not None else (
            context.message.text or context.message.caption or "").split():
        if arg[-1] == '}':
            arg_text += arg[:-1].lstrip("{")
            match [sub_arg.strip().lower() for sub_arg in arg_text.split(":")]:
                case ["pitch" | "freq" | "frequency" | "pitch shift" | "pitch adjust" | "freq shift" | "freq adjust" |
                      "frequency shift" | "frequency adjust", shift_str]:
                    shift: float | None = await parse_float(shift_str, context, query_message_id)
                    if shift is None:
                        return
                    if not -24 <= shift <= 24:
                        await context.send_message(
                            f"Max freq shift is 2 octaves",
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=query_message_id)
                        return
                    postprocessing.pitch_shift = shift
                case ["contract" | "quicken" | "time contract" | "speed" | "time scale" | "scale time" |
                      "contract time" | "speed scale" | "tempo scale" | "tempo" | "scale tempo" | "tempo adjust" |
                      "speed adjust" | "speed up" | "playback speed" | "playback rate" | "playback tempo", scale_str]:
                    scale: float | None = await parse_float(scale_str, context, query_message_id)
                    if scale is None:
                        return
                    if not 1 / 4 <= abs(scale) <= 4:
                        await context.send_message(
                            f"Time scale (absolute value) should be in the range [{1 / 4}, 4]",
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=query_message_id)
                        return
                    postprocessing.tempo_scale = scale
                case ["stretch" | "elongate" | "time stretch" | "slow" | "time slow" | "slow time" | "stretch time" |
                      "tempo slow" | "tempo" | "slow tempo" | "slow down", inv_scale_str]:
                    inv_scale: float | None = await parse_float(inv_scale_str, context, query_message_id)
                    if inv_scale is None:
                        return
                    if not 1 / 4 <= abs(inv_scale) <= 4:
                        await context.send_message(
                            f"Time stretch (absolute value) should be in the range [{1 / 4}, 4]",
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=query_message_id)
                        return
                    postprocessing.tempo_scale = 1 / inv_scale
                case ["nightcore" | "night-core" | "sped up" | "sped-up"]:
                    postprocessing.pitch_shift = 12 * log(1.35) / log(2)
                    postprocessing.tempo_scale = 1.35
                case ["loop" | "repeat"] | ["loop", "forever"]:
                    postprocessing.loop = True
                case ["echo"]:
                    postprocessing.echo = True
                case ["metal"]:
                    postprocessing.metal = True
                case ["reverb"]:
                    postprocessing.reverb = True
                case _:
                    await context.send_message(
                        f"Unknown postprocessing command: {arg_text}",
                        parse_mode=ParseMode.HTML,
                        reply_to_message_id=query_message_id)
                    return

            arg_text = ""
        elif arg_text or arg[0] == '{':
            if arg_text:
                arg_text += " "
            arg_text += arg.lstrip("{")
        else:
            if query_text:
                query_text += " "
            query_text += arg

    query_message: Message = context.message
    query_audio: Audio | None = query_message.audio

    audio_source: AudioSource

    if query_audio is None:
        audio_source = YtDLPAudioSource(yt_dlp_audio_source.Query.from_query_text(query_text))
    else:
        audio_source = TelegramAudioSource(query_audio)

    return audio_source, postprocessing


async def queue_video(context: UpdateHandlerContext, audio_source: AudioSource, user: User, query_message_id: int,
                      postprocessing: AudioProcessingSettings):
    # TODO: Make audio_source a future so that the bot replies immediately/
    message: Message = await context.send_message(str(
        format_add_video_status(audio_source, user, postprocessing, "Searching")),
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id
    )
    download_resource = bot_config.resource_handler.claim()

    # TODO: Option for if it's part of a playlist
    message_edit_status_callback = StandardMessageEditStatusCallback(message, audio_source, user, postprocessing)

    queue_element: AudioQueueElement = AudioQueueElement(
        element_id=context.run_data.queue.get_id(),
        resource=download_resource,
        audio_source=audio_source,
        processing=postprocessing,
        message_setter=message_edit_status_callback,
        path=Future(),
        download_task=Future()
    )
    await context.run_data.queue.add(queue_element)


# @protect_from_telegram_flood_control(bot_config.connection_listener)
# @protect_from_telegram_timeout
# async def queue_playlist(context: UpdateHandlerContext, playlist: Playlist, user: User, query_message_id: int,
#                          postprocessing: AudioProcessingSettings):
#     message: Message = await context.send_message(
#         str(format_add_playlist_status(playlist, user, postprocessing, "Loading")),
#         parse_mode=ParseMode.HTML,
#         reply_to_message_id=query_message_id
#     )
#     for video in playlist.videos:
#         await queue_video(context, video, user, message.message_id, postprocessing, part_of_playlist=True)
#     await message.edit_text(
#         str(format_add_playlist_status(playlist, user, postprocessing, "Done loading")),
#         parse_mode=ParseMode.HTML
#     )


async def enqueue_impl(context: UpdateHandlerContext):
    user: User = context.update.effective_user
    query_message_id: int = context.message.message_id

    parsed_query: tuple[AudioSource, AudioProcessingSettings] | None = await parse_query(context, query_message_id)

    if parsed_query is None:
        return

    audio_source, postprocessing = parsed_query

    if audio_source is not None:
        await opinions.be_opinionated(audio_source.title, context)
        await queue_video(context, audio_source, user, query_message_id, postprocessing)
    else:
        await context.send_message(
            "Couldn't find video or playlist",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id)
        return


@bot_config.add_command_handler(
    ["q", "queue", "add", "enqueue"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=True,
    permissions=UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
)
async def enqueue(context: UpdateHandlerContext):
    """Add a song to the queue
    At present, you can pass this command a:
    - YouTube video link
    - YouTube Music song link
    - YouTube or YouTube Music playlist link (wip — may break because of Telegram api issues)
    - Search term for a YouTube video
    Optionally, you can also pass some audio pre-processing instructions:
    - "pitch shift" / "pitch adjust" / "freq shift" / etc.: shift the play-back pitch by a number of semitones
    - "speed" / "time contract" / "tempo" / etc.: scale the play-back tempo
    - "nightcore" ≈ (pitch shift: 5.12, speed: 1.35)
    - "echo"
    - "metal"
    - "reverb"
    Pass the post-processing instructions individually, surrounded by braces, before the link / search term.
    For example: <code>/q {speed: 1.5} {pitch shift: 2} microchip song</code>
    """
    await enqueue_impl(context)


@bot_config.add_command_handler(
    ["hampter"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=False,
    permissions=UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
)
async def hampter(context: UpdateHandlerContext):
    """Hampter"""
    query_message: Message = context.message

    await context.run_data.queue.hampter()
    await query_message.set_reaction("👍")


@bot_config.add_callback_query_handler(...)
async def callback_query_handler(context: UpdateHandlerContext):
    query: CallbackQuery = context.update.callback_query
    await query.answer()
    button_name, skippable_element_index = cast(tuple[str, int], query.data)
    if button_name != "skip_button":
        return
    user: User = context.update.effective_user
    await context.run_data.queue.skip_specific(user.name, skippable_element_index)


@bot_config.add_command_handler(
    ["pause", "stop"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=False,
    permissions=UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
)
async def pause(context: UpdateHandlerContext):
    """Pause playback"""
    query_message: Message = context.message
    await context.run_data.queue.pause()
    await query_message.set_reaction("👍")


@bot_config.add_command_handler(
    ["play", "resume", "unpause"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=False,
    permissions=UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
)
async def resume(context: UpdateHandlerContext):
    """Resume (unpause) playback"""
    query_message: Message = context.message
    await context.run_data.queue.resume()
    await query_message.set_reaction("👍")


@bot_config.add_command_handler(
    "skip",
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=False,
    permissions=UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
)
async def skip(context: UpdateHandlerContext):
    """Skip the currently playing (or paused) song"""
    query_message: Message = context.message
    user: User = context.update.effective_user
    result: bool = await context.run_data.queue.skip(user.name)
    await query_message.set_reaction("👍" if result else "🤷")


@bot_config.add_command_handler(
    ["skip_all", "clear", "skipall"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=False,
    permissions=UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
)
async def skip_all(context: UpdateHandlerContext):
    """Skip all songs currently playing or in the queue"""
    query_message: Message = context.message
    user: User = context.update.effective_user
    await context.run_data.queue.skip_all(user.name)
    await query_message.set_reaction("👍")


@bot_config.add_command_handler(
    ["volume", "vol", "v"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=1,
    permissions=UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
)
async def set_volume(context: UpdateHandlerContext):
    """Set the (digital) output volume (in percent)
    The volume should normally remain between 0 (silent) and 100 (the maximum "reasonable" volume).
    In some cases, depending on the current configuration, the volume can be set above 100%.
    Please do not set the volume above 100% without <i>very</i> good reason.
    """

    query_message: Message = context.message
    try:
        new_volume: float = float(context.args[0])
    except ValueError:
        await query_message.set_reaction(opinions.lol_emoji())
        return
    if new_volume < 0.0:
        await query_message.set_reaction(opinions.lol_emoji())
    else:
        result = await context.run_data.queue.set_digital_volume(new_volume)
        if result:
            await query_message.set_reaction("👍")
            context.bot_data.digital_volume = new_volume
        else:
            await query_message.set_reaction("🙉")


@bot_config.add_command_handler(
    ["volume", "vol", "v"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=False
)
async def get_volume(context: UpdateHandlerContext):
    """Get the current (digital) output volume (in percent)"""

    query_message: Message = context.message
    query_message_id: int = query_message.message_id
    await context.send_message(
        f"Current volume: {round(await context.run_data.queue.get_digital_volume())}",
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id)


# @bot_config.add_command_handler(
#     ["sys_volume", "sys_vol", "sys_v"],
#     filters=~filters.UpdateType.EDITED_MESSAGE,
#     has_args=1,
#     permissions=UserSelector.ChatIDIsIn(Settings.registered_chat_ids)
# )
# async def set_sys_volume(context: UpdateHandlerContext):
#     query_message: Message = context.message
#     try:
#         new_volume: float = float(context.args[0])
#     except ValueError:
#         await query_message.set_reaction(opinions.lol_emoji())
#         return
#     context.run_data.queue.set_sys_volume(new_volume)
#     await query_message.set_reaction("👍")
#
#
# @bot_config.add_command_handler(
#     ["sys_volume", "sys_vol", "sys_v"],
#     filters=~filters.UpdateType.EDITED_MESSAGE,
#     has_args=False
# )
# async def sys_volume(context: UpdateHandlerContext):
#     query_message: Message = context.message
#     query_message_id: int = query_message.message_id
#     await context.send_message(
#         f"Current volume: {context.run_data.queue.get_sys_volume()}",
#         parse_mode=ParseMode.HTML,
#         reply_to_message_id=query_message_id)

@bot_config.add_command_handler(
    ["quiet_hours", "get_quiet_hours", "qh"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=False
)
async def get_quiet_hours(context: UpdateHandlerContext):
    """Get the currently configured quiet hours times"""
    query_message: Message = context.message
    query_message_id: int = query_message.message_id
    await context.send_message(
        str(
            TreeMessage.Sequence([
                TreeMessage.Named("Start", TreeMessage.Sequence([
                    TreeMessage.Named("Week-nights", TreeMessage.Text(
                        str(timedelta(hours=Settings.normal_quiet_hours_start_time))
                    )),
                    TreeMessage.Named("Weekend-nights", TreeMessage.Text(
                        str(timedelta(hours=Settings.weekend_quiet_hours_start_time))
                    ))
                ])),
                TreeMessage.Named("End", TreeMessage.Text(
                    str(timedelta(hours=Settings.quiet_hours_end_time))
                ))
            ])
        ),
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id
    )


@bot_config.add_command_handler(
    "wee",
    filters=~filters.UpdateType.EDITED_MESSAGE
)
async def wee(context: UpdateHandlerContext):
    """HOO"""
    query_message: Message = context.message
    query_message_id: int = query_message.message_id
    await context.send_message(
        f"/hoo",
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id
    )


@bot_config.add_command_handler(
    "hoo",
    filters=~filters.UpdateType.EDITED_MESSAGE
)
async def hoo(context: UpdateHandlerContext):
    """WEE"""
    query_message: Message = context.message
    query_message_id: int = query_message.message_id
    await context.send_message(
        f"/wee",
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id
    )


@bot_config.add_command_handler(
    "send_registration_information",
    filters=~filters.UpdateType.EDITED_MESSAGE,
    user_selector_filter=UserSelector.ChatIDIsIn(
        [Settings.registered_primary_chat_id]
    ),
    hide_from_help=True
)
async def send_registration_information(context: UpdateHandlerContext):
    query_message: Message = context.message
    query_message_id: int = query_message.message_id
    user: User = context.update.effective_user
    print(
        f"Registration request received:\n"
        f"\tMessage ID: {query_message_id}\n"
        f"\tUsername: {user.username}\n"
        f"\tUser ID: {user.id}\n"
        f"\tChat name: {context.chat.effective_name}\n"
        f"\tChat ID: {context.chat.id}\n\n"
    )
    await query_message.delete()


@bot_config.add_command_handler(
    "amogus",
    filters=~filters.UpdateType.EDITED_MESSAGE,
    user_selector_filter=UserSelector.ChatIDIsIn(
        [Settings.registered_primary_chat_id]
    ),
    has_args=False
)
async def amogus(context: UpdateHandlerContext):
    """Instantly mutes @AlanTheTable for 6.9 minutes"""
    query_message: Message = context.message
    query_message_id: int = query_message.message_id

    result: bool = await context.chat.restrict_member(
        Settings.amogus_ban_id,
        ChatPermissions.no_permissions(),
        until_date=(datetime.now() + timedelta(minutes=6.9))
    )
    if result:
        await context.send_message(
            f"@AlanTheTable has been banned for 6.9 minutes",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
    else:
        await query_message.delete()


@bot_config.add_command_handler(
    "sus",
    filters=~filters.UpdateType.EDITED_MESSAGE,
    user_selector_filter=UserSelector.ChatIDIsIn(
        [Settings.registered_primary_chat_id]
    ),
    has_args=False
)
async def sus(context: UpdateHandlerContext):
    """End @AlanTheTable's ban/mute :("""
    query_message: Message = context.message

    result: bool = await context.chat.unban_member(Settings.amogus_ban_id, only_if_banned=True)
    result |= await context.chat.restrict_member(
        Settings.amogus_ban_id,
        ChatPermissions.all_permissions()
    )
    if result:
        await query_message.set_reaction("👍")
    else:
        await query_message.delete()


@bot_config.add_message_handler(
    message_filter=filters.AUDIO
)
async def queue_audio_message(context: UpdateHandlerContext):
    """Enqueue telegram audio"""
    await enqueue_impl(context)
