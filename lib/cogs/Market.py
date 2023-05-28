from __future__ import annotations

from copy import copy
from time import perf_counter

import discord
import relic_engine
from discord import ButtonStyle
from discord.ext import commands
from discord.ext.commands import Cog
from market_engine.modules.MarketData import MarketItem
from pymysql import OperationalError

from market_engine.modules import MarketData


class SubtypeSelectMenu(discord.ui.Select):
    def __init__(self, market_item_view: MarketItemView, subtypes):
        options = []
        for subtype in subtypes:
            options.append(discord.SelectOption(label=subtype.title(), value=subtype))
        self.market_item_view = market_item_view

        super().__init__(placeholder="Select a subtype", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.market_item_view.subtype_handler(interaction, self.values[0])


class MarketItemView(discord.ui.View):
    def __init__(self, item: MarketItem, database: MarketData.MarketDatabase, bot: commands.Bot):
        self.item = item
        self.database = database
        self.bot = bot
        self.message = None
        self.order_type = 'sell'
        self.base_embed = None

        super().__init__()
        if len(self.item.parts) == 0:
            self.remove_item(self.part_prices)

        self.remove_item(self.orders_button)
        if self.order_type == "sell":
            self.remove_item(self.sell_orders)
        elif self.order_type == "buy":
            self.remove_item(self.buy_orders)

        self.subtype = None
        if subtypes := self.get_subtypes():
            self.subtype_menu = SubtypeSelectMenu(self, subtypes)
            self.add_item(self.subtype_menu)

    def get_subtypes(self):
        subtypes = []
        for order in self.item.orders[self.order_type]:
            if 'subtype' in order and order['subtype'] not in subtypes and order['state'] == 'ingame':
                subtypes.append(order['subtype'])

        return subtypes

    def get_order_type_button(self):
        if self.order_type == "sell":
            return self.buy_orders
        elif self.order_type == "buy":
            return self.sell_orders

    async def order_change_handler(self, interaction):
        await interaction.response.defer(thinking=False)

        embed = await self.get_embed_handler()

        if self.part_prices in self.children:
            orders = True
        else:
            orders = False

        self.clear_items()
        if orders:
            self.add_item(self.orders_button)
        else:
            self.add_item(self.part_prices)

        self.add_item(self.get_order_type_button())

        await self.message.edit(embed=embed, view=self)

    @discord.ui.button(
        label="Part Prices",
        style=ButtonStyle.green,
        custom_id=f"part_price"
    )
    async def part_prices(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.order_change_handler(interaction)

    async def get_embed_handler(self):
        if self.part_prices in self.children:
            embed = await self.get_part_prices(self.order_type)
        else:
            embed = await self.get_order_embed(self.order_type)

        return embed

    @discord.ui.button(
        label="Orders",
        style=ButtonStyle.green,
        custom_id=f"get_orders"
    )
    async def orders_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.order_change_handler(interaction)

    @discord.ui.button(
        label="Buy Orders",
        style=ButtonStyle.green,
        custom_id=f"buy_orders"
    )
    async def buy_orders(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=False)

        self.order_type = "buy"
        embed = await self.get_embed_handler()

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
        embed = await self.get_embed_handler()

        self.remove_item(self.sell_orders)
        self.add_item(self.buy_orders)
        await self.message.edit(embed=embed, view=self)

    async def subtype_handler(self, interaction, subtype):
        await interaction.response.defer(thinking=False)

        self.subtype = subtype
        embed = await self.get_embed_handler()

        await self.message.edit(embed=embed, view=self)

    @staticmethod
    def get_rarities(part):
        rarities = set()
        for relic in relic_engine.get_relic_dict().values():
            if part in relic:
                rarities.add(relic[part])

        return rarities

    @staticmethod
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

    def format_part_name(self, part_name: str, emoji: str) -> str:
        set_name = self.item.item_name.replace('Set', '').strip()
        return f"{emoji} {part_name.replace(set_name, '').strip()}"

    def get_part_price_embed_fields(self, order_type):
        part_price = 0
        name_string = ""
        price_string = ""
        required_string = ""
        for part in self.item.parts:
            emoji = self.get_emoji(self.get_rarities(part.item_name))
            orders = self.filter_orders(part, 1)
            required = relic_engine.get_required_amount(part.item_name)
            name_string += f"{self.format_part_name(part.item_name, emoji)}\n"
            price_string += f"{orders[0]['price']}\n"
            part_price += (orders[0]['price'] * required)
            required_string += f"{relic_engine.get_required_amount(part.item_name)}\n"

        orders = self.filter_orders(self.item, 1)

        name_string += f"Set Price\n"
        price_string += f"{orders[0]['price']}\n"

        name_string += f"Part Price\n"
        price_string += f"{part_price}\n"

        return ("Part", name_string), ("Price", price_string), ("Required", required_string)

    async def get_part_prices(self, order_type: str = 'sell'):
        embed = self.embed()

        for field in self.get_part_price_embed_fields(order_type):
            embed.add_field(name=field[0], value=field[1], inline=True)

        return embed

    @staticmethod
    def format_row(label, value, average=None):
        if average is not None:
            return f"{label:<7} {value:<7} {average:<4}\n"
        else:
            return f"{label:<7} {value:<7}\n"

    def format_volume(self, day: int, week: int, month: int) -> str:
        return f'```python\n' \
               f'{self.format_row("Day:", day)}' \
               f'{self.format_row("Week:", week, week // 7)}' \
               f'{self.format_row("Month:", month, month // 31)}```'

    @staticmethod
    def get_sums(volume: list) -> tuple:
        day_total = sum(volume[-1:])
        week_total = sum(volume[-7:])
        month_total = sum(volume)
        return day_total, week_total, month_total

    def get_volume(self) -> str:
        volume = [x[0] for x in self.database.get_item_volume(self.item.item_id, 31)]
        day_total, week_total, month_total = self.get_sums(volume)
        return self.format_volume(day_total, week_total, month_total)

    def embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"{self.item.item_name}"
                                    f"{f' - {self.subtype.title()}' if self.subtype is not None else ''}",
                              url=self.item.item_url, color=discord.Color.dark_gold())
        embed.set_thumbnail(url=self.item.thumb_url)
        embed.add_field(name='Period | Volume | Daily Average', value=self.get_volume(), inline=False)

        return embed

    @staticmethod
    def format_user(user) -> str:
        return f"[{user}]({f'https://warframe.market/profile/{user}'})"

    def filter_orders(self, item, num_orders):
        filters, mode = self.item.create_filters(state='ingame', state_mode='whitelist')
        if self.subtype is not None:
            filters_subtype, mode_subtype = self.item.create_filters(subtype=self.subtype, subtype_mode='whitelist')
            filters.update(filters_subtype)
            mode.update(mode_subtype)

        orders = item.filter_orders(order_type=self.order_type,
                                    num_orders=num_orders,
                                    filters=filters,
                                    mode=mode)

        return orders

    def get_order_embed_fields(self, num_orders: int = 5) -> \
            tuple[tuple[str, str], tuple[str, str], tuple[str, str]]:
        orders = self.filter_orders(self.item, num_orders)

        user_string = '\n'.join([self.format_user(order['user']) for order in orders])
        quantity_string = '\n'.join([f"{order['quantity']}" for order in orders])
        price_string = '\n'.join([f"{order['price']}" for order in orders])

        return ("User", user_string), ("Price", price_string), ("Quantity", quantity_string)

    async def get_order_embed(self, order_type: str = "sell", num_orders: int = 5,
                              subtype: str = None) -> discord.Embed:
        num_orders = 5

        embed = self.embed()

        for field in self.get_order_embed_fields(num_orders=num_orders):
            embed.add_field(name=field[0], value=field[1], inline=True)

        return embed


class Market(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.base_api_url = "https://api.warframe.market/v1"
        self.base_url = "https://warframe.market"
        try:
            self.market_db = MarketData.MarketDatabase(user=self.bot.bot_config['db_user'],
                                                       password=self.bot.bot_config['db_password'],
                                                       host=self.bot.bot_config['db_host'],
                                                       database='market')
        except OperationalError:
            self.market_db = None
            self.bot.logger.error("Could not connect to database. Market cog will not be loaded.")

    async def item_embed_handler(self, target_item: str, ctx: commands.Context,
                                 embed_type: str) -> None:
        wfm_item = await self.market_db.get_item(target_item)
        if wfm_item is None or wfm_item.item_url is None:
            await self.bot.send_message(ctx, f"Item {target_item} does not on Warframe.Market")
            return

        view = MarketItemView(wfm_item, self.market_db, self.bot)

        if embed_type == 'order':
            embed = await view.get_order_embed()
        elif embed_type == 'part_price':
            embed = await view.get_part_prices()
        else:
            self.bot.logger.error(f"Invalid embed type {embed_type} passed to item_embed_handler")
            return

        message = await self.bot.send_message(ctx, embed=embed, view=view)

        view.message = message

    @commands.hybrid_command(name='marketorders',
                             description="Gets orders for the requested item, if it exists.",
                             aliases=["getorders", 'wfmorders', 'wfmo', 'go'])
    async def get_market_orders(self, ctx: commands.Context, *, target_item: str) -> None:
        await self.item_embed_handler(target_item, ctx, 'order')

    @commands.hybrid_command(name='partprices',
                             description="Gets prices for the requested part, if it exists.",
                             aliases=["partprice", "pp", "partp"])
    async def get_part_prices(self, ctx: commands.Context, *, target_part: str) -> None:
        await self.item_embed_handler(target_part, ctx, 'part_price')

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Market")


async def setup(bot):
    await bot.add_cog(Market(bot))
