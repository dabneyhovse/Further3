from __future__ import annotations

import logging
import re
from collections.abc import Collection, Callable
from functools import wraps, cached_property

from telegram import Message, User, Bot, Chat
from telegram.constants import ParseMode
from telegram.ext import MessageHandler, ApplicationBuilder, CommandHandler, BaseHandler, PicklePersistence, \
    CallbackQueryHandler
from telegram.ext.filters import BaseFilter

from decorator_tools import arg_decorator, method_decorator, map_first_arg_decorator, map_all_args_decorator, \
    map_all_to_first_arg_decorator
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
    def __init__(self, bot_token_path: str, persistence_file: str | None, resource_dir: str | None,
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
        if resource_dir:
            self.resource_handler: ResourceHandler = ResourceHandler(resource_dir)

        self.default_permissions: UserSelector = \
            default_permissions if default_permissions is not None else UserSelector.Always

        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )

        self.handlers: list[BaseHandler] = []
        self.post_init_handler = None

        self.run_data = dict()

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
                            permissions: UserSelector | None = None, user_selector_filter: UserSelector | None = None):
        if name is None:
            name = f.__name__

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

    def build(self):
        builder = ApplicationBuilder()
        (builder
         .token(self.bot_token)
         .post_init(self.post_init_handler)
         .arbitrary_callback_data(True))
        if self.persistence_file is not None:
            builder.persistence(PicklePersistence(filepath="store/persistence_store"))
        application = builder.build()

        application.add_handlers(self.handlers)

        application.bot_config = self

        application.run_polling()

    async def get_help(self, context: UpdateHandlerContext) -> FormattedText:
        return FormattedText(
            str(TreeMessage.Sequence([await message.display(context) for message in self.help_messages]))
        )


async def edit_message_text(message: Message, text: str | FormattedText, **kwargs):
    if isinstance(text, str):
        text: FormattedText = FormattedText(text)
    message_text: FormattedText = break_message_text(text)
    return await message.edit_text(text=str(message_text), **kwargs)


def break_message_text(message: FormattedText) -> FormattedText:
    max_len: int = 4096
    if len(message) > max_len:
        return message[:max_len - 3] + FormattedText("...")
    else:
        return message
