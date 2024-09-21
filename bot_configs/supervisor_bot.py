from __future__ import annotations

import traceback
from asyncio import create_task, get_running_loop, sleep
from multiprocessing import Process, Pipe
from multiprocessing.connection import Connection  # noqa
from sys import stderr
from time import time

from telegram import Message, Bot
from telegram.constants import ParseMode
from telegram.ext import filters

from bot_communication import ConnectionListener, DownwardsCommunication, UpwardsCommunication
from bot_config import BotConfig
from debugging import intercept
from handler_context import UpdateHandlerContext, ApplicationHandlerContext
from settings import Settings
from user_selector import UserSelector, MembershipStatusFlag, ChatTypeFlag

BOT_TOKEN_FILE = "sensitive/supervisor_bot_token.txt"

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

    query_message_id: int = context.update.message.message_id

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
    ),
    has_args=False
)
async def complain(context: UpdateHandlerContext):
    """Ping me and the comptrollers about an issue
    <i><b>Please, I'm begging you, please don't spam or abuse this.</b></i>
    This command will ring my phone loudly and persistently enough to wake the dead.
    If I don't respond, it is probably because I am busy, not because I haven't seen this.
    """

    query_message: Message = context.update.message
    query_message_id = query_message.message_id

    context.bot_data.defaults.last_complaint_time = 0
    last_complaint_time: float = context.bot_data.last_complaint_time
    if time() - last_complaint_time > 60 * 5:
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
        context.bot_data.last_complaint_time = time()
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

    query_message: Message = context.update.message

    context.bot_data.last_complaint_time = time() + ((float(context.args[0]) if context.args else 0) - 5) * 60

    await query_message.delete()


def further_bot_target(connection: Connection):
    from bot_configs import further_bot
    try:
        further_bot.bot_config.build(connection_listener=ConnectionListener(connection))
    except Exception as e:
        connection.send(UpwardsCommunication.ExceptionShutdown(e))
    else:
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
            resume_time = time() + delay
            if bot_config.run_data.flood_control_message is None:
                bot_config.run_data.flood_control_message = await bot.send_message(
                    chat_id=Settings.registered_primary_chat_id,
                    text="Telegram flood control throttling detected - expected long delays"
                )
                get_running_loop().call_later(delay, clear_flood_control_message_callback)
            elif resume_time > bot_config.run_data.flood_control_completion_time:
                bot_config.run_data.flood_control_completion_time = resume_time


async def clear_flood_control_message_callback():
    while bot_config.run_data.flood_control_message is not None and \
            time() >= bot_config.run_data.flood_control_completion_time:
        await sleep(time() - bot_config.run_data.flood_control_completion_time + Settings.async_sleep_refresh_rate)
    if bot_config.run_data.flood_control_message is not None:
        await bot_config.run_data.flood_control_message.delete()
        bot_config.run_data.flood_control_message = None


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

    query_message: Message = context.update.message
    query_message_id = query_message.message_id

    if context.run_data.further_process is not None and context.run_data.further_process.is_alive():
        await context.send_message(
            "Can't start Further Bot because it is already running",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
        return
    else:
        if context.run_data.further_process is not None:
            context.run_data.further_process.close()
            context.run_data.further_connection.close()

        context.run_data.further_connection, further_side_connection = Pipe()
        context.run_data.further_process = Process(
            target=further_bot_target, args=(further_side_connection,),
            daemon=True
        )
        context.run_data.further_connection_listener = ConnectionListener(context.run_data.further_connection)
        create_task(context.run_data.further_connection_listener.listen(further_bot_communications_handler))  # noqa

    context.run_data.further_process.start()

    await query_message.set_reaction("👍")


@bot_config.add_command_handler(
    ["stop_further", "shutdown_further"],
    filters=~filters.UpdateType.EDITED_MESSAGE,
    permissions=UserSelector.And(
        UserSelector.MembershipStatusIsIn(MembershipStatusFlag.OWNER | MembershipStatusFlag.ADMINISTRATOR),
        UserSelector.ChatIDIsIn([Settings.registered_primary_chat_id])
    ),
    has_args=1,
    blocking=True
)
async def stop_further(context: UpdateHandlerContext):
    """Attempt to gracefully stop @DabneyFurtherBot bot"""

    query_message: Message = context.update.message
    query_message_id = query_message.message_id

    if context.run_data.further_process is None or not context.run_data.further_process.is_alive():
        await context.send_message(
            "Can't stop Further Bot because it does not appear to be running",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=query_message_id
        )
    else:
        force: int = int(context.args[0])
        match force:
            case 0 | 1:
                context.run_data.further_connection.send(DownwardsCommunication.ShutDown(force))
            case 2:
                context.run_data.further_process.terminate()
                context.run_data.further_connection.close()
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

    query_message: Message = context.update.message
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
