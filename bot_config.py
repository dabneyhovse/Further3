from __future__ import annotations

import logging
import re
from asyncio import create_task, get_running_loop
from collections.abc import Collection, Callable
from functools import wraps, cached_property
from typing import Any

from telegram import Message, User, Bot, Chat
from telegram.constants import ParseMode
from telegram.ext import MessageHandler, ApplicationBuilder, CommandHandler, BaseHandler, PicklePersistence, \
    CallbackQueryHandler, Application
from telegram.ext.filters import BaseFilter

from attr_dict import AttrDictView
from bot_communication import DownwardsCommunication, ConnectionListener
from decorator_tools import arg_decorator, method_decorator, map_first_arg_decorator, map_all_args_decorator, \
    map_all_to_first_arg_decorator
from flood_control_protection import protect_from_telegram_flood_control, protect_from_telegram_timeout
from formatted_text import FormattedText
from funcs import compose
from handler_context import UpdateHandlerContext, ApplicationHandlerContext
from help import HelpMessage
from resource_handler import ResourceHandler
from tree_message import TreeMessage
from user_selector import UserSelector
from util import trim_docstring


def guard_permissions(f, *_args, permissions: UserSelector | None = None,
                      user_selector_filter: UserSelector | None = None, **_kwargs):
    @wraps(f)
    async def guarded(context: UpdateHandlerContext):
        query_message: Message = context.update.message
        query_message_id = query_message.message_id

        bot: Bot = context.bot
        user_id: int = context.update.effective_user.id
        chat: Chat = context.chat

        if user_selector_filter is not None and not await user_selector_filter.matches(bot, user_id, chat):
            return
        if permissions is not None and not await permissions.matches(bot, user_id, chat):
            async def user_name_lookup(u_id: int) -> str:
                return f"&lt;User {u_id}&gt;"

            async def chat_name_lookup(c_id: int) -> str:
                chat_name: str = (await context.bot.get_chat(c_id)).effective_name
                return f"\"{chat_name}\""

            permission_description: str = await permissions.describe(user_name_lookup, chat_name_lookup)
            await context.send_message(
                f"This command can only be used {permission_description}.",
                parse_mode=ParseMode.HTML,
                reply_to_message_id=query_message_id
            )
            # TODO: Silly "opinion" reaction or response
            return
        await f(context)

    return guarded


class BotConfig:
    def __init__(self, bot_token_path: str, persistence_file: str | None, resource_dir: str | None = None,
                 default_permissions: UserSelector | None = None) -> None:
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
        )
        logging.getLogger("httpx").setLevel(logging.WARNING)

        self.logger: logging.Logger = logging.getLogger(__name__)

        self.help_messages: list[HelpMessage] = []

        with open(bot_token_path, 'r') as bot_token_file:
            self.bot_token: str = bot_token_file.read()

        self.persistence_file: None | str = persistence_file

        self.resource_dir: None | str = resource_dir
        if resource_dir is not None:
            self.resource_handler: ResourceHandler = ResourceHandler(resource_dir)

        self.default_permissions: UserSelector = \
            default_permissions if default_permissions is not None else UserSelector.Always

        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )

        self.application: Application | None = None
        self.connection_listener: ConnectionListener | None = None

        self.handlers: list[BaseHandler] = []
        self.post_init_handler = None

        self._run_data = dict()

    @property
    def run_data(self) -> AttrDictView[str, Any]:
        return AttrDictView(self._run_data)

    @method_decorator(map_first_arg_decorator(map_all_args_decorator(ApplicationHandlerContext)))
    def add_post_init_handler(self, f):
        self.post_init_handler = f

    @method_decorator(
        compose(
            arg_decorator,
            compose(
                map_all_to_first_arg_decorator(guard_permissions),
                map_first_arg_decorator(
                    map_all_args_decorator(UpdateHandlerContext)
                )
            )
        )
    )
    def add_command_handler(self, f, name: str | Collection[str] | None = None, filters: BaseFilter | None = None,
                            has_args: bool | int | None = None, blocking: bool = False,
                            permissions: UserSelector | None = None, user_selector_filter: UserSelector | None = None,
                            hide_from_help: bool = False):
        if name is None:
            name = f.__name__

        if not hide_from_help:
            self.help_messages.append(HelpMessage(
                name=name,
                has_args=has_args,
                permissions=permissions,
                user_selector_filter=user_selector_filter,
                docstring=trim_docstring(f.__doc__)
            ))

        self.handlers.append(CommandHandler(name, f, filters=filters, has_args=has_args, block=blocking))

    @method_decorator(compose(arg_decorator, map_first_arg_decorator(map_all_args_decorator(UpdateHandlerContext))))
    def add_message_handler(self, f, message_filter: BaseFilter | None, blocking: bool = True):
        self.handlers.append(MessageHandler(message_filter, f, block=blocking))

    @method_decorator(compose(arg_decorator, map_first_arg_decorator(map_all_args_decorator(UpdateHandlerContext))))
    def add_callback_query_handler(self, f, pattern: re.Pattern | str | type(...) | None = None):
        if pattern is None:
            pattern = "^" + f.__name__ + "$"
        if pattern is Ellipsis:
            pattern = None
        self.handlers.append(CallbackQueryHandler(f, pattern=pattern))

    def build(self, connection_listener: ConnectionListener | None = None) -> None:
        self.connection_listener = connection_listener

        builder = ApplicationBuilder()
        (builder
         .token(self.bot_token)
         .post_init(self.post_init_handler)
         .arbitrary_callback_data(True))
        if self.persistence_file is not None:
            builder.persistence(PicklePersistence(filepath="store/further_persistence_store"))
        self.application = builder.build()

        self.application.add_handlers(self.handlers)

        self.application.bot_config = self

        self.application.run_polling()

    async def get_help(self, context: UpdateHandlerContext) -> FormattedText:
        return FormattedText(
            str(TreeMessage.Sequence([await message.display(context) for message in self.help_messages]))
        )

    async def start_connection_listener(self):
        if self.connection_listener is not None:
            create_task(self.connection_listener.listen(self.process_communication))  # noqa
        else:
            raise ValueError("No ConnectionListener configured")

    async def process_communication(self, communication: DownwardsCommunication):
        match communication:
            case DownwardsCommunication.ShutDown(0):
                await self.application.stop()
                await self.application.updater.stop()
                await self.application.shutdown()
                try:
                    get_running_loop().stop()
                except RuntimeError:
                    pass
            case DownwardsCommunication.ShutDown(1):
                raise SystemExit()
