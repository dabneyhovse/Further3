from abc import abstractmethod, ABC
from typing import Optional

from telegram import Update, Message, Bot, User, Chat, ChatMember
from telegram.ext import Application, ContextTypes, CallbackContext

from attr_dict import AttrDictView
from formatted_text import FormattedText


class HandlerContext(ABC):
    @property
    @abstractmethod
    def application(self) -> Application: ...

    @property
    def bot_data(self):
        return AttrDictView(self.application.bot_data)

    @property
    def chat_data(self):
        return AttrDictView(self.application.bot_data)
        # return AttrDictView(self.application.chat_data["data"])

    @property
    def user_data(self):
        return AttrDictView(self.application.user_data["data"])

    @property
    def run_data(self):
        return AttrDictView(self.application.bot_config.run_data)


class ApplicationHandlerContext(HandlerContext):
    def __init__(self, application: Application) -> None:
        self._application = application

    @property
    def application(self) -> Application:
        return self._application


class UpdateHandlerContext(HandlerContext):
    def __init__(self, update: Update, context: CallbackContext) -> None:
        self.update: Update = update
        self.context: CallbackContext = context

    async def send_message(self, text: str | FormattedText, chat_id: Optional[int] = None, **kwargs) -> Message:
        if isinstance(text, str):
            text: FormattedText = FormattedText(text)
        if chat_id is None:
            chat_id = self.update.effective_chat.id
        from bot_config import break_message_text
        message_text: FormattedText = break_message_text(text)
        return await self.context.bot.send_message(chat_id=chat_id, text=str(message_text), **kwargs)

    @property
    def application(self) -> Application:
        return self.context.application

    @property
    def args(self) -> list[str]:
        return self.context.args

    @property
    def bot(self) -> Bot:
        return self.application.bot

    @property
    def user(self) -> User:
        return self.update.effective_user

    @property
    def chat(self) -> Chat:
        return self.update.effective_chat

    @property
    async def chat_member(self) -> ChatMember:
        return await self.bot.get_chat_member(self.chat.id, self.user.id)
