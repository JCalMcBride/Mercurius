from __future__ import annotations

import json
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Tuple, Union, Dict, Any

import aiohttp
import discord
import pymysql as pymysql
import redis
from aiohttp import TCPConnector, ClientTimeout
from aiolimiter import AsyncLimiter
from discord.ext import commands
from discord.ext.commands import Cog
from discord.utils import escape_markdown
from fuzzywuzzy import fuzz
from pymysql import Connection

logger = logging.getLogger('bot')
rate_limiter = AsyncLimiter(3, 1)  # 3 requests per 1 second
connector = TCPConnector(limit=10)
headers = {"Connection": "keep-alive", "Upgrade-Insecure-Requests": "1"}
timeout = ClientTimeout(total=5, connect=2, sock_connect=2, sock_read=2)
session = aiohttp.ClientSession(connector=connector, headers=headers, timeout=timeout)


@asynccontextmanager
async def cache_manager():
    cache = redis.Redis(host='localhost', port=6379, db=0)
    yield cache


async def fetch_wfm_data(url: str):
    async with cache_manager() as cache:
        data = cache.get(url)
        if data is not None:
            logger.debug(f"Using cached data for {url}")
            return json.loads(data)

    retries = 3
    for _ in range(retries):
        try:
            async with rate_limiter:
                async with session.get(url) as r:
                    if r.status == 200:
                        logger.info(f"Fetched data from {url}")
                        data = await r.json()

                        # Store the data in the cache with a 1-minute expiration
                        cache.set(url, json.dumps(data), ex=60)

                        return await r.json()
                    else:
                        raise aiohttp.ClientError
        except aiohttp.ClientError:
            logger.error(f"Failed to fetch data from {url}")


def format_row(label, value, average=None):
    if average is not None:
        return f"{label:<7} {value:<7} {average:<4}\n"
    else:
        return f"{label:<7} {value:<7}\n"


def get_item_names(item: Dict[str, Any]) -> List[str]:
    return [item['item_name']] + item.get('aliases', [])


def closest_common_word(word: str, common_words: set, threshold: int) -> Optional[str]:
    best_match, best_score = None, 0
    for common_word in common_words:
        score = fuzz.ratio(word, common_word)
        if score > best_score:
            best_match, best_score = common_word, score

    return best_match if best_score >= threshold else None


def remove_common_words(name: str, common_words: set) -> str:
    name = remove_blueprint(name)
    threshold = 80  # Adjust this value based on the desired level of fuzzy matching

    words = name.split()
    filtered_words = [word for word in words if not closest_common_word(word, common_words, threshold)]
    return ' '.join(filtered_words)


def remove_blueprint(s: str) -> str:
    words = s.lower().split()
    if words[-1:] == ['blueprint'] and words[-2:-1] != ['prime']:
        return ' '.join(words[:-1])
    return s.lower()


def find_best_match(item_name: str, items: List[Dict[str, Any]]) -> Tuple[int, Optional[Dict[str, str]]]:
    best_score, best_item = 0, None
    common_words = {'arcane', 'prime', 'scene', 'set'}

    item_name = remove_common_words(item_name, common_words)

    for item in items:
        processed_names = [remove_common_words(name, common_words) for name in get_item_names(item)]
        max_score = max(fuzz.ratio(item_name, name) for name in processed_names)
        if max_score > best_score:
            best_score, best_item = max_score, item

        if best_score == 100:
            break

    return best_score, best_item


