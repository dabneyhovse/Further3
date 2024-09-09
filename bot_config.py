import logging
import re
from collections.abc import Collection

from telegram import Message
from telegram.ext import MessageHandler, ApplicationBuilder, CommandHandler, BaseHandler, PicklePersistence, \
    CallbackQueryHandler
from telegram.ext.filters import BaseFilter

from decorator_tools import arg_decorator, method_decorator, map_first_arg_decorator, map_all_args_decorator
from formatted_text import FormattedText
from funcs import compose
from handler_context import UpdateHandlerContext, ApplicationHandlerContext
from resource_handler import ResourceHandler


class BotConfig:
    def __init__(self, bot_token_path: str, persistence_file: None | str, resource_dir: None | str) -> None:
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
        )
        logging.getLogger("httpx").setLevel(logging.WARNING)

        self.logger: logging.Logger = logging.getLogger(__name__)

        with open(bot_token_path, 'r') as bot_token_file:
            self.bot_token: str = bot_token_file.read()

        self.persistence_file: None | str = persistence_file

        self.resource_dir: None | str = resource_dir
        if resource_dir:
            self.resource_handler: ResourceHandler = ResourceHandler(resource_dir)

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

    @method_decorator(compose(arg_decorator, map_first_arg_decorator(map_all_args_decorator(UpdateHandlerContext))))
    def add_command_handler(self, f, name: str | Collection[str] | None = None, filters: BaseFilter | None = None,
                            has_args: bool | int | None = None, blocking: bool = False):
        if name is None:
            name = f.__name__
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
