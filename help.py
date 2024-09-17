from collections.abc import Collection
from dataclasses import dataclass

from handler_context import UpdateHandlerContext
from tree_message import TreeMessage
from user_selector import UserSelector


@dataclass
class HelpMessage:
    name: str | Collection[str]
    has_args: bool | int | None
    permissions: UserSelector | None
    user_selector_filter: UserSelector | None
    docstring: str | None

    async def display(self, context: UpdateHandlerContext) -> TreeMessage:
        name_message: TreeMessage
        match self.name if isinstance(self.name, str) else list(self.name):
            case []:
                name_message = TreeMessage.Skip
            case (str() as x) | [x]:
                name_message = TreeMessage.Text(f"/{x}")
            case [x, y]:
                name_message = TreeMessage.Text(f"/{x} or /{y}")
            case _:
                name_message = TreeMessage.Text("".join(f"/{x}, " for x in self.name[:-1]) + f"or /{self.name[-1]}")

        args_message: TreeMessage
        match self.has_args:
            case None:
                args_message = TreeMessage.Text("0 - ∞")
            case True:
                args_message = TreeMessage.Text("1 - ∞")
            case False:
                args_message = TreeMessage.Text("0")
            case _:
                args_message = TreeMessage.Text(str(self.has_args))

        async def user_name_lookup(u_id: int) -> str:
            return f"&lt;User {u_id}&gt;"  # TODO: try to look up username

        async def chat_name_lookup(c_id: int) -> str:
            chat_name: str = (await context.bot.get_chat(c_id)).effective_name
            return f"\"{chat_name}\""

        permission_message: TreeMessage = TreeMessage.Text(
            await (
                self.permissions if self.permissions is not None else UserSelector.Always
            ).describe(user_name_lookup, chat_name_lookup)
        )

        user_selector_filter_message: TreeMessage = TreeMessage.Text(
            await (
                self.user_selector_filter if self.user_selector_filter is not None else UserSelector.Always
            ).describe(user_name_lookup, chat_name_lookup)
        )

        docstring_head_message: TreeMessage = TreeMessage.Text(f"<b>{self.docstring.splitlines()[0]}</b>")
        docstring_tail_message: TreeMessage = TreeMessage.Text("\n".join(self.docstring.splitlines()[1:]))

        return name_message & TreeMessage.Sequence([
            TreeMessage.Named("Command", name_message),
            TreeMessage.Named("Args", args_message),
            TreeMessage.Named("Can be run", permission_message),
            TreeMessage.Named("Filter", user_selector_filter_message) @ (self.user_selector_filter is not None),
            docstring_head_message,
            docstring_tail_message @ ("\n" in self.docstring)
        ])