class MarketDatabase:
    GET_ITEM_QUERY: str = "SELECT * FROM items WHERE item_name=%s"
    GET_ITEM_SUBTYPES_QUERY: str = "SELECT * FROM item_subtypes WHERE item_id=%s"
    GET_ITEM_MOD_RANKS_QUERY: str = "SELECT * FROM item_mod_ranks WHERE item_id=%s"
    GET_ITEM_STATISTICS_QUERY: str = ("SELECT datetime, avg_price "
                                      "FROM item_statistics "
                                      "WHERE item_id=%s "
                                      "AND order_type='closed'")
    GET_ITEM_VOLUME_QUERY: str = ("SELECT volume "
                                  "FROM item_statistics "
                                  "WHERE datetime >= NOW() - INTERVAL %s DAY "
                                  "AND order_type='closed' "
                                  "AND item_id = %s")
    GET_ALL_ITEMS_QUERY: str = ("SELECT items.id, items.item_name, items.item_type, "
                                "items.url_name, items.thumb, item_aliases.alias "
                                "FROM items LEFT JOIN item_aliases ON items.id = item_aliases.item_id")
    GET_ITEMS_IN_SET_QUERY: str = ("SELECT items.id, items.item_name, items.item_type, items.url_name, items.thumb "
                                   "FROM items_in_set "
                                   "INNER JOIN items "
                                   "ON items_in_set.item_id = items.id "
                                   "WHERE items_in_set.set_id = %s")

    def __init__(self, user: str, password: str, host: str, database: str) -> None:
        self.connection: Connection = pymysql.connect(user=user,
                                                      password=password,
                                                      host=host,
                                                      database=database)

        self.all_items = self.get_all_items()

    def get_all_items(self) -> list[list]:
        all_data = self._execute_query(self.GET_ALL_ITEMS_QUERY)

        item_dict = defaultdict(lambda: defaultdict(list))
        for item_id, item_name, item_type, url_name, thumb, alias in all_data:
            if not item_dict[item_id]['item_data']:
                item_dict[item_id]['item_data'] = {'id': item_id, 'item_name': item_name, 'item_type': item_type,
                                                   'url_name': url_name, 'thumb': thumb}
            if alias:
                item_dict[item_id]['aliases'].append(alias)

        all_items = [item_data['item_data'] for item_data in item_dict.values()]

        return all_items

    def _execute_query(self, query: str, *params) -> List[Tuple]:
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def get_item(self, item: str) -> Optional[MarketItem]:
        fuzzy_item = self.get_fuzzy_item(item)

        if fuzzy_item is None:
            return None

        item_data: str = list(fuzzy_item.values())
        sub_types: tuple = self._execute_query(self.GET_ITEM_SUBTYPES_QUERY, item_data[0])
        mod_ranks: tuple = self._execute_query(self.GET_ITEM_MOD_RANKS_QUERY, item_data[0])

        return MarketItem(self, *item_data, sub_types, mod_ranks)

    def get_item_statistics(self, item_id: str) -> List[Tuple]:
        return self._execute_query(self.GET_ITEM_STATISTICS_QUERY, item_id)

    def get_item_volume(self, item_id: str, days: int = 31) -> List[Tuple]:
        return self._execute_query(self.GET_ITEM_VOLUME_QUERY, days, item_id)

    def close(self) -> None:
        self.connection.close()

    def get_fuzzy_item(self, item_name: str) -> Optional[Dict[str, str]]:
        best_score, best_item = find_best_match(item_name, self.all_items)

        return best_item if best_score > 50 else None

    def get_item_parts(self, item_id: str) -> List[Tuple]:
        return self._execute_query(self.GET_ITEMS_IN_SET_QUERY, item_id)


def format_user(user) -> str:
    return f"[{escape_markdown(str(user))}]({f'https://warframe.market/profile/{user}'})"


def format_volume(day: int, week: int, month: int) -> str:
    return f'```python\n' \
           f'{format_row("Day:", day)}' \
           f'{format_row("Week:", week, week // 7)}' \
           f'{format_row("Month:", month, month // 31)}```'


def get_sums(volume: list) -> tuple:
    day_total = sum(volume[-1:])
    week_total = sum(volume[-7:])
    month_total = sum(volume)
    return day_total, week_total, month_total


