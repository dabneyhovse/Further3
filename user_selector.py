from __future__ import annotations

from collections.abc import Callable, Coroutine
from enum import Flag, auto, StrEnum

from telegram import Chat, Bot
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import BadRequest

from gadt import GADT


class ChatTypeFlag(Flag):
    INLINE_QUERY = auto()
    DM = auto()
    GROUP = auto()
    SUPERGROUP = auto()
    CHANNEL = auto()

    def __init__(self, value: int) -> None:
        super().__init__(self, value)

    @property
    def chat_type_value(self) -> str:
        return {
            ChatTypeFlag.INLINE_QUERY: ChatType.SENDER,
            ChatTypeFlag.DM: ChatType.PRIVATE,
            ChatTypeFlag.GROUP: ChatType.GROUP,
            ChatTypeFlag.SUPERGROUP: ChatType.SUPERGROUP,
            ChatTypeFlag.CHANNEL: ChatType.CHANNEL,
        }[self]

    def __eq__(self, other) -> bool:
        if isinstance(other, (ChatType, str)):
            return self.chat_type_value == other
        else:
            return super().__eq__(other)

    @staticmethod
    def from_chat_type(chat_type: ChatType) -> ChatTypeFlag:
        return {
            ChatType.SENDER: ChatTypeFlag.INLINE_QUERY,
            ChatType.PRIVATE: ChatTypeFlag.DM,
            ChatType.GROUP: ChatTypeFlag.GROUP,
            ChatType.SUPERGROUP: ChatTypeFlag.SUPERGROUP,
            ChatType.CHANNEL: ChatTypeFlag.CHANNEL,
        }[chat_type]

    @property
    def name(self) -> str:
        match self:
            case ChatTypeFlag.INLINE_QUERY:
                return "inline queries"
            case ChatTypeFlag.DM:
                return "private chats"
            case ChatTypeFlag.GROUP:
                return "group chats"
            case ChatTypeFlag.SUPERGROUP:
                return "supergroups"
            case ChatTypeFlag.CHANNEL:
                return "channels"
            case _:
                return "<COMPOUND>"


class MembershipStatusFlag(Flag):
    ADMINISTRATOR = auto()
    OWNER = auto()
    BANNED = auto()
    LEFT = auto()
    MEMBER = auto()
    RESTRICTED = auto()
    NONMEMBER = auto()

    @property
    def chat_member_status_value(self) -> str:
        return {
            MembershipStatusFlag.ADMINISTRATOR: ChatMemberStatus.ADMINISTRATOR,
            MembershipStatusFlag.OWNER: ChatMemberStatus.OWNER,
            MembershipStatusFlag.BANNED: ChatMemberStatus.BANNED,
            MembershipStatusFlag.LEFT: ChatMemberStatus.LEFT,
            MembershipStatusFlag.MEMBER: ChatMemberStatus.MEMBER,
            MembershipStatusFlag.RESTRICTED: ChatMemberStatus.RESTRICTED,
            MembershipStatusFlag.NONMEMBER: "nonmember"
        }[self]

    def __eq__(self, other) -> bool:
        if isinstance(other, (ChatMemberStatus, str)):
            return self.chat_member_status_value == other
        else:
            return super().__eq__(other)

    @staticmethod
    def from_chat_member_status(member_status: ChatMemberStatus) -> MembershipStatusFlag:
        return {
            ChatMemberStatus.ADMINISTRATOR: MembershipStatusFlag.ADMINISTRATOR,
            ChatMemberStatus.OWNER: MembershipStatusFlag.OWNER,
            ChatMemberStatus.BANNED: MembershipStatusFlag.BANNED,
            ChatMemberStatus.LEFT: MembershipStatusFlag.LEFT,
            ChatMemberStatus.MEMBER: MembershipStatusFlag.MEMBER,
            ChatMemberStatus.RESTRICTED: MembershipStatusFlag.RESTRICTED,
            "nonmember": MembershipStatusFlag.NONMEMBER
        }[member_status]

    @property
    def name(self) -> str:
        match self:
            case MembershipStatusFlag.ADMINISTRATOR:
                return "administrators"
            case MembershipStatusFlag.OWNER:
                return "the chat owner"
            case MembershipStatusFlag.BANNED:
                return "banned members"
            case MembershipStatusFlag.LEFT:
                return "members that left the chat"
            case MembershipStatusFlag.MEMBER:
                return "members"
            case MembershipStatusFlag.RESTRICTED:
                return "restricted members"
            case MembershipStatusFlag.NONMEMBER:
                return "non-members"


class ConjunctionType(StrEnum):
    CONJUNCTION = "and"
    DISJUNCTION = "or"
    NEG_DISJUNCTION = "nor"


