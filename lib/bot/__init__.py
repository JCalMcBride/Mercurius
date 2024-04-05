import asyncio
import logging
from asyncio import sleep
from pathlib import Path
from typing import Union, List

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord import Intents, HTTPException, Forbidden, NotFound
from discord.ext.commands import Bot as BotBase, MissingRole, MissingPermissions, CommandOnCooldown, CommandNotFound
from discord.ext.commands import when_mentioned_or
from aiomysql import OperationalError
from market_engine.Models.MarketDatabase import MarketDatabase
from market_engine.Models.MarketItem import MarketItem

from fissure_engine.fissure_engine import FissureEngine
from lib.db.database import MercuriusDatabase

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
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
        self.market_db = None
        self.database = None
        self.guild = 939271447065526315
        self.emoji_dict = {}
        self.fissure_engine = FissureEngine()

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

    async def send_message(self, ctx, content: str = None, error: Exception = None,
                           embed: Union[discord.Embed, List, None] = None,
                           view: discord.ui.View = None, ephemeral: bool = False):
        if ctx is None:
            if error:
                self.logger.error(f"{content}", exc_info=error)
                return

            self.logger.info(f"{content}")
            return

        embeds = [embed] if isinstance(embed, discord.Embed) else embed

        message = await ctx.send(content=content, view=view, embeds=embeds, ephemeral=ephemeral)
        if error:
            self.logger.error(format_log_message(ctx, content), exc_info=error)
        else:
            self.logger.info(format_log_message(ctx, content))

        return message

    async def message_delete_handler(self, original_message, message, channel, delete_delay=15, delete_original=True):
        if message.guild:
            if delete_original:
                try:
                    await original_message.delete(delay=1)
                except NotFound:
                    pass
                except Forbidden:
                    pass
                except HTTPException:
                    pass

            if channel.name != "bot-spam":
                await sleep(delete_delay)
                try:
                    await message.delete()
                except NotFound:
                    pass
                except Forbidden:
                    pass
                except HTTPException:
                    pass

    def mdh(self, original_message, message, channel, delete_delay=15, delete_original=True):
        self.loop.create_task(self.message_delete_handler(original_message, message, channel, delete_delay, delete_original))

    def run(self):
        self.logger.info('Running setup.')
        self.setup()

        self.logger.info("Running bot.")
        super().run(self.token, reconnect=True, root_logger=True)

    async def get_valid_items(self, input_string: str,
                              fetch_parts: bool = False, fetch_orders: bool = False, fetch_part_orders: bool = False,
                              fetch_price_history: bool = False, fetch_demand_history: bool = False,
                              order_type: str = 'sell', platform='pc') -> tuple[list[str], list[MarketItem],
    list[str], str]:
        if 'buy' in input_string:
            order_type = 'buy'
            input_string = input_string.replace('buy', '').strip()
        elif 'sell' in input_string:
            input_string = input_string.replace('sell', '').strip()

        input_items = input_string.lower().strip().split(',')
        output_strings = []
        output_items = []

        subtypes = []
        for target_item in input_items:
            target_item = target_item.strip()
            wfm_item: MarketItem = await self.market_db.get_item(target_item.lower(),
                                                                 fetch_parts=fetch_parts,
                                                                 fetch_orders=fetch_orders,
                                                                 fetch_part_orders=fetch_part_orders,
                                                                 fetch_price_history=fetch_price_history,
                                                                 fetch_demand_history=fetch_demand_history,
                                                                 platform=platform)

            if wfm_item is None:
                output_strings.append(f"Item {target_item} does not exist on Warframe.Market")
                continue

            item_subtypes = wfm_item.get_subtypes(order_type)

            for valid_subtype in item_subtypes:
                if valid_subtype.lower() in target_item:
                    subtypes.append(valid_subtype)
                    target_item = target_item.replace(valid_subtype.lower(), '').strip()
                    break
            else:
                subtypes.append(None)

            if wfm_item.item_name != target_item and target_item.lower() not in wfm_item.item_name.lower():
                output_strings.append(f"{target_item} could not be found, closest match is {wfm_item.item_name}")
            else:
                output_strings.append("")

            output_items.append(wfm_item)

            if len(output_items) >= 5:
                output_strings.append("You can only show 5 items at a time.")
                break

        return output_strings, output_items, subtypes, order_type

    async def on_connect(self):
        self.logger.info("Bot connected.")

    async def on_disconnect(self):
        self.logger.info("Bot disconnected.")

    async def on_error(self, err, *args, **kwargs):
        if err == "on_command_error":
            await args[0].send("This command has an unspecified error. Please try again later.")

        self.logger.error(f"An error occurred: {err}", exc_info=True)
        raise

    async def on_command_error(self, ctx, exc):
        if isinstance(exc, CommandNotFound):
            pass
        elif isinstance(exc, CommandOnCooldown):
            await self.send_message(ctx, "Command is currently on cooldown, try again later.")
        elif isinstance(exc, MissingPermissions):
            await self.send_message(ctx, "You lack the permissions to use this command here.")
        elif isinstance(exc, MissingRole):
            await self.send_message(ctx, "You lack the role required to use this command here.")
        elif hasattr(exc, "original"):
            if isinstance(exc.original, SyntaxError):
                await self.send_message(ctx, "Something is wrong with the syntax of that command.")
            elif isinstance(exc, HTTPException):
                await self.send_message(ctx, "Unable to send message.")
            elif isinstance(exc, Forbidden):
                await self.send_message(ctx, "I do not have permission to do that.")
            else:
                raise exc.original
        else:
            raise exc

    async def on_ready(self):
        if not self.ready:
            self.guild = self.get_guild(self.guild)

            for emoji in self.guild.emojis:
                self.emoji_dict[emoji.name] = emoji

            try:
                self.market_db: MarketDatabase = MarketDatabase(user=self.bot_config['db_user'],
                                                                password=self.bot_config['db_password'],
                                                                host=self.bot_config['db_host'],
                                                                database='market')

            except OperationalError:
                self.market_db = None
                self.logger.error("Could not connect to database. Market cog will not be loaded.", exc_info=True)

            try:
                self.database: MercuriusDatabase = MercuriusDatabase(user=self.bot_config['db_user'],
                                                                     password=self.bot_config['db_password'],
                                                                     host=self.bot_config['db_host'],
                                                                     database='mercurius')
                self.database.build_database()
            except OperationalError as e:
                self.database = None
                self.logger.error("Could not connect to database.", exc_info=e)

            self.database.insert_servers([x.id for x in self.guilds])

            while not self.cogs_ready.all_ready():
                await sleep(0.5)

            self.stdout = self.get_channel(self.stdout)

            self.ready = True
            self.logger.info("Bot ready.")
        else:
            self.logger.info("Bot reconnected.")
