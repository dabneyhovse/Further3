from __future__ import annotations

from asyncio import Future
from datetime import timedelta, datetime
from math import log
from typing import cast, Tuple

import pytubefix
from pytubefix import Search, YouTube, Playlist
from telegram import User, Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatMember
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import filters

import debugging
import opinions
from audio_processing import AudioProcessingSettings
from audio_queue import AudioQueue, AudioQueueElement
from bot_config import BotConfig
from flood_control_protection import protect_from_telegram_flood_control, protect_from_telegram_timeout
from handler_context import UpdateHandlerContext, ApplicationHandlerContext
from settings import Settings
from tree_message import TreeMessage
from user_selector import UserSelector, ChatTypeFlag, MembershipStatusFlag
from util import count_iterable

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


def format_add_video_status(video: YouTube, user: User | None, postprocessing: AudioProcessingSettings | None,
                            status: str | None) -> TreeMessage:
    return TreeMessage.Sequence([
        TreeMessage.Named("Queued song", TreeMessage.InlineCode(video.title)),
        TreeMessage.Named("Author", TreeMessage.InlineCode(video.author)),
        TreeMessage.Named("Queued by", TreeMessage.Text(user.name)) if user is not None else TreeMessage.Skip,
        TreeMessage.Named(
            "Duration",
            TreeMessage.Text(str(timedelta(seconds=video.length)))
            if not postprocessing.loop else
            TreeMessage.Text("∞")
        ),
        TreeMessage.Named("Post-processing", TreeMessage.Text(str(postprocessing)))
        if postprocessing else TreeMessage.Skip,
        TreeMessage.Named("Status", TreeMessage.Text(status)) if status is not None else TreeMessage.Skip
    ])


def format_add_playlist_status(playlist: Playlist, user: User, postprocessing: AudioProcessingSettings,
                               status: str) -> TreeMessage:
    return TreeMessage.Sequence([
        TreeMessage.Named("Queued playlist", TreeMessage.InlineCode(playlist.title)),
        TreeMessage.Named("Owner", TreeMessage.InlineCode(playlist.owner)),
        TreeMessage.Named("Queued by", TreeMessage.Text(user.name)),
        TreeMessage.Named("Songs", TreeMessage.Text(str(count_iterable(playlist.videos)))),
        TreeMessage.Named("Post-processing", TreeMessage.Text(str(postprocessing)))
        if postprocessing else TreeMessage.Skip,
        TreeMessage.Named("Status", TreeMessage.Text(status))
    ])


def find_video(query_text: str) -> YouTube | None:
    try:
        video: YouTube = YouTube(query_text)
        return video
    except pytubefix.exceptions.RegexMatchError:
        search: Search = Search(query_text)
        videos: list[YouTube] = search.videos
        return videos[0] if videos else None


def find_playlist(query_text: str) -> Playlist | None:
    try:
        playlist: Playlist = Playlist(query_text)
        return playlist
    except pytubefix.exceptions.RegexMatchError:
        search: Search = Search(query_text)
        playlists: list[Playlist] = search.playlist
        return playlists[0] if playlists else None


