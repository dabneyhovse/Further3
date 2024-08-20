import os
from enum import Enum
from random import choice

from telegram import Message
from telegram.constants import ParseMode, ReactionEmoji

from handler_context import UpdateHandlerContext


def lol_emoji() -> str:
    return choice(["🤮", "💩", "🤡", "🥱", "🥴", "🐳", "🤨", "😴", "🤓", "💅", "🤪"])


class Verdict:
    class VerdictType(Enum):
        NONE = 0
        EMOJI = 1
        RESPONSE = 2

    def __init__(self, verdict_type: VerdictType, value: str | None) -> None:
        self.type: Verdict.VerdictType = verdict_type
        self.value: str | None = value

    async def apply(self, context: UpdateHandlerContext) -> None:
        message: Message = context.update.message
        match self.type:
            case Verdict.VerdictType.NONE:
                return
            case Verdict.VerdictType.EMOJI:
                await message.set_reaction(self.value)
            case Verdict.VerdictType.RESPONSE:
                await context.send_message(self.value,
                                           parse_mode=ParseMode.HTML,
                                           reply_to_message_id=message.message_id)


def e(value: str) -> Verdict:
    return Verdict(Verdict.VerdictType.EMOJI, value)


def r(value: str) -> Verdict:
    return Verdict(Verdict.VerdictType.RESPONSE, value)


def c(file_name: str) -> Verdict:
    with open(os.path.join("canned_responses", file_name)) as f:
        value = f.read()
        return Verdict(Verdict.VerdictType.RESPONSE, value)


opinions: dict[tuple[str, ...], list[Verdict]] = {
    ("anne carson",): [e("🤓"), e("🥱"), r("😴"), r("💤"), r("🥱")],
    ("among us", "amongus", "among-us"): [c("among_us.txt"), r("sus")],
    ("flowers from moby", "squat song", "Moby - 'Flower'"): [r("🦵"), r("Fl*m"), e("😭")],
    ("big iron",): [r("🤠"), r("🤠"), r("BIG iron? amrita.sticc"), r("You know what time it is? It's HIGH NOON"),
                    r("It's <i>HIGH NOON</i>")],
    ("jojo siwa",): [r("Oh not again..."), r("NOOOOOOOOOOOOO"), e("😭"), e("🤮")],
    ("taylor swift",): [r("Oh not again..."), r("You know, there are more then 4 chords out there"), e("😭"),
                        r("How about next time you queue actual music?"), r("I have a headache")]
}


async def be_opinionated(title: str, context: UpdateHandlerContext):
    title = title.lower()
    for keywords, verdicts in opinions.items():
        if any(keyword in title for keyword in keywords):
            await choice(verdicts).apply(context)
            return
