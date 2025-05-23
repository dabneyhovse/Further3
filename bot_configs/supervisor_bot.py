from __future__ import annotations

import os
import threading
import time
import traceback
from asyncio import create_task, sleep, subprocess
from asyncio.subprocess import create_subprocess_shell
from datetime import datetime
from multiprocessing import Process, Pipe
from multiprocessing.connection import Connection  # noqa
from sys import stderr

from telegram import Message, Bot, ChatFullInfo
from telegram.constants import ParseMode
from telegram.ext import filters

from bot_communication import ConnectionListener, DownwardsCommunication, UpwardsCommunication
from bot_config import BotConfig
from debugging import intercept
from handler_context import UpdateHandlerContext, ApplicationHandlerContext, HandlerContext
from settings import Settings
from tree_message import TreeMessage
from user_selector import UserSelector, MembershipStatusFlag, ChatTypeFlag
from util import count_iterable

BOT_TOKEN_FILE = Settings.supervisor_bot_token_path

bot_config = BotConfig(
    BOT_TOKEN_FILE,
    persistence_file="store/supervisor_persistence_store"
)


@bot_config.add_post_init_handler
async def post_init(context: ApplicationHandlerContext):
    context.run_data.defaults.further_process = None
    context.run_data.defaults.further_connection = None
    context.run_data.defaults.further_connection_listener = None
    context.run_data.defaults.flood_control_completion_time = 0
    context.run_data.defaults.flood_control_message = None

    await clear_pinned_messages()
    await try_to_start_further(context)

    context.run_data.run_start_time = datetime.now()


