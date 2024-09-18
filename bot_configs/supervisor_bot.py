from __future__ import annotations

from bot_config import BotConfig

BOT_TOKEN_FILE = "../sensitive/supervisor_bot_token.txt"

bot_config = BotConfig(
    BOT_TOKEN_FILE,
    persistence_file="../store/supervisor_persistence_store",
    resource_dir="../downloads"
)

bot_config.build()
