from typing import List

import aiohttp
import discord
import pymysql as pymysql
from discord.ext import commands
from discord.ext.commands import Cog


async def fetch_wfm_data(url: str):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as r:
                data = await r.json()
                if 'error' in data:
                    return None
                return data
        except aiohttp.ClientError:
            return None


class MarketDatabase:
    def __init__(self, user: str, password: str, host: str, database: str):
        self.connection = pymysql.connect(user=user,
                                          password=password,
                                          host=host,
                                          database=database)

    def get_item(self, item):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT * FROM items WHERE item_name=%s", item)
            item_data = cursor.fetchone()
            if item_data is None:
                return None

            sub_types = cursor.execute("SELECT * FROM item_subtypes WHERE item_id=%s", item_data[0])
            mod_ranks = cursor.execute("SELECT * FROM item_mod_ranks WHERE item_id=%s", item_data[0])

            return MarketItem(self, *item_data, sub_types, mod_ranks)


class MarketItem:
    base_url = "https://warframe.market/items"
    asset_url = "https://warframe.market/static/assets"

    def __init__(self, database: MarketDatabase,
                 item_id: str, item_name: str, item_type: str, item_url_name: str, thumb: str,
                 sub_types: str, mod_rank: str):
        self.database: MarketDatabase = database
        self.item_id: str = item_id
        self.item_name: str = item_name
        self.item_type: str = item_type
        self.item_url_name: str = item_url_name
        self.thumb: str = thumb
        self.thumb_url: str = f"{MarketItem.asset_url}/{self.thumb}"
        self.item_url: str = f"{MarketItem.base_url}/{self.item_url_name}"
        self.sub_types: List = sub_types.split(",") if sub_types else list()
        self.mod_rank: List = mod_rank.split(",") if mod_rank else list()

    def embed(self):
        embed = discord.Embed(title=self.item_name, url=self.item_url, color=discord.Color.dark_gold())
        embed.set_thumbnail(url=self.thumb_url)
        return embed

    def __str__(self):
        return f"{self.item_name} ({self.item_url_name})"

    def __repr__(self):
        return f"{self.item_name} ({self.item_url_name})"

    def __eq__(self, other):
        if isinstance(other, MarketItem):
            return self.item_id == other.item_id
        else:
            return False

    def __hash__(self):
        return hash(self.item_id)

    def __lt__(self, other):
        if isinstance(other, MarketItem):
            return self.item_id < other.item_id
        else:
            return False

    def __le__(self, other):
        if isinstance(other, MarketItem):
            return self.item_id <= other.item_id
        else:
            return False

    def __gt__(self, other):
        if isinstance(other, MarketItem):
            return self.item_id > other.item_id
        else:
            return False

    def __ge__(self, other):
        if isinstance(other, MarketItem):
            return self.item_id >= other.item_id
        else:
            return False

    def __ne__(self, other):
        if isinstance(other, MarketItem):
            return self.item_id != other.item_id
        else:
            return True


class Market(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.base_api_url = "https://api.warframe.market/v1"
        self.base_url = "https://warframe.market"
        self.market_db = MarketDatabase(user=self.bot.bot_config['db_user'],
                                        password=self.bot.bot_config['db_password'],
                                        host=self.bot.bot_config['db_host'],
                                        database=self.bot.bot_config['db_name'])

    @commands.hybrid_command(name='marketprofile',
                             description="Gets link to the requested user's profile, if it exists.",
                             aliases=["gen", "getprofile", "gp", 'wfmprofile', 'wfm', 'wfmp', 'mp'])
    async def get_market_profile(self, ctx: commands.Context, target_user: str) -> None:
        wfm_api_profile = f"{self.base_api_url}/profile/{target_user}"
        wfm_profile = f"{self.base_url}/profile/{target_user}"

        data = await fetch_wfm_data(wfm_api_profile)

        if data is None:
            await self.bot.send_message(ctx, f"User {target_user} does not exist on Warframe.Market "
                                             f"or an error occurred while fetching data.")
            return

        await self.bot.send_message(ctx, wfm_profile)

    @commands.hybrid_command(name='marketitem',
                             description="Gets link to the requested item's page, if it exists.",
                             aliases=["getitem", 'wfmitem', 'wfi', 'wfmi'])
    async def get_market_item(self, ctx: commands.Context, *, target_item: str) -> None:
        wfm_item = self.market_db.get_item(target_item)
        if wfm_item is None or wfm_item.item_url is None:
            await self.bot.send_message(ctx, f"Item {target_item} does not on Warframe.Market")
            return

        await self.bot.send_message(ctx, embed=wfm_item.embed())

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Market")


async def setup(bot):
    await bot.add_cog(Market(bot))
