from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from functools import wraps
from typing import List, Optional, Tuple, Union, Dict, Any

import aiohttp
import discord
import pymysql as pymysql
import redis
import relic_engine
from aiohttp import TCPConnector, ClientTimeout
from aiolimiter import AsyncLimiter
from discord import ButtonStyle
from discord.ext import commands
from discord.ext.commands import Cog
from discord.utils import escape_markdown
from fuzzywuzzy import fuzz
from pymysql import Connection

logger = logging.getLogger('bot')
rate_limiter = AsyncLimiter(3, 1)  # 3 requests per 1 second


@asynccontextmanager
async def cache_manager():
    cache = redis.Redis(host='localhost', port=6379, db=0)
    yield cache


@asynccontextmanager
async def session_manager():
    connector = TCPConnector(limit=10)
    headers = {"Connection": "keep-alive", "Upgrade-Insecure-Requests": "1"}
    timeout = ClientTimeout(total=5, connect=2, sock_connect=2, sock_read=2)
    session = aiohttp.ClientSession(connector=connector, headers=headers, timeout=timeout)
    yield session


class MarketItemView(discord.ui.View):
    def __init__(self, item: MarketItem):
        self.item = item
        self.item.get_parts()
        self.order_type = "sell"
        self.message = None
        super().__init__()
        if not self.item.get_parts():
            self.part_prices.disabled = True

        self.remove_item(self.orders_button)
        if self.order_type == "sell":
            self.remove_item(self.sell_orders)
        elif self.order_type == "buy":
            self.remove_item(self.buy_orders)

    def get_order_type_button(self):
        if self.order_type == "sell":
            return self.buy_orders
        elif self.order_type == "buy":
            return self.sell_orders

    @discord.ui.button(
        label="Part Prices",
        style=ButtonStyle.green,
        custom_id=f"part_price"
    )
    async def part_prices(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=False)

        embed = await self.item.get_part_prices(self.order_type)
        self.clear_items()
        self.add_item(self.orders_button)
        self.add_item(self.get_order_type_button())
        await self.message.edit(embed=embed, view=self)

    async def order_type_logic(self):
        embed = None
        if self.orders_button in self.children:
            embed = await self.item.get_part_prices(self.order_type)
        elif self.part_prices in self.children:
            embed = await self.item.get_order_embed(self.order_type)

        return embed

    @discord.ui.button(
        label="Orders",
        style=ButtonStyle.green,
        custom_id=f"get_orders"
    )
    async def orders_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=False)

        embed = await self.item.get_order_embed(self.order_type)
        self.clear_items()
        self.add_item(self.part_prices)
        self.add_item(self.get_order_type_button())
        await self.message.edit(embed=embed, view=self)

    @discord.ui.button(
        label="Buy Orders",
        style=ButtonStyle.green,
        custom_id=f"buy_orders"
    )
    async def buy_orders(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=False)

        self.order_type = "buy"
        embed = await self.order_type_logic()

        self.remove_item(self.buy_orders)
        self.add_item(self.sell_orders)
        await self.message.edit(embed=embed, view=self)

    @discord.ui.button(
        label="Sell Orders",
        style=ButtonStyle.green,
        custom_id=f"sell_orders"
    )
    async def sell_orders(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=False)

        self.order_type = "sell"
        embed = await self.order_type_logic()

        self.remove_item(self.sell_orders)
        self.add_item(self.buy_orders)
        await self.message.edit(embed=embed, view=self)


async def fetch_wfm_data(url: str):
    async with cache_manager() as cache:
        data = cache.get(url)
        if data is not None:
            logger.debug(f"Using cached data for {url}")
            return json.loads(data)

    retries = 3
    async with session_manager() as session:
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


def require_orders():
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            await self.get_orders()
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


def require_all_part_orders():
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            tasks = [item.get_orders() for item in self.parts]
            await asyncio.gather(*tasks)
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


def get_emoji(rarities):
    rarity_descriptions = {
        frozenset([1]): "<:common:1099015121516367934>",
        frozenset([2]): "<:uncommon:1099015120111292428>",
        frozenset([3]): "<:rare:1099015118718779472>",
        frozenset([1, 2]): "<:commonuncommon:1099015114860019723>",
        frozenset([1, 3]): "<:commonrare:1099015117548564610>",
        frozenset([2, 3]): "<:uncommonrare:1099015116139282482>",
        frozenset([1, 2, 3]): "<:commonuncommonrare:1099019241002389606>"
    }

    description = rarity_descriptions.get(frozenset(rarities))
    return description


