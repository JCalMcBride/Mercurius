from typing import List

import json
import logging
from contextlib import asynccontextmanager

import aiohttp
import discord
import pymysql as pymysql
import redis as redis
from discord.ext import commands
from discord.ext.commands import Cog
from aiolimiter import AsyncLimiter

logger = logging.getLogger('bot')
rate_limiter = AsyncLimiter(3, 1)  # 3 requests per 1 second


@asynccontextmanager
async def cache_manager():
    cache = redis.Redis(host='localhost', port=6379, db=1)
    yield cache


@asynccontextmanager
async def session_manager():
    async with aiohttp.ClientSession() as session:
        yield session


async def fetch_wfm_data(url: str, expiration: int = 60 * 60 * 24):
    async with cache_manager() as cache:
        data = cache.get(url)

        if data is not None:
            logger.debug(f"Using cached data for {url}")
            return json.loads(data)
        else:
            logger.debug(f"Fetching data for {url}")
            async with session_manager() as session:
                try:
                    async with session.get(url) as r:
                        data = await r.json()
                        cache.set(url, json.dumps(data), ex=expiration)
                except aiohttp.ClientError:
                    return None

    if 'error' in data:
        return None
    return data


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

    def get_item_statistics(self, item_id):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT datetime, avg_price "
                           "FROM item_statistics "
                           "WHERE item_id=%s "
                           "AND order_type='closed'", item_id)
            return cursor.fetchall()

    def get_item_volume(self, item_id, days: int = 31):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT volume "
                           "FROM item_statistics "
                           "WHERE datetime >= NOW() - INTERVAL %s DAY "
                           "AND order_type='closed' "
                           "AND item_id = %s", (days, item_id))
            return cursor.fetchall()


class MarketItem:
    base_api_url = "https://api.warframe.market/v1"
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
        self.orders = {'buy': list(), 'sell': list()}

    def embed(self):
        embed = discord.Embed(title=self.item_name, url=self.item_url, color=discord.Color.dark_gold())
        embed.set_thumbnail(url=self.thumb_url)
        return embed

    def get_item_statistics(self):
        item_statistics = self.database.get_item_statistics(self.item_id)
        print(item_statistics)

    def parse_orders(self, orders):
        for order in orders:
            parsed_order = {
                'last_update': order['last_update'],
                'quantity': order['quantity'],
                'price': order['platinum'],
                'user': order['user']['ingame_name'],
                'state': order['user']['status']
            }
            if order['order_type'] == 'sell':
                self.orders['sell'].append(parsed_order)
            else:
                self.orders['buy'].append(parsed_order)

        self.orders['sell'].sort(key=lambda x: x['last_update'], reverse=True)
        self.orders['sell'].sort(key=lambda x: x['price'])

        self.orders['buy'].sort(key=lambda x: x['last_update'], reverse=True)
        self.orders['buy'].sort(key=lambda x: x['price'], reverse=True)

    async def get_orders(self, order_type: str = 'sell', only_online: bool = True):
        orders = await fetch_wfm_data(f"{self.base_api_url}/items/{self.item_url_name}/orders")
        self.parse_orders(orders['payload']['orders'])

        if only_online:
            self.orders[order_type] = list(filter(lambda x: x['state'] == 'ingame', self.orders[order_type]))

        return self.orders[order_type]

    def get_volume(self, days: int = 31):
        volume = self.database.get_item_volume(self.item_id, days)
        volume = [x[0] for x in volume]
        print(volume)
        volume_string = ""
        volume_string += f"Last 24 hours: {sum(volume[-1:])}\n"
        volume_string += f"Last 7 days: {sum(volume[-7:])}\n"
        volume_string += f"Last {days} days: {sum(volume)}\n"
        volume_string += f"{days} day average: {sum(volume) // len(volume)}\n"
        return volume_string

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

    @commands.hybrid_command(name='marketstats',
                             description="Gets statistics for the requested item, if it exists.",
                             aliases=["getstats", 'wfmstats', 'wfms'])
    async def get_market_stats(self, ctx: commands.Context, *, target_item: str) -> None:
        wfm_item = self.market_db.get_item(target_item)
        if wfm_item is None or wfm_item.item_url is None:
            await self.bot.send_message(ctx, f"Item {target_item} does not on Warframe.Market")
            return

        wfm_item.get_item_statistics()
        await self.bot.send_message(ctx, embed=wfm_item.embed())

    @commands.hybrid_command(name='marketorders',
                             description="Gets orders for the requested item, if it exists.",
                             aliases=["getorders", 'wfmorders', 'wfmo', 'go'])
    async def get_market_orders(self, ctx: commands.Context, *, target_item: str) -> None:
        num_orders = 5

        wfm_item = self.market_db.get_item(target_item)
        if wfm_item is None or wfm_item.item_url is None:
            await self.bot.send_message(ctx, f"Item {target_item} does not on Warframe.Market")
            return

        orders = await wfm_item.get_orders()
        if len(orders) == 0:
            await self.bot.send_message(ctx, f"No orders found for {target_item}.")
            return

        orders = orders[:num_orders]

        user_string = '\n'.join([f"{order['user']}" for order in orders])
        quantity_string = '\n'.join([f"{order['quantity']}" for order in orders])
        price_string = '\n'.join([f"{order['price']}" for order in orders])

        embed = discord.Embed(title=f"{wfm_item.item_name}",
                              color=discord.Color.blue())
        embed.add_field(name='Volume', value=wfm_item.get_volume(days=31), inline=False)
        embed.add_field(name="User", value=user_string, inline=True)
        embed.add_field(name="Price", value=price_string, inline=True)
        embed.add_field(name="Quantity", value=quantity_string, inline=True)

        await self.bot.send_message(ctx, embed=embed)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Market")


async def setup(bot):
    await bot.add_cog(Market(bot))
