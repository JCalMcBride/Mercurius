import asyncio
import logging
from asyncio import sleep
from pathlib import Path

from discord import Intents
from discord.ext.commands import Bot as BotBase
from discord.ext.commands import when_mentioned_or

cogs_dir = Path("lib/cogs")
COGS = [p.stem for p in cogs_dir.glob("*.py")]

class Ready(object):
    def __init__(self):
        self.logger = logging.getLogger('bot')
        for cog in COGS:
            setattr(self, cog, False)

    def ready_up(self, cog):
        setattr(self, cog, True)
        self.logger.info(f"Cog ready: {cog}")

    def all_ready(self):
        return all([getattr(self, cog) for cog in COGS])


def get_prefix(bot, message):
    prefix_list = ['--', '—']
    if not message.guild:
        prefix_list.append('')

    return when_mentioned_or(*prefix_list)(bot, message)


class Bot(BotBase):
    def __init__(self, bot_config):
        self.stdout = None
        self.ready = False
        self.cogs_ready = Ready()
        self.logger = logging.getLogger('bot')
        self.token = bot_config['discord_token']

        super().__init__(
            command_prefix=get_prefix,
            owner_ids=bot_config['owner_ids'],
            intents=Intents.all()
        )

    def setup(self):
        for cog in COGS:
            asyncio.run(self.load_extension(f"lib.cogs.{cog}"))
            self.logger.info(f"Cog loaded: {cog}")

        self.logger.info("Setup complete.")

    def run(self):
        self.logger.info('Running setup.')
        self.setup()

        self.logger.info("Running bot.")
        super().run(self.token, reconnect=True, root_logger=True)

    async def on_connect(self):
        self.logger.info("Bot connected.")

    async def on_disconnect(self):
        self.logger.info("Bot disconnected.")

    async def on_error(self, err, *args, **kwargs):
        self.logger.error(f"An error occurred: {err}", exc_info=True)
        raise

    async def on_ready(self):
        if not self.ready:

            while not self.cogs_ready.all_ready():
                await sleep(0.5)

            self.ready = True
            self.logger.info("Bot ready.")
        else:
            self.logger.info("Bot reconnected.")