class MarketItem:
    base_api_url: str = "https://api.warframe.market/v1"
    base_url: str = "https://warframe.market/items"
    asset_url: str = "https://warframe.market/static/assets"

    def __init__(self, database: MarketDatabase,
                 item_id: str, item_name: str, item_type: str, item_url_name: str, thumb: str,
                 sub_types: str = None, mod_rank: str = None) -> None:
        self.database: MarketDatabase = database
        self.item_id: str = item_id
        self.item_name: str = item_name
        self.item_type: str = item_type
        self.item_url_name: str = item_url_name
        self.thumb: str = thumb
        self.thumb_url: str = f"{MarketItem.asset_url}/{self.thumb}"
        self.item_url: str = f"{MarketItem.base_url}/{self.item_url_name}"
        self.sub_types: List[str] = sub_types.split(",") if sub_types is not None and sub_types else []
        self.mod_rank: List[str] = mod_rank.split(",") if mod_rank is not None and mod_rank else []
        self.orders: Dict[str, List[Dict[str, Union[str, int]]]] = {'buy': [], 'sell': []}
        self.parts: List[MarketItem] = []

    def embed(self) -> discord.Embed:
        embed = discord.Embed(title=self.item_name, url=self.item_url, color=discord.Color.dark_gold())
        embed.set_thumbnail(url=self.thumb_url)
        return embed

    def parse_orders(self, orders: List[Dict[str, Any]]) -> None:
        for order in orders:
            order_type = order['order_type']
            user = order['user']
            parsed_order = {
                'last_update': order['last_update'],
                'quantity': order['quantity'],
                'price': order['platinum'],
                'user': user['ingame_name'],
                'state': user['status']
            }
            self.orders[order_type].append(parsed_order)

        for key, reverse in [('sell', False), ('buy', True)]:
            self.orders[key].sort(key=lambda x: (x['price'], x['last_update']), reverse=reverse)

    def get_parts(self) -> bool:
        if 'Set' in self.item_name:
            self.parts = [MarketItem(self.database, *item) for item in self.database.get_item_parts(self.item_id)]
            return True
        return False

    async def get_orders(self, order_type: str = 'sell', only_online: bool = True) -> List[Dict[str, Union[str, int]]]:
        orders = await fetch_wfm_data(f"{self.base_api_url}/items/{self.item_url_name}/orders")

        self.parse_orders(orders['payload']['orders'])

        if only_online:
            self.orders[order_type] = list(filter(lambda x: x['state'] == 'ingame', self.orders[order_type]))

        return self.orders[order_type]

    async def get_order_embed(self) -> discord.Embed:
        num_orders = 5

        orders = await self.get_orders()

        orders = orders[:num_orders]

        user_string = '\n'.join([format_user(order['user']) for order in orders])
        quantity_string = '\n'.join([f"{order['quantity']}" for order in orders])
        price_string = '\n'.join([f"{order['price']}" for order in orders])

        embed = self.embed()

        embed.add_field(name='Period | Volume | Daily Average', value=self.get_volume(), inline=False)
        embed.add_field(name="User", value=user_string, inline=True)
        embed.add_field(name="Price", value=price_string, inline=True)
        embed.add_field(name="Quantity", value=quantity_string, inline=True)

        return embed

    def get_volume(self) -> str:
        volume = [x[0] for x in self.database.get_item_volume(self.item_id, 31)]
        day_total, week_total, month_total = get_sums(volume)
        return format_volume(day_total, week_total, month_total)

    def __str__(self) -> str:
        return f"{self.item_name} ({self.item_url_name})"

    def __repr__(self) -> str:
        return f"{self.item_name} ({self.item_url_name})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, MarketItem):
            return self.item_id == other.item_id
        else:
            return False

    def __hash__(self) -> int:
        return hash(self.item_id)

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, MarketItem):
            return self.item_id < other.item_id
        else:
            return False

    def __le__(self, other: Any) -> bool:
        if isinstance(other, MarketItem):
            return self.item_id <= other.item_id
        else:
            return False

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, MarketItem):
            return self.item_id > other.item_id
        else:
            return False

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, MarketItem):
            return self.item_id >= other.item_id
        else:
            return False

    def __ne__(self, other: Any) -> bool:
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

        await self.bot.send_message(ctx, embed=wfm_item.embed())

    @commands.hybrid_command(name='marketvolume',
                             description="Gets volume for the requested item, if it exists.",
                             aliases=["getvolume", 'wfmvolume', 'gv'])
    async def get_market_volume(self, ctx: commands.Context, *, target_item: str) -> None:
        wfm_item = self.market_db.get_item(target_item)
        if wfm_item is None or wfm_item.item_url is None:
            await self.bot.send_message(ctx, f"Item {target_item} does not on Warframe.Market")
            return
        embed = wfm_item.embed()
        embed.description = "**Period | Volume | Daily Average**" + wfm_item.get_volume()

        await self.bot.send_message(ctx, embed=embed)

    @commands.hybrid_command(name='marketorders',
                             description="Gets orders for the requested item, if it exists.",
                             aliases=["getorders", 'wfmorders', 'wfmo', 'go'])
    async def get_market_orders(self, ctx: commands.Context, *, target_item: str) -> None:
        num_orders = 5

        wfm_item = self.market_db.get_item(target_item)
        if wfm_item is None or wfm_item.item_url is None:
            await self.bot.send_message(ctx, f"Item {target_item} does not on Warframe.Market")
            return

        embed = await wfm_item.get_order_embed()

        await self.bot.send_message(ctx, embed=embed)

    @commands.hybrid_command(name='partprices',
                             description="Gets prices for the requested part, if it exists.",
                             aliases=["partprice", "pp", "partp"])
    async def get_part_prices(self, ctx: commands.Context, *, target_part: str) -> None:
        wfm_item = self.market_db.get_item(target_part)
        if wfm_item is None or wfm_item.item_url is None:
            await self.bot.send_message(ctx, f"Item {target_part} does not on Warframe.Market")
            return

        if not wfm_item.get_parts():
            await self.bot.send_message(ctx, f"Item {target_part} does not have any parts.")
            return

        print(wfm_item.parts)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Market")


async def setup(bot):
    await bot.add_cog(Market(bot))
