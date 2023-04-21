import asyncio
import logging
from asyncio import sleep
from pathlib import Path

import discord
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


def format_log_message(ctx, message):
    return f"User: {ctx.author} | Command: {ctx.command} | {message}"


class Bot(BotBase):
    def __init__(self, bot_config):
        self.stdout = 1098289631444873356
        self.ready = False
        self.cogs_ready = Ready()
        self.logger = logging.getLogger('bot')
        self.token = bot_config['discord_token']
        self.bot_config = bot_config

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

    async def send_message(self, ctx, content: str = None, error: Exception = None, embed: discord.Embed = None,
                           view: discord.ui.View = None):
        if ctx is None:
            if error:
                self.logger.error(f"{content}", exc_info=error)
                return

            self.logger.info(f"{content}")
            return

        message = await ctx.send(content=content, embed=embed, view=view)
        if error:
            self.logger.error(format_log_message(ctx, content), exc_info=error)
        else:
            self.logger.info(format_log_message(ctx, content))

        return message

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

            self.stdout = self.get_channel(self.stdout)

            self.ready = True
            self.logger.info("Bot ready.")
        else:
            self.logger.info("Bot reconnected.")