def format_get_queue(queue: AudioQueue) -> TreeMessage:
    songs: list[AudioQueueElement] = [element for element in queue if not element.freed]
    return TreeMessage.Sequence([
        TreeMessage.Sequence([
            TreeMessage.Named("State", TreeMessage.Text(str(queue.state))),
            TreeMessage.Named("Songs", TreeMessage.Text(str(len(songs)))),
            TreeMessage.Named(
                "Remaining play time",
                TreeMessage.Text(str(timedelta(
                    seconds=round(
                        sum(element.video.length for element in songs) +
                        (
                            queue.current.video.length - queue.player.get_time() / 1000
                            if queue.state in [AudioQueue.State.PLAYING, AudioQueue.State.PAUSED] else
                            0
                        )
                    )
                )))
                if not any(element.processing.loop for element in songs) else
                TreeMessage.Text("∞")
            )
        ]),
        TreeMessage.Named(
            "Current",
            format_add_video_status(queue.current.video, None, queue.current.processing, None)
            if queue.current is not None and not queue.current.skipped else
            TreeMessage.Text("&lt;None&gt;")
        ),
        TreeMessage.Named(
            "Queue",
            TreeMessage.Sequence([
                TreeMessage.Sequence([
                    format_add_video_status(element.video, None, element.processing, None)
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
    query_message_id: int = context.update.message.message_id

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
    query_message: Message = context.update.message
    query_message_id = query_message.message_id
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


async def parse_query(context: UpdateHandlerContext, query_message_id: int):
    postprocessing: AudioProcessingSettings = AudioProcessingSettings()

    query_text: str = ""
    arg_text: str = ""
    for arg in context.args:
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
                      "speed adjust" | "speed up", scale_str]:
                    scale: float | None = await parse_float(scale_str, context, query_message_id)
                    if scale is None:
                        return
                    if not 1 / 4 <= scale <= 4:
                        await context.send_message(
                            f"Time scale should be in the range [{1 / 4}, 4]",
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=query_message_id)
                        return
                    postprocessing.tempo_scale = scale
                case ["stretch" | "elongate" | "time stretch" | "slow" | "time slow" | "slow time" | "stretch time" |
                      "tempo slow" | "tempo" | "slow tempo" | "slow down", inv_scale_str]:
                    inv_scale: float | None = await parse_float(inv_scale_str, context, query_message_id)
                    if inv_scale is None:
                        return
                    if not 1 / 4 <= inv_scale <= 4:
                        await context.send_message(
                            f"Time stretch should be in the range [{1 / 4}, 4]",
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=query_message_id)
                        return
                    postprocessing.tempo_scale = 1 / inv_scale
                case ["increase percussion" | "percussion" | "decrease melody" | "percussion balance", balance_str]:
                    balance: float | None = await parse_float(balance_str, context, query_message_id)
                    if balance is None:
                        return
                    if not -1 <= balance <= 1:
                        await context.send_message(
                            f"Percussive / harmonic balance should be in the range [-1, 1]",
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=query_message_id)
                        return
                    postprocessing.percussive_harmonic_balance = balance
                case ["increase melody" | "melody" | "decrease percussion" | "melody balance", balance_str]:
                    balance: float | None = await parse_float(balance_str, context, query_message_id)
                    if balance is None:
                        return
                    if not -1 <= balance <= 1:
                        await context.send_message(
                            f"Percussive / harmonic balance should be in the range [-1, 1]",
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=query_message_id)
                        return
                    postprocessing.percussive_harmonic_balance = -balance
                case ["nightcore" | "night-core" | "sped up" | "sped-up"]:
                    postprocessing.pitch_shift = 12 * log(1.35) / log(2)
                    postprocessing.tempo_scale = 1.35
                case ["loop" | "repeat"] | ["loop" "forever"]:
                    postprocessing.loop = True
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

    return query_text, postprocessing


async def queue_video(context: UpdateHandlerContext, video: YouTube, user: User, query_message_id: int,
                      postprocessing: AudioProcessingSettings, part_of_playlist: bool = False):
    message: Message = await context.send_message(
        str(format_add_video_status(video, user if not part_of_playlist else None, postprocessing, "Downloading")),
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id
    )
    download_resource = bot_config.resource_handler.claim()

    @protect_from_telegram_timeout
    @protect_from_telegram_flood_control(bot_config.connection_listener)
    async def message_edit_status(status: str, skip_index: int | None) -> None:
        keyboard = [
            [InlineKeyboardButton("Skip", callback_data=("skip_button", skip_index))]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await message.edit_text(
                str(format_add_video_status(video, user if not part_of_playlist else None, postprocessing, status)),
                parse_mode=ParseMode.HTML,
                reply_markup=(reply_markup if skip_index is not None else None)
            )
        except BadRequest as e:
            if not e.message.startswith("Message is not modified"):
                raise

    await message_edit_status("Adding to queue", None)
    queue_element: AudioQueueElement = AudioQueueElement(
        element_id=context.run_data.queue.get_id(),
        resource=download_resource,
        video=video,
        processing=postprocessing,
        message_setter=message_edit_status,
        path=Future(),
        download_task=Future()
    )
    await context.run_data.queue.add(queue_element)


@protect_from_telegram_flood_control(bot_config.connection_listener)
@protect_from_telegram_timeout
async def queue_playlist(context: UpdateHandlerContext, playlist: Playlist, user: User, query_message_id: int,
                         postprocessing: AudioProcessingSettings):
    message: Message = await context.send_message(
        str(format_add_playlist_status(playlist, user, postprocessing, "Loading")),
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id
    )
    for video in playlist.videos:
        await queue_video(context, video, user, message.message_id, postprocessing, part_of_playlist=True)
    await message.edit_text(
        str(format_add_playlist_status(playlist, user, postprocessing, "Done loading")),
        parse_mode=ParseMode.HTML
    )


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
    Pass the post-processing instructions individually, surrounded by braces, before the link / search term.
    For example: <code>/q {speed: 1.5} {pitch shift: 2} microchip song</code>
    """
    user: User = context.update.effective_user
    query_message_id: int = context.update.message.message_id

    query_text, postprocessing = await parse_query(context, query_message_id)

    video: YouTube | None = find_video(query_text)
    if video is not None:
        await opinions.be_opinionated(video.title, context)
        await queue_video(context, video, user, query_message_id, postprocessing)
    else:
        playlist: Playlist | None = find_playlist(query_text)
        if playlist is not None:
            await opinions.be_opinionated(playlist.title, context)
            await queue_playlist(context, playlist, user, query_message_id, postprocessing)
        else:
            await context.send_message(
                "Couldn't find video or playlist",
                parse_mode=ParseMode.HTML,
                reply_to_message_id=query_message_id)
            return


@bot_config.add_command_handler(
    ["hampter"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    # has_args=False, TODO
    permissions=UserSelector.And(
        UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id]),
        UserSelector.MembershipStatusIsIn(MembershipStatusFlag.OWNER | MembershipStatusFlag.ADMINISTRATOR)
    )
)
async def hampter(context: UpdateHandlerContext):
    """Hampter"""
    query_message: Message = context.update.message

    await context.run_data.queue.hampter(int(context.args[0]) if context.args else 0)
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
    query_message: Message = context.update.message
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
    query_message: Message = context.update.message
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
    query_message: Message = context.update.message
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
    query_message: Message = context.update.message
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

    query_message: Message = context.update.message
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

    query_message: Message = context.update.message
    query_message_id = query_message.message_id
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
#     query_message: Message = context.update.message
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
#     query_message: Message = context.update.message
#     query_message_id = query_message.message_id
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
    query_message: Message = context.update.message
    query_message_id = query_message.message_id
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
        reply_to_message_id=query_message_id)


@bot_config.add_command_handler(
    "wee",
    filters=~filters.UpdateType.EDITED_MESSAGE
)
async def wee(context: UpdateHandlerContext):
    """HOO"""
    query_message: Message = context.update.message
    query_message_id = query_message.message_id
    await context.send_message(
        f"/hoo",
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id)


@bot_config.add_command_handler(
    "hoo",
    filters=~filters.UpdateType.EDITED_MESSAGE
)
async def hoo(context: UpdateHandlerContext):
    """WEE"""
    query_message: Message = context.update.message
    query_message_id = query_message.message_id
    await context.send_message(
        f"/wee",
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id)


@bot_config.add_command_handler(
    "send_registration_information",
    filters=~filters.UpdateType.EDITED_MESSAGE,
    user_selector_filter=UserSelector.ChatIDIsIn(
        [Settings.registered_primary_chat_id]
    ),
    hide_from_help=True
)
async def send_registration_information(context: UpdateHandlerContext):
    query_message: Message = context.update.message
    query_message_id = query_message.message_id
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
    hide_from_help=True
)
async def amogus(context: UpdateHandlerContext):
    """Instantly bans @AlanTheTable for 6.9 minutes"""
    query_message: Message = context.update.message

    await context.chat.ban_member(Settings.amogus_ban_id, until_date=(datetime.now() + timedelta(minutes=6.9)))
    await query_message.set_reaction("👍")