class UserSelector(metaclass=GADT):
    Never: UserSelector
    Always: UserSelector
    And: Callable[[UserSelector, UserSelector], UserSelector]
    Or: Callable[[UserSelector, UserSelector], UserSelector]
    Not: Callable[[UserSelector], UserSelector]
    All: Callable[[list[UserSelector]], UserSelector]
    Any: Callable[[list[UserSelector]], UserSelector]
    UserIDIsIn: Callable[[list[int]], UserSelector]
    ChatIDIsIn: Callable[[list[int]], UserSelector]
    ChatTypeIsIn: Callable[[ChatTypeFlag], UserSelector]
    MembershipStatusIsIn: Callable[[MembershipStatusFlag], UserSelector]

    def __and__(self, other: UserSelector) -> UserSelector:
        return UserSelector.And(self, other)

    def __or__(self, other: UserSelector) -> UserSelector:
        return UserSelector.Or(self, other)

    def __invert__(self) -> UserSelector:
        return UserSelector.Not(self)

    async def matches(self, bot: Bot, user_id: int, chat: Chat) -> bool:
        match self:
            case UserSelector.Never:
                return False
            case UserSelector.Always:
                return True
            case UserSelector.And(x, y):
                return await x.matches(bot, user_id, chat) and await y.matches(bot, user_id, chat)
            case UserSelector.Or(x, y):
                return await x.matches(bot, user_id, chat) or await y.matches(bot, user_id, chat)
            case UserSelector.Not(x):
                return not await x.matches(bot, user_id, chat)
            case UserSelector.All(xs):
                return all(await x.matches(bot, user_id, chat) for x in xs)
            case UserSelector.Any(xs):
                return any(await x.matches(bot, user_id, chat) for x in xs)
            case UserSelector.UserIDIsIn(ids):
                return user_id in ids
            case UserSelector.ChatIDIsIn(ids):
                return chat.id in ids
            case UserSelector.ChatTypeIsIn(types):
                return ChatTypeFlag.from_chat_type(chat.type) in types  # noqa
            case UserSelector.MembershipStatusIsIn(statuses):
                try:
                    return MembershipStatusFlag.from_chat_member_status(
                        (await bot.get_chat_member(chat.id, user_id)).status  # noqa
                    ) in statuses
                except BadRequest as e:
                    if e.message != "Participant_id_invalid":
                        raise
                    return MembershipStatusFlag.NONMEMBER in statuses

    def apply_to_user_selector_args(self, f: Callable[[UserSelector], UserSelector]) -> UserSelector:
        match self:
            case (UserSelector.Always | UserSelector.Never
                  | UserSelector.UserIDIsIn() | UserSelector.ChatIDIsIn()
                  | UserSelector.ChatTypeIsIn() | UserSelector.MembershipStatusIsIn()):
                return self
            case UserSelector.Not(x):
                return UserSelector.Not(f(x))
            case UserSelector.All(xs) | UserSelector.Any(xs):
                return type(self)([f(x) for x in xs])  # noqa
            case UserSelector.And(x, y) | UserSelector.Or(x, y):
                return type(self)(f(x), f(y))  # noqa

    def simplify_step(self) -> UserSelector:
        match self:
            case UserSelector.And(x, y):
                return UserSelector.All([x, y])
            case UserSelector.Or(x, y):
                return UserSelector.Any([x, y])

            case UserSelector.Not(UserSelector.Not(x)):
                return x
            case UserSelector.Not(UserSelector.Always):
                return UserSelector.Never
            case UserSelector.Not(UserSelector.Never):
                return UserSelector.Always

            case UserSelector.All([]):
                return UserSelector.Always
            case UserSelector.Any([]):
                return UserSelector.Never
            case UserSelector.UserIDIsIn([]):
                return UserSelector.Never
            case UserSelector.ChatIDIsIn([]):
                return UserSelector.Never
            case UserSelector.ChatTypeIsIn([]):
                return UserSelector.Never
            case UserSelector.MembershipStatusIsIn([]):
                return UserSelector.Never

            case UserSelector.Any([x]):
                return x
            case UserSelector.All([x]):
                return x

            case UserSelector.All(xs) if UserSelector.Always in xs:
                return UserSelector.All([x for x in xs if x != UserSelector.Always])
            case UserSelector.Any(xs) if UserSelector.Never in xs:
                return UserSelector.Any([x for x in xs if x != UserSelector.Never])

            case UserSelector.All(xs) if UserSelector.Never in xs:
                return UserSelector.Never
            case UserSelector.Any(xs) if UserSelector.Always in xs:
                return UserSelector.Always

            case UserSelector.All(xs):
                args = []
                for x in xs:
                    match x:
                        case UserSelector.All(ys):
                            args += ys
                        case UserSelector.Not(UserSelector.Any(ys)):
                            args += [UserSelector.Not(y) for y in ys]
                        case _:
                            args.append(x)
                return UserSelector.All(args)
            case UserSelector.Any(xs):
                args = []
                for x in xs:
                    match x:
                        case UserSelector.Any(ys):
                            args += ys
                        case UserSelector.Not(UserSelector.All(ys)):
                            args += [UserSelector.Not(y) for y in ys]
                        case _:
                            args.append(x)
                return UserSelector.Any(args)

            case _:
                return self

    def simplify_iteration(self) -> UserSelector:
        if self.__construction_data__ is None:
            return self

        simplified: UserSelector = self.apply_to_user_selector_args(UserSelector.simplify_iteration)  # noqa

        while True:
            new_simplified = simplified.simplify_step()
            if new_simplified == simplified:
                return simplified
            simplified = new_simplified

    @property
    def negated(self) -> bool:
        match self:
            case UserSelector.Not(x):
                return not x.negated
            case _:
                return False

    def push_negation_upward(self) -> UserSelector:
        if self.__construction_data__ is None:
            return self

        recursed: UserSelector = self.apply_to_user_selector_args(UserSelector.push_negation_upward)  # noqa

        match recursed:
            case UserSelector.All(xs) if any(x.negated for x in xs):  # noqa
                return UserSelector.Not(UserSelector.Any([UserSelector.Not(x) for x in xs]))
            case UserSelector.Any(xs) if any(x.negated for x in xs):  # noqa
                return UserSelector.Not(UserSelector.All([UserSelector.Not(x) for x in xs]))
            case _:
                return recursed.simplify_step()

    def settle_negation(self) -> UserSelector:
        if self.__construction_data__ is None:
            return self

        match self:
            case UserSelector.Not(UserSelector.Not(x)):
                return x.settle_negation()
            case UserSelector.Not(UserSelector.All(xs)):
                return UserSelector.Any([UserSelector.Not(x).settle_negation() for x in xs])
            case UserSelector.Not(UserSelector.Any(xs)) if sum(x.negated for x in xs) * 2 >= len(xs):
                return UserSelector.All([UserSelector.Not(x).settle_negation() for x in xs])
            case _:
                return self.apply_to_user_selector_args(UserSelector.settle_negation)  # noqa

    def simplify(self) -> UserSelector:
        simplified: UserSelector = self.simplify_iteration()

        while True:
            pushed: UserSelector = simplified.push_negation_upward()
            simple_pushed: UserSelector = pushed.simplify_iteration()
            settled: UserSelector = simple_pushed.settle_negation()
            new_simplified: UserSelector = settled.simplify_iteration()
            if new_simplified == simplified:
                return new_simplified
            simplified = new_simplified

    @staticmethod
    def isolate_text(description: tuple[str, int]) -> str:
        match description[1]:
            case 0 | 1 | 2:
                return description[0]
            case _:
                return f"[{description[0]}]"

    @staticmethod
    def list_text(descriptions: list[tuple[str, int]], conjunction_type: ConjunctionType) -> tuple[str, int]:
        level: int = max(isolation_level for _, isolation_level in descriptions)
        items: list[str] = [item for item, _ in descriptions]
        match items, conjunction_type, level:
            case [], ConjunctionType.DISJUNCTION, _:
                return "never", 0
            case [], (ConjunctionType.CONJUNCTION | ConjunctionType.NEG_DISJUNCTION), _:
                return "always", 0
            case [item], _, _:
                return item, level
            case [item_1, item_2], ConjunctionType.DISJUNCTION, 0:
                return f"{item_1} or {item_2}", 1
            case [item_1, item_2], ConjunctionType.CONJUNCTION, 0:
                return f"{item_1} {item_2}", 1
            case [item_1, item_2], ConjunctionType.DISJUNCTION, _:
                return f"either {item_1} or {item_2}", level
            case [item_1, item_2], ConjunctionType.CONJUNCTION, _:
                return f"if both {item_1} and {item_2}", level
            case [item_1, item_2], ConjunctionType.NEG_DISJUNCTION, _:
                return f"neither {item_1} nor {item_2}", level
            case _:
                delimiter: str = "; " if level == 2 else ", "
                return (
                        ("neither " if conjunction_type == ConjunctionType.NEG_DISJUNCTION else "") +
                        delimiter.join(UserSelector.isolate_text(description) for description in descriptions[: -1]) +
                        f"{delimiter}{conjunction_type} {items[-1]}"
                ), min(level - 1, 0) % 2 + 2

    async def describe_rec(self,
                           user_name_lookup: Callable[[int], Coroutine[None, None, str]],
                           chat_name_lookup: Callable[[int], Coroutine[None, None, str]]
                           ) -> tuple[str, int]:
        match self:
            case UserSelector.Never:
                return "never", 0
            case UserSelector.Always:
                return "always", 0

            case UserSelector.UserIDIsIn(ids):
                option_list = UserSelector.list_text(
                    [(await user_name_lookup(user_id), 0) for user_id in ids],
                    ConjunctionType.DISJUNCTION
                )
                return f"by {option_list[0]}", option_list[1]
            case UserSelector.Not(UserSelector.UserIDIsIn(ids)):
                option_list = UserSelector.list_text(
                    [(await user_name_lookup(chat_id), 0) for chat_id in ids],
                    ConjunctionType.DISJUNCTION
                )
                return f"by anyone other than {option_list[0]}", option_list[1]

            case UserSelector.ChatIDIsIn(ids):
                option_list = UserSelector.list_text(
                    [(await chat_name_lookup(user_name), 0) for user_name in ids],
                    ConjunctionType.DISJUNCTION
                )
                return f"in {option_list[0]}", option_list[1]
            case UserSelector.Not(UserSelector.ChatIDIsIn(ids)):
                option_list = UserSelector.list_text(
                    [(await chat_name_lookup(user_name), 0) for user_name in ids],
                    ConjunctionType.DISJUNCTION
                )
                return f"in any chat other than {option_list[0]}", option_list[1]

            case UserSelector.ChatTypeIsIn(chat_types):
                option_list = UserSelector.list_text(
                    [(chat_type.name, 0) for chat_type in chat_types],
                    ConjunctionType.DISJUNCTION
                )
                return f"in {option_list[0]}", option_list[1]
            case UserSelector.Not(UserSelector.ChatTypeIsIn(chat_types)):
                return await UserSelector.ChatTypeIsIn(~chat_types).describe_rec(user_name_lookup, chat_name_lookup)

            case UserSelector.MembershipStatusIsIn(user_statuses):
                option_list = UserSelector.list_text(
                    [(user_status.name, 0) for user_status in user_statuses],
                    ConjunctionType.DISJUNCTION
                )
                return f"by {option_list[0]}", option_list[1]
            case UserSelector.Not(UserSelector.MembershipStatusIsIn(user_statuses)):
                return await (UserSelector.MembershipStatusIsIn(~user_statuses)
                              .describe_rec(user_name_lookup, chat_name_lookup))

            case UserSelector.Not(UserSelector.Any(xs)):
                return UserSelector.list_text(
                    [await x.describe_rec(user_name_lookup, chat_name_lookup) for x in xs],
                    ConjunctionType.NEG_DISJUNCTION
                )
            case UserSelector.All([x, UserSelector.Not(y)]) | UserSelector.All([UserSelector.Not(y), x]):
                x_description: tuple[str, int] = await x.describe_rec(user_name_lookup, chat_name_lookup)
                y_description: tuple[str, int] = await y.describe_rec(user_name_lookup, chat_name_lookup)
                return (
                        ("if " if max(x_description[1], y_description[1]) else "") +
                        f"{x_description[0]} but not {y_description[0]}"
                ), min(max(x_description[1], y_description[1]), 1)
            case (UserSelector.Any([x, UserSelector.Not(y)]) |
                  UserSelector.Any([UserSelector.Not(y), x])) if not isinstance(x, UserSelector.Not):  # noqa
                x_description: tuple[str, int] = await x.describe_rec(user_name_lookup, chat_name_lookup)
                y_description: tuple[str, int] = await y.describe_rec(user_name_lookup, chat_name_lookup)
                return (
                    f"if not {y_description[0]} except {x_description[0]}",
                    min(max(x_description[1], y_description[1]), 1)
                )

            case UserSelector.And(x, y):
                return await UserSelector.All([x, y]).describe_rec(user_name_lookup, chat_name_lookup)
            case UserSelector.Or(x, y):
                return await UserSelector.Any([x, y]).describe_rec(user_name_lookup, chat_name_lookup)
            case UserSelector.Not(x):
                text, isolation = await x.describe_rec(user_name_lookup, chat_name_lookup)
                match isolation:
                    case 0 | 1:
                        return f"not {text}", 1
                    case _:
                        return f"not [{text}]", 1

            case UserSelector.All(xs):
                return UserSelector.list_text(
                    [await x.describe_rec(user_name_lookup, chat_name_lookup) for x in xs],
                    ConjunctionType.CONJUNCTION
                )
            case UserSelector.Any(xs):
                return UserSelector.list_text(
                    [await x.describe_rec(user_name_lookup, chat_name_lookup) for x in xs],
                    ConjunctionType.DISJUNCTION
                )

    async def describe(self,
                       user_name_lookup: Callable[[int], Coroutine[None, None, str]],
                       chat_name_lookup: Callable[[int], Coroutine[None, None, str]]
                       ) -> str:
        simplified: UserSelector = self.simplify()
        return (await simplified.describe_rec(user_name_lookup, chat_name_lookup))[0]