@bot_config.add_command_handler(
    ["help", "supervisor_help"],
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
    "complain",
    filters=~filters.UpdateType.EDITED_MESSAGE,
    permissions=UserSelector.And(
        UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id]),
        UserSelector.Not(
            UserSelector.MembershipStatusIsIn(
                MembershipStatusFlag.RESTRICTED | MembershipStatusFlag.NONMEMBER | MembershipStatusFlag.LEFT
            )
        )
    )
)
async def complain(context: UpdateHandlerContext):
    """Ping me and the comptrollers about an issue
    <i><b>Please, I'm begging you, please don't spam or abuse this.</b></i>
    This command will ring my phone loudly and persistently enough to wake the dead.
    If I don't respond, it is probably because I am busy, not because I haven't seen this.
    """

    query_message: Message = context.message
    query_message_id = query_message.message_id

    context.bot_data.defaults.last_complaint_time = 0
    last_complaint_time: float = context.bot_data.last_complaint_time
    if time.time() - last_complaint_time > 60 * 5:
        for comptroller_id in Settings.comptroller_ids:
            await context.bot.send_message(
                chat_id=comptroller_id,
                text=f"A darb is reporting an issue / requesting assistance via the Further bot: {query_message.link}"
            )
        await context.bot.send_message(
            chat_id=Settings.owner_id,
            text=f"bc33b6204cedf60452a886fa8715e7e6acacc06ebc28a6c8eda0b3c869001d0c\n"
                 f"Complaint sent to Further bot: {query_message.link}"
        )
        context.bot_data.last_complaint_time = time.time()
        await context.send_message(
            "The comptrollers and I have been notified, and I will respond shortly if I'm not busy. "
            "This command rings my phone loudly and persistently enough to wake the dead, so if I don't respond, "
            "it is probably because I am busy, not because I haven't seen this.\n"
            "<u><i><b>Please, I'm begging you, please don't spam or abuse this command.</b></i></u>",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
    else:
        await context.send_message(
            "<u><i><b>Please stop spamming this.\n</b></i></u>"
            "I have already been notified and will respond shortly if I'm not busy. "
            "This command rings my phone loudly and persistently enough to wake the dead, so if I don't respond, "
            "it is probably because I am busy, not because I haven't seen this.\n"
            "<u><i><b>Please, I'm begging you, please don't spam or abuse command.</b></i></u>",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )


@bot_config.add_command_handler(
    "reset_complain",
    filters=~filters.UpdateType.EDITED_MESSAGE,
    permissions=UserSelector.UserIDIsIn([Settings.owner_id])
)
async def reset_complain(context: UpdateHandlerContext):
    """Reset the complaint anti-spam timeout"""

    query_message: Message = context.message

    context.bot_data.last_complaint_time = time.time() + ((float(context.args[0]) if context.args else 0) - 5) * 60

    await query_message.delete()


def further_bot_target(connection: Connection):
    from bot_configs import further_bot
    try:
        further_bot.bot_config.build(connection_listener=ConnectionListener(connection))
    except Exception as e:
        connection.send(UpwardsCommunication.ExceptionShutdown(e))
    else:
        for _ in range(10):
            if count_iterable(threading.enumerate()) == 1:
                break
            else:
                time.sleep(0.5)
        else:
            connection.send(UpwardsCommunication.ThreadingFailedShutdown)
            return
        connection.send(UpwardsCommunication.CleanShutdown)


async def further_bot_communications_handler(communication: UpwardsCommunication):
    bot: Bot = bot_config.application.bot
    match communication:
        case UpwardsCommunication.CleanShutdown:
            await bot.send_message(
                chat_id=Settings.registered_primary_chat_id,
                text="Clean Further Bot shutdown detected"
            )
        case UpwardsCommunication.ExceptionShutdown(e):
            await bot.send_message(
                chat_id=Settings.registered_primary_chat_id,
                text="Managed exception Further Bot shutdown detected"
            )
            print(traceback.format_exception(e), file=stderr)
        case UpwardsCommunication.FloodControlIssues(delay):
            resume_time = time.time() + delay
            if bot_config.run_data.flood_control_message is None:
                bot_config.run_data.flood_control_message = await bot.send_message(
                    chat_id=Settings.registered_primary_chat_id,
                    text="Telegram flood control throttling detected - expect long delays"
                )
                await bot_config.run_data.flood_control_message.pin()
                create_task(clear_flood_control_message_callback())
            elif resume_time > bot_config.run_data.flood_control_completion_time:
                bot_config.run_data.flood_control_completion_time = resume_time
        case UpwardsCommunication.ThreadingFailedShutdown:
            await bot.send_message(
                chat_id=Settings.registered_primary_chat_id,
                text="Further Bot incomplete shutdown detected due to hanging threads. "
                     "Increased shutdown force recommended."
            )


async def clear_flood_control_message_callback():
    while bot_config.run_data.flood_control_message is not None and \
            time.time() >= bot_config.run_data.flood_control_completion_time:
        await sleep(time.time() - bot_config.run_data.flood_control_completion_time + Settings.async_sleep_refresh_rate)
    if bot_config.run_data.flood_control_message is not None:
        await bot_config.run_data.flood_control_message.delete()
        bot_config.run_data.flood_control_message = None


async def clear_pinned_messages():
    bot: Bot = bot_config.application.bot
    chat: ChatFullInfo = await bot.get_chat(Settings.registered_primary_chat_id)
    while chat.pinned_message is not None:
        await chat.pinned_message.unpin()
        await chat.pinned_message.delete()
        chat: ChatFullInfo = await bot.get_chat(Settings.registered_primary_chat_id)


async def try_to_start_further(context: HandlerContext):
    if context.run_data.further_process is not None and context.run_data.further_process.is_alive():
        return False
    else:
        if context.run_data.further_process is not None:
            context.run_data.further_process.close()
            context.run_data.further_connection.close()

        context.run_data.further_connection, further_side_connection = Pipe()
        context.run_data.further_process = Process(
            target=further_bot_target, args=(further_side_connection,),
            daemon=True,
            name="FurtherBot"
        )
        context.run_data.further_connection_listener = ConnectionListener(context.run_data.further_connection)
        create_task(context.run_data.further_connection_listener.listen(further_bot_communications_handler))  # noqa

    context.run_data.further_process.start()
    return True


@bot_config.add_command_handler(
    "start_further",
    filters=~filters.UpdateType.EDITED_MESSAGE,
    permissions=UserSelector.And(
        UserSelector.MembershipStatusIsIn(MembershipStatusFlag.OWNER | MembershipStatusFlag.ADMINISTRATOR),
        UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
    ),
    has_args=False,
    blocking=True
)
async def start_further(context: UpdateHandlerContext):
    """Start @DabneyFurtherBot bot"""

    query_message: Message = context.message
    query_message_id = query_message.message_id

    if not await try_to_start_further(context):
        await context.send_message(
            "Can't start Further Bot because it is already running",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
        return

    await query_message.set_reaction("👍")


@bot_config.add_command_handler(
    ["stop_further", "shutdown_further"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    permissions=UserSelector.And(
        UserSelector.MembershipStatusIsIn(MembershipStatusFlag.OWNER | MembershipStatusFlag.ADMINISTRATOR),
        UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
    ),
    blocking=True
)
async def stop_further(context: UpdateHandlerContext):
    """Attempt to gracefully stop @DabneyFurtherBot bot"""

    query_message: Message = context.message
    query_message_id = query_message.message_id

    if context.run_data.further_process is None or not context.run_data.further_process.is_alive():
        await context.send_message(
            "Can't stop Further Bot because it does not appear to be running",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
    else:
        force: int = int(context.args[0] if context.args else 1)
        match force:
            case 0 | 1:
                context.run_data.further_connection.send(DownwardsCommunication.ShutDown(force))
            case 2:
                context.run_data.further_process.terminate()
                context.run_data.further_connection.close()
        await query_message.set_reaction("👍")


@bot_config.add_command_handler(
    ["stop_process", "stop_service"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    permissions=UserSelector.And(
        UserSelector.MembershipStatusIsIn(MembershipStatusFlag.OWNER | MembershipStatusFlag.ADMINISTRATOR),
        UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
    ),
    blocking=True
)
async def stop_process(context: UpdateHandlerContext):
    """Attempt to stop the Further and Further Supervisor server process"""

    query_message: Message = context.message
    query_message_id = query_message.message_id

    allow_stop_further: bool = False
    force: bool = False

    for arg in context.args:
        for sub_arg in arg.lstrip("-") if arg.startswith("-") and not arg.startswith("--") else (arg,):
            match sub_arg:
                case "i":
                    allow_stop_further = True
                case "f":
                    force = True

    if (
            (not allow_stop_further)
            and (context.run_data.further_process is not None)
            and (context.run_data.further_process.is_alive())
    ):
        await context.send_message(
            "Can't stop Supervisor Bot because Further appears to be running. Rerun with -i if you want to stop the "
            "process anyways.",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
    elif allow_stop_further and force:
        await context.send_message(
            "<u><i>This is NOT the command you are looking for</i></u>. Do not attempt to stop Supervisor Bot with "
            "both -f and -i. This is a very bad idea. It will orphan the Further Bot process and break everything.",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
    else:
        await query_message.set_reaction("👍")
        if force:
            os._exit(1)  # noqa
        else:
            raise SystemExit()


async def get_version():
    commit_message_proc: subprocess.Process = await create_subprocess_shell(
        f"git log -1 --pretty=%B",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout_commit_message, _ = (bytes_str.decode() for bytes_str in await commit_message_proc.communicate())
    return stdout_commit_message.strip()


@bot_config.add_command_handler(
    ["update", "update_further", "upgrade"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    permissions=UserSelector.And(
        UserSelector.MembershipStatusIsIn(MembershipStatusFlag.OWNER | MembershipStatusFlag.ADMINISTRATOR),
        UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
    ),
    has_args=False,
    blocking=True
)
async def update_further(context: UpdateHandlerContext):
    """Attempt to update further
    Pulls from the git repository. Restart required afterward.
    """

    query_message: Message = context.message
    query_message_id = query_message.message_id

    update_message: Message = await context.send_message(
        "Updating...",
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id
    )
    proc: subprocess.Process = await create_subprocess_shell(
        f"git pull origin main; git checkout main",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout_result, stderr_result = (bytes_str.decode() for bytes_str in await proc.communicate())
    if stdout_result:
        print(f"Update stdout:\n{stdout_result}\n", file=stderr)
    if stderr_result:
        print(f"Update stderr:\n{stderr_result}\n", file=stderr)
    version: str = await get_version()
    await update_message.edit_text(
        f"Already up to date: {version}"
        if "Already up to date." in stdout_result else
        f"Updated to: {version}\n"
        f"Send /stop_further and then /stop_process to restart and apply updates."
    )
    await query_message.set_reaction("👍")


@bot_config.add_command_handler(
    ["revert", "downgrade"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    permissions=UserSelector.And(
        UserSelector.MembershipStatusIsIn(MembershipStatusFlag.OWNER | MembershipStatusFlag.ADMINISTRATOR),
        UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
    ),
    has_args=1,
    blocking=True
)
async def update_further(context: UpdateHandlerContext):
    """Attempt to downgrade further to n versions from the most recent available
    Pulls from the git repository. Restart required afterward.
    """

    query_message: Message = context.message
    query_message_id = query_message.message_id

    try:
        downgrade_amount: int = int(context.args[0])
    except ValueError:
        await context.send_message(
            "Arg must be a non-negative integer...",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
        return
    if downgrade_amount < 0:
        await context.send_message(
            "Arg must be a non-negative integer...",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )

    update_message: Message = await context.send_message(
        "Downgrading...",
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query_message_id
    )
    proc: subprocess.Process = await create_subprocess_shell(
        f"git pull origin main; git checkout main~{downgrade_amount}",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout_result, stderr_result = (bytes_str.decode() for bytes_str in await proc.communicate())
    if stdout_result:
        print(f"Update stdout:\n{stdout_result}\n", file=stderr)
    if stderr_result:
        print(f"Update stderr:\n{stderr_result}\n", file=stderr)
    version: str = await get_version()
    await update_message.edit_text(
        f"Already up to date: {version}"
        if "Already up to date." in stdout_result else
        f"Updated to: {version}\n"
        f"Send /stop_further and then /stop_process to restart and apply updates."
    )
    await query_message.set_reaction("👍")


@bot_config.add_command_handler(
    "intercept",
    filters=~filters.UpdateType.EDITED_MESSAGE,
    permissions=UserSelector.UserIDIsIn([Settings.owner_id]),
    has_args=False,
    blocking=True
)
async def intercept_further_execution(context: UpdateHandlerContext):
    """Attempt to intercept @DabneyFurtherBot bot execution and create an interactive console on the server
    Please don't run this command if you don't have access to the running process on the server.
    """

    query_message: Message = context.message
    query_message_id = query_message.message_id

    if context.run_data.further_process is None or not context.run_data.further_process.is_alive():
        await context.send_message(
            "Can't intercept Further Bot because it does not appear to be running",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
    else:
        pid: int = context.run_data.further_process.pid
        intercept(pid)
        await query_message.set_reaction("👍")


@bot_config.add_command_handler(
    "status",
    filters=~filters.UpdateType.EDITED_MESSAGE,
    has_args=False,
    blocking=True
)
async def get_further_status(context: UpdateHandlerContext):
    """Gets an overview of the @DabneyFurtherBot status
    """

    query_message: Message = context.message
    query_message_id = query_message.message_id

    if context.run_data.further_process is None or not context.run_data.further_process.is_alive():
        await context.send_message(
            "Further bot not running",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
    else:
        await context.send_message(
            str(
                TreeMessage.Sequence([
                    TreeMessage.Named("Version", TreeMessage.Text(await get_version())),
                    TreeMessage.Named(
                        "Further bot",
                        TreeMessage.Text(
                            "running"
                            if
                            context.run_data.further_process is not None and context.run_data.further_process.is_alive()
                            else "stopped"
                        )
                    ),
                    TreeMessage.Named(
                        "Startup time",
                        TreeMessage.Text(str(context.run_data.run_start_time))
                    ),
                ])
            ),
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )

# class Log:
#     def __init__(self, log_message: Message):
#         self.log_message: Message = log_message
#         self.lines: list[str] = []
#         self.position: int = 0
#         self.length: int = 8
#
#     async def refresh(self, context: UpdateHandlerContext):
#         query_message: Message = context.message
#         query_message_id = query_message.message_id
#
#         proc: Process = await create_subprocess_shell(
#             f"journalctl --user --no-tail -xu further",
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE
#         )
#         stdout_result, stderr_result = (bytes_str.decode() for bytes_str in await proc.communicate())
#         if stderr_result:
#             await context.send_message(
#                 f"<u>Error:</u>\n<pre>{html.escape(stderr_result)}</pre>\n",
#                 parse_mode=ParseMode.HTML,
#                 reply_to_message_id=query_message_id
#             )
#         self.lines = stdout_result.splitlines()
#
#     def get_log_text(self):
#         return "\n".join(self.lines[len(self.lines) - self.position - self.length: len(self.lines) - self.position])
#
#     async def update(self):
#         await self.log_message.edit_text(
#             html.escape(self.get_log_text()),
#             parse_mode=ParseMode.HTML,
#             link_preview_options=LinkPreviewOptions(is_disabled=True)
#         )
#
#
# @bot_config.add_command_handler(
#     ["start_log", "log"],
#     filters=~filters.UpdateType.EDITED_MESSAGE,
#     permissions=UserSelector.And(
#         UserSelector.UserIDIsIn(Settings.comptroller_ids),
#         UserSelector.ChatTypeIsIn(ChatTypeFlag.DM)
#     ),
#     has_args=False,
#     blocking=True
# )
# async def start_log(context: UpdateHandlerContext):
#     """Show the debug log"""
#     query_message: Message = context.message
#     query_message_id = query_message.message_id
#
#     context.user_data.log = Log(await context.send_message(
#         html.escape("<Log started>"),
#         parse_mode=ParseMode.HTML,
#         reply_to_message_id=query_message_id
#     ))
#
#
# @bot_config.add_command_handler(
#     ["log_len", "len"],
#     filters=~filters.UpdateType.EDITED_MESSAGE,
#     permissions=UserSelector.And(
#         UserSelector.UserIDIsIn(Settings.comptroller_ids),
#         UserSelector.ChatTypeIsIn(ChatTypeFlag.DM)
#     ),
#     has_args=1,
#     blocking=True
# )
# async def log_len(context: UpdateHandlerContext):
#     """Show the debug log"""
#     query_message: Message = context.message
#     query_message_id = query_message.message_id
#
#     context.user_data.defaults.log = None
#     if context.user_data.log is None:
#         await context.send_message(
#             html.escape("No log open"),
#             parse_mode=ParseMode.HTML,
#             reply_to_message_id=query_message_id
#         )
#         return
#
#     context.user_data.log.length = int(context.args[0])