def get_rarities(part):
    rarities = set()
    for relic in relic_engine.get_relic_dict().values():
        if part in relic:
            rarities.add(relic[part])

    return rarities


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
        self.sub_types: List[str] = [x[1] for x in sub_types] if sub_types is not None and sub_types else []
        self.mod_rank: List[str] = [x[1] for x in mod_rank] if mod_rank is not None and mod_rank else []
        self.orders: Dict[str, List[Dict[str, Union[str, int]]]] = {'buy': [], 'sell': []}
        self.parts: List[MarketItem] = []

    def embed(self) -> discord.Embed:
        embed = discord.Embed(title=self.item_name, url=self.item_url, color=discord.Color.dark_gold())
        embed.set_thumbnail(url=self.thumb_url)
        embed.add_field(name='Period | Volume | Daily Average', value=self.get_volume(), inline=False)

        return embed

    def filter_orders(self, order_type: str = 'sell', num_orders: int = 5, only_online: bool = True) \
            -> List[Dict[str, Union[str, int]]]:
        orders = self.orders[order_type]

        if only_online:
            orders = list(filter(lambda x: x['state'] == 'ingame', orders))

        return orders[:num_orders]

    def get_order_embed_fields(self, order_type: str = 'sell',
                               num_orders: int = 5) -> \
            tuple[tuple[str, str], tuple[str, str], tuple[str, str]]:
        orders = self.filter_orders(order_type=order_type, num_orders=num_orders)

        user_string = '\n'.join([format_user(order['user']) for order in orders])
        quantity_string = '\n'.join([f"{order['quantity']}" for order in orders])
        price_string = '\n'.join([f"{order['price']}" for order in orders])

        return ("User", user_string), ("Price", price_string), ("Quantity", quantity_string)

    @require_orders()
    async def get_order_embed(self, order_type: str = "sell", num_orders: int = 5) -> discord.Embed:
        num_orders = 5

        embed = self.embed()

        for field in self.get_order_embed_fields(order_type=order_type, num_orders=num_orders):
            embed.add_field(name=field[0], value=field[1], inline=True)

        return embed

    def format_part_name(self, part_name: str, emoji: str) -> str:
        set_name = self.item_name.replace('Set', '').strip()
        return f"{emoji} {part_name.replace(set_name, '').strip()}"

    def get_part_price_embed_fields(self, order_type):
        part_price = 0
        name_string = ""
        price_string = ""
        required_string = ""
        for part in self.parts:
            emoji = get_emoji(get_rarities(part.item_name))
            orders = part.filter_orders(order_type)
            required = relic_engine.get_required_amount(part.item_name)
            name_string += f"{self.format_part_name(part.item_name, emoji)}\n"
            price_string += f"{orders[0]['price']}\n"
            part_price += (orders[0]['price'] * required)
            required_string += f"{relic_engine.get_required_amount(part.item_name)}\n"

        orders = self.filter_orders(order_type)

        name_string += f"Set Price\n"
        price_string += f"{orders[0]['price']}\n"

        name_string += f"Part Price\n"
        price_string += f"{part_price}\n"

        return ("Part", name_string), ("Price", price_string), ("Required", required_string)

    @require_orders()
    @require_all_part_orders()
    async def get_part_prices(self, order_type: str = 'sell'):
        embed = self.embed()

        for field in self.get_part_price_embed_fields(order_type):
            embed.add_field(name=field[0], value=field[1], inline=True)

        return embed

    def parse_orders(self, orders: List[Dict[str, Any]]) -> None:
        self.orders: Dict[str, List[Dict[str, Union[str, int]]]] = {'buy': [], 'sell': []}
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

    async def get_orders(self) -> None:
        orders = await fetch_wfm_data(f"{self.base_api_url}/items/{self.item_url_name}/orders")
        if orders is None:
            return

        self.parse_orders(orders['payload']['orders'])

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

        embed = wfm_item.embed()
        embed.description = "**Period | Volume | Daily Average**" + wfm_item.get_volume()

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
        wfm_item = self.market_db.get_item(target_item)
        if wfm_item is None or wfm_item.item_url is None:
            await self.bot.send_message(ctx, f"Item {target_item} does not on Warframe.Market")
            return

        view = MarketItemView(wfm_item)

        embed = await wfm_item.get_order_embed()

        message = await self.bot.send_message(ctx, embed=embed, view=view)

        view.message = message

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

        embed = await wfm_item.get_part_prices()

        await self.bot.send_message(ctx, embed=embed)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Market")


async def setup(bot):
    await bot.add_cog(Market(bot))
