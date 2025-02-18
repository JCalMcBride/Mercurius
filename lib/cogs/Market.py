from __future__ import annotations

import asyncio
from typing import Tuple, List, Dict, Any, Union

import aiohttp
import discord
import pycountry as pycountry
import relic_engine
from bs4 import BeautifulSoup
from dateutil.parser import parse
from discord import ButtonStyle, app_commands
from discord.app_commands import Choice
from discord.ext import commands, tasks
from discord.ext.commands import Cog
from market_engine.Models.MarketDatabase import MarketDatabase
from market_engine.Models.MarketItem import MarketItem
from market_engine.Models.MarketUser import MarketUser
from pymysql import IntegrityError


class FavoritesView(discord.ui.View):
    def __init__(self, ctx: commands.Context, favorite_items: List[Dict[str, Union[str, int, bool]]],
                 market_cog: Market):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.favorite_items = favorite_items
        self.market_cog = market_cog
        self.current_page = 0
        self.embeds = []

        self.refresh_button = discord.ui.Button(label="Refresh", style=discord.ButtonStyle.green)
        self.refresh_button.callback = self.refresh_callback
        self.add_item(self.refresh_button)

        if len(self.favorite_items) > 10:
            self.next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.blurple)
            self.next_button.callback = self.next_callback
            self.add_item(self.next_button)

            self.previous_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.blurple, disabled=True)
            self.previous_button.callback = self.previous_callback
            self.add_item(self.previous_button)

    async def create_favorite_embed(self, item: Dict[str, Union[str, int, bool]]) -> discord.Embed | None:
        item_id = item["item_id"]

        # Fetch the item from the market database
        wfm_item: MarketItem = await self.market_cog.bot.market_db.get_item(item_id,
                                                                            fetch_parts=False,
                                                                            fetch_orders=True,
                                                                            fetch_part_orders=False,
                                                                            fetch_price_history=False,
                                                                            fetch_demand_history=False)

        if wfm_item is None:
            return None

        # Get the average price from the market database
        average_price = int(self.market_cog.bot.market_db.get_item_price(wfm_item.item_name))

        # Get the first two orders from in-game users
        filters, mode = wfm_item.create_filters(state='ingame', state_mode='whitelist')

        orders = wfm_item.filter_orders(order_type='sell',
                                        num_orders=2,
                                        filters=filters,
                                        mode=mode)

        # Format the orders
        order_text = "\n".join(
            f"[{order['user']}](https://warframe.market/profile/{order['user']}): {order['price']}" for order in orders)

        # Create the embed
        embed = discord.Embed(color=discord.Color.dark_gold(),
                              description=f"{order_text}")
        embed.set_author(name=f"{wfm_item.item_name} - {average_price}", url=wfm_item.item_url,
                         icon_url=wfm_item.thumb_url)

        return embed, average_price

    async def create_embeds(self):
        self.embeds = []
        for item in self.favorite_items:
            embed_data = await self.create_favorite_embed(item)
            if embed_data is not None:
                embed, average_price = embed_data
                self.embeds.append((embed, average_price))

        # Sort the embeds by the item's average price in descending order
        self.embeds.sort(key=lambda x: x[1], reverse=True)

    def get_page_embeds(self):
        start = self.current_page * 10
        end = min(start + 10, len(self.embeds))
        return [embed for embed, _ in self.embeds[start:end]]

    async def update_message(self, interaction: discord.Interaction):
        page_embeds = self.get_page_embeds()
        if page_embeds:
            if len(self.favorite_items) > 10:
                self.next_button.disabled = self.current_page == len(self.embeds) // 10
                self.previous_button.disabled = self.current_page == 0
            await interaction.response.edit_message(embeds=page_embeds, view=self)
        else:
            await interaction.response.edit_message(content="No favorites found.", embed=None, view=None)

    async def refresh_callback(self, interaction: discord.Interaction):
        start = self.current_page * 10
        end = min(start + 10, len(self.favorite_items))
        for i, item in enumerate(self.favorite_items[start:end]):
            embed_data = await self.create_favorite_embed(item)
            if embed_data is not None:
                embed, average_price = embed_data
                self.embeds[start+i] = (embed, average_price)

        self.embeds.sort(key=lambda x: x[1], reverse=True)

        await self.update_message(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        if self.current_page < len(self.embeds) // 10:
            self.current_page += 1
            await self.update_message(interaction)

    async def previous_callback(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You can't use this button.", ephemeral=True)
            return False
        return True


class SubtypeSelectMenu(discord.ui.Select):
    def __init__(self, market_item_view: MarketItemView, subtypes):
        options = []
        subtypes.sort()
        for subtype in subtypes:
            options.append(discord.SelectOption(label=subtype.title(), value=subtype))
        self.market_item_view = market_item_view

        super().__init__(placeholder="Select a subtype", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.market_item_view.subtype_handler(interaction, self.values[0])


class MarketItemView(discord.ui.View):
    def __init__(self, item: MarketItem, database: MarketDatabase, bot: commands.Bot,
                 user: discord.User, order_type: str = 'sell', subtype: str = None, platform: str = 'pc'):
        self.item = item
        self.database = database
        self.bot = bot
        self.message = None
        self.order_type = order_type
        self.base_embed = None
        self.user = user

        super().__init__()
        if len(self.item.parts) == 0:
            self.remove_item(self.part_prices)

        self.remove_item(self.orders_button)
        if self.order_type == "sell":
            self.remove_item(self.sell_orders)
        elif self.order_type == "buy":
            self.remove_item(self.buy_orders)

        self.subtype = subtype
        if subtypes := self.item.get_subtypes():
            self.subtype_menu = SubtypeSelectMenu(self, subtypes)
            self.add_item(self.subtype_menu)

        self.platform = platform

    def get_order_type_button(self):
        if self.order_type == "sell":
            return self.buy_orders
        elif self.order_type == "buy":
            return self.sell_orders

    async def user_check(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("Only the user who requested this can use this button",
                                                    ephemeral=True)
            return False
        return True

    def update_buttons(self):
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

    async def order_change_handler(self, interaction):
        await interaction.response.defer(thinking=False)

        self.update_buttons()

        embed = await self.get_embed_handler()

        await self.message.edit(embed=embed, view=self)

    @discord.ui.button(
        label="Part Prices",
        style=ButtonStyle.green,
        custom_id=f"part_price"
    )
    async def part_prices(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.user_check(interaction):
            return

        if not self.item.part_orders_fetched:
            tasks = self.item.get_part_orders_tasks()
            await asyncio.gather(*tasks)

        await self.order_change_handler(interaction)

    async def get_embed_handler(self):
        if self.orders_button in self.children:
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
        if not await self.user_check(interaction):
            return

        await self.order_change_handler(interaction)

    @discord.ui.button(
        label="Buy Orders",
        style=ButtonStyle.green,
        custom_id=f"buy_orders"
    )
    async def buy_orders(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.user_check(interaction):
            return

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
        if not await self.user_check(interaction):
            return

        await interaction.response.defer(thinking=False)

        self.order_type = "sell"
        embed = await self.get_embed_handler()

        self.remove_item(self.sell_orders)
        self.add_item(self.buy_orders)
        await self.message.edit(embed=embed, view=self)

    async def subtype_handler(self, interaction, subtype):
        if not await self.user_check(interaction):
            return

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
            frozenset([1]): "<:common:1258881648879992982>",
            frozenset([2]): "<:uncommon:1258881644278841404>",
            frozenset([3]): "<:rare:1258881645495455804>",
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

            if orders:
                price_string += f"{orders[0]['price']}\n"
                part_price += (orders[0]['price'] * required)
            else:
                price_string += "N/A\n"

            name_string += f"{self.format_part_name(part.item_name, emoji)}\n"
            required_string += f"{relic_engine.get_required_amount(part.item_name)}\n"

        orders = self.filter_orders(self.item, 1)

        name_string += f"Set Price\n"
        price_string += f"{orders[0]['price']}\n"

        name_string += f"Part Price\n"
        price_string += f"{part_price}\n"

        return ("Part", name_string), ("Price", price_string), ("Required", required_string)

    async def get_part_prices(self, order_type: str = 'sell'):
        embed = await self.embed()

        fields = self.get_part_price_embed_fields(order_type)
        for i, field in enumerate(fields):
            embed.insert_field_at(i, name=field[0], value=field[1], inline=True)

        return embed

    @staticmethod
    def format_row(label, value, average=None):
        if average is not None:
            return f"{label:<7} {value:<7} {average:<4}\n"
        else:
            return f"{label:<7} {value:<7}\n"

    def format_volume(self, day: int, week: int, month: int) -> Tuple[list, list, list]:
        return ["Day", "Week", "Month"], [str(day), str(week), str(month)], ["​", str(week // 7), str(month // 31)]

    @staticmethod
    def get_sums(volume: list) -> tuple:
        day_total = sum(volume[-1:])
        week_total = sum(volume[-7:])
        month_total = sum(volume)
        return day_total, week_total, month_total

    async def get_volume(self) -> Tuple[list, list, list]:
        volume = [x[0] for x in self.database.get_item_volume(self.item.item_id, 31, self.platform)]

        day_total, week_total, month_total = self.get_sums(volume)
        return self.format_volume(day_total, week_total, month_total)

    async def embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"{self.item.item_name} ({self.platform.upper()})"
                                    f"{f' - {self.subtype.title()}' if self.subtype is not None else ''}",
                              url=self.item.item_url, color=discord.Color.dark_gold())
        embed.set_thumbnail(url=self.item.thumb_url)

        period, volume, daily_average = await self.get_volume()

        embed.add_field(name='Period', value='\n' + '\n'.join(period) + '', inline=True)
        embed.add_field(name='Volume', value='\n' + '\n'.join(volume) + '', inline=True)
        embed.add_field(name='Daily Average', value='\n' + '\n'.join(daily_average) + '', inline=True)

        return embed

    @staticmethod
    def format_user(user) -> str:
        max_length = 10
        user_url_string = user.replace(' ', '%20')
        return f"[{user[:max_length] + '..' if len(user) > max_length else user}]" \
               f"({f'https://warframe.market/profile/{user_url_string}'})"

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
        quantity_string = '\n'.join(
            [f"{order['quantity']} {order['subtype'] if 'subtype' in order else ''}" for order in orders])
        price_string = '\n'.join([f"{order['price']}" for order in orders])

        return ("User", user_string), ("Price", price_string), ("Quantity", quantity_string)

    async def get_order_embed(self, order_type: str = "sell", num_orders: int = 5,
                              subtype: str = None) -> discord.Embed:
        num_orders = 5

        embed = await self.embed()

        fields = self.get_order_embed_fields(num_orders=num_orders)
        for i, field in enumerate(fields):
            embed.insert_field_at(i, name=field[0], value=field[1], inline=True)

        return embed


def get_language_name(locale_code):
    # Split the locale code by hyphen and take the first part
    lang_code = locale_code.split('-')[0]

    language = pycountry.languages.get(alpha_2=lang_code)
    if language is None:
        raise ValueError(f'Unknown language code: {lang_code}')

    return language.name


def get_discord_timestamp(wfm_timestamp):
    # Parse the date and time string
    date_time = parse(wfm_timestamp)

    return f"<t:{int(date_time.timestamp())}:R>"


class MarketUserView(discord.ui.View):
    def __init__(self, user: MarketUser, database: MarketDatabase, bot: commands.Bot):
        super().__init__()
        self.user = user
        self.database = database
        self.bot = bot
        self.message = None

    def embed(self) -> discord.Embed:
        soup = BeautifulSoup(self.user.about, 'html.parser')

        embed = discord.Embed(title=f"{self.user.username}",
                              url=self.user.profile_url, color=discord.Color.dark_gold(),
                              description=soup.get_text())
        embed.set_thumbnail(url=self.user.avatar_url)

        fields = [
            ("Reputation", self.user.reputation, True),
            ("Last Seen", get_discord_timestamp(self.user.last_seen), True),
            ("Locale", get_language_name(self.user.locale), True)
        ]

        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

        return embed

    async def get_review_embed(self):
        embed = self.embed()

        if self.user.reviews is None or len(self.user.reviews) == 0:
            return embed

        reviews = [f"{get_discord_timestamp(x['date'])} **{x['user']}**: {x['text'] if x['text'] else 'N/A'}"
                   for x in self.user.reviews][:5]

        embed.add_field(name='Reviews', value='\n'.join(reviews), inline=False)

        return embed

    @staticmethod
    def format_item(item, url_name) -> str:
        return f"[{item}]({f'https://warframe.market/items/{url_name}'})"

    async def get_order_embed(self, order_type: str = 'sell'):
        embed = self.embed()

        if self.user.orders is None or len(self.user.orders[order_type]) == 0:
            return embed

        orders = [[self.format_item(x['item'], x['item_url_name']), x['quantity'], x['price']] for x in
                  self.user.orders[order_type]][:5]

        embed.add_field(name='Item', value='\n'.join([x[0] for x in orders]), inline=True)
        embed.add_field(name='Price', value='\n'.join([str(x[2]) for x in orders]), inline=True)
        embed.add_field(name='Quantity', value='\n'.join([str(x[1]) for x in orders]), inline=True)

        return embed


def get_alias_used_and_message(message, prefix):
    split_message = message[len(prefix):].split(' ', maxsplit=1)

    alias_used = split_message[0].lower()
    clean_message = split_message[1] if len(split_message) > 1 else None

    return alias_used, clean_message


class Market(Cog, name="market"):
    def __init__(self, bot):
        self.bot = bot
        self.base_api_url = "https://api.warframe.market/v1"
        self.base_url = "https://warframe.market"
        self.easter_eggs = {
            'go': {'go power rangers': 'https://www.youtube.com/watch?v=BwbHW8MeHDU',
                   'to bed': 'go to bed <@167596939460739072>',
                   'tobed': 'go to bed <@167596939460739072>'},
            'pp': {'big': '😳'}
        }

    @tasks.loop(minutes=1)
    async def update_usernames(self):
        self.bot.market_db.update_usernames()

    async def item_embed_handler(self, input_string: str, ctx: commands.Context,
                                 embed_type: str) -> None:
        fetch_part_orders = False
        if embed_type == 'part_price':
            fetch_part_orders = True

        platform = self.bot.database.get_platform(ctx.author.id)

        output_strings, output_items, subtypes, order_type = await self.bot.get_valid_items(
            input_string,
            fetch_part_orders=fetch_part_orders,
            fetch_orders=True,
            fetch_parts=True,
            platform=platform
        )

        for wfm_item, subtype, output_string in zip(output_items, subtypes, output_strings):
            view = MarketItemView(wfm_item, self.bot.market_db, self.bot,
                                  order_type=order_type, subtype=subtype, user=ctx.author, platform=platform)

            if embed_type == 'part_price' and len(wfm_item.parts) == 0:
                output_string = "Item has no parts, showing orders instead.\n" + output_string
                embed_type = 'order'

            if embed_type == 'order':
                embed = await view.get_order_embed()
            elif embed_type == 'part_price':
                embed = await view.get_part_prices()
                view.update_buttons()
            else:
                self.bot.logger.error(f"Invalid embed type {embed_type} passed to item_embed_handler")
                return

            message = await self.bot.send_message(ctx, content=output_string, embed=embed, view=view)

            view.message = message

    async def user_embed_handler(self, target_user: str, ctx: commands.Context,
                                 embed_type: str) -> None:
        fetch_reviews = False
        fetch_orders = False
        if embed_type == 'reviews':
            fetch_reviews = True

        if embed_type == 'orders':
            fetch_orders = True

        wfm_user = await self.bot.market_db.get_user(target_user,
                                                     fetch_reviews=fetch_reviews,
                                                     fetch_orders=fetch_orders)

        if wfm_user is None:
            await self.bot.send_message(ctx, f"User {target_user} does not exist on Warframe.Market")
            return

        view = MarketUserView(wfm_user, self.bot.market_db, self.bot)

        if embed_type == 'reviews':
            embed = await view.get_review_embed()
        elif embed_type == 'orders':
            embed = await view.get_order_embed()
        else:
            self.bot.logger.error(f"Invalid embed type {embed_type} passed to user_embed_handler")
            return

        message = await self.bot.send_message(ctx, embed=embed, view=view)

        view.message = message

    @commands.hybrid_command(name="userreviews",
                             description="Shows recent reviews for a given user on warframe.market.", aliases=["ur"])
    @app_commands.describe(target_user='User you want to get the reviews for.')
    async def get_user_reviews(self, ctx: commands.Context, target_user: str):
        """Shows recent reviews for a given user on warframe.market."""
        await self.user_embed_handler(target_user, ctx, 'reviews')

    @commands.hybrid_command(name="userorders",
                             description="Shows recent reviews for a given user on warframe.market.", aliases=["uo"])
    @app_commands.describe(target_user='User you want to get the reviews for.')
    async def get_user_orders(self, ctx: commands.Context, target_user: str):
        """Shows the first five orders for a given user on warframe.market."""
        await self.user_embed_handler(target_user, ctx, 'orders')

    def easter_egg_check(self, message, prefix):
        alias_used, clean_message = get_alias_used_and_message(message, prefix)
        if alias_used not in self.easter_eggs or clean_message not in self.easter_eggs[alias_used]:
            return False

        return self.easter_eggs[alias_used][clean_message]

    @commands.hybrid_command(name='marketorders',
                             description="Gets orders for the requested item, if it exists.",
                             aliases=["getorders", 'wfmorders', 'wfmo', 'go'])
    async def get_market_orders(self, ctx: commands.Context, *, target_item: str) -> None:
        """Gets orders for the requested item, if it exists."""
        if easter_egg := self.easter_egg_check(ctx.message.content, ctx.prefix):
            await ctx.send(easter_egg)
            return

        await self.item_embed_handler(target_item.lower(), ctx, 'order')

    @commands.hybrid_command(name='partprices',
                             description="Gets prices for the requested part, if it exists.",
                             aliases=["partprice", "pp", "partp"])
    async def get_part_prices(self, ctx: commands.Context, *, target_part: str) -> None:
        if easter_egg := self.easter_egg_check(ctx.message.content, ctx.prefix):
            await ctx.send(easter_egg)
            return

        await self.item_embed_handler(target_part.lower(), ctx, 'part_price')

    @commands.hybrid_command(name='highestprice', aliases=['itemsearch', 'isearch', 'searchitems'],
                             brief='Search for highest priced items of a specific type.')
    @app_commands.describe(item_type='The type of item to search for.',
                           min_price='The minimum price threshold (default: 0).',
                           max_price='The maximum price threshold (default: 1000000).')
    @app_commands.choices(item_type=[
        Choice(name=item_type, value=item_type) for item_type in [
            'ArcaneHelmets', 'Arcanes', 'ArmorPieces', 'Avionics', 'AyatanSculptures', 'CapturaScenes',
            'CollectorItems',
            'Emotes', 'Fish', 'FocusLens', 'Gems', 'Imprints', 'Misc', 'Mods', 'PrimeSentinelParts', 'PrimeSentinels',
            'PrimeWarframeParts', 'PrimeWarframes', 'PrimeWeaponParts', 'PrimeWeapons', 'Relics', 'SentinelParts',
            'WeaponParts', 'Weapons', 'All'
        ]
    ])
    async def highest_price(self, ctx,
                            item_type: str,
                            min_price: int = commands.parameter(default=0, description="The minimum price threshold."),
                            max_price: int = commands.parameter(default=1000000,
                                                                description="The maximum price threshold.")):
        """
        Search for highest priced items of a specific type within a given price range.

        Results are limited to 20 items and will be displayed in an embed with Item and Price fields.

        Usage examples:
        --highestprice Mods 10 100
        /highestprice item_type:PrimeWeapons min_price:50 max_price:500
        """
        params = {
            'min_price': min_price,
            'max_price': max_price,
            'sort_by': 'last_average_price',
            'sort_direction': 'desc',
            'items_per_page': 20,
            'return_type': 'price_info'
        }

        if item_type != "All":
            params['item_type_include'] = [item_type]

        async with aiohttp.ClientSession() as session:
            async with session.get('http://relics.run/items', params=params) as response:
                if response.status != 200:
                    await self.bot.send_message(ctx, f"Error retrieving data: HTTP {response.status}", ephemeral=True)
                    return

                data = await response.json()
                items = data['items']

                if not items:
                    await self.bot.send_message(ctx,
                                                f"No valid items found.",
                                                ephemeral=True)
                    return

                # Additional sort to ensure items are in correct order
                sorted_items = dict(sorted(items.items(), key=lambda x: x[1], reverse=True))

                embed = discord.Embed(title=f"Highest Priced {item_type}", color=discord.Color.blue())

                item_names = "\n".join([f"**{item_name}**" for item_name in sorted_items.keys()][:20])
                item_prices = "\n".join([f"{int(price)}" for price in sorted_items.values()][:20])

                embed.add_field(name="Item", value=item_names, inline=True)
                embed.add_field(name="Price", value=item_prices, inline=True)

                await self.bot.send_message(ctx, embed=embed)
    @commands.hybrid_command(name='addalias',
                             description="Adds an alias for an item.")
    @app_commands.describe(target_item='Item you want to add an alias for.')
    @app_commands.describe(alias='Alias you want to add.')
    @commands.has_any_role(780376440998199296,
                           780376480734904351,
                           780630958368882689,
                           1035644033843855490)
    async def add_alias(self, ctx: commands.Context, target_item: str, alias: str) -> None:
        """
        Adds an alias for an item.
        """
        wfm_item: MarketItem = await self.bot.market_db.get_item(target_item.lower(),
                                                                 fetch_parts=False,
                                                                 fetch_orders=False,
                                                                 fetch_part_orders=False,
                                                                 fetch_price_history=False,
                                                                 fetch_demand_history=False)

        if wfm_item is None:
            await self.bot.send_message(ctx, f"Item {target_item} does not exist on Warframe.Market",
                                        ephemeral=True)
            return

        if alias.lower() in wfm_item.aliases:
            await self.bot.send_message(ctx, f"Alias {alias} already exists for item {target_item}",
                                        ephemeral=True)
            return

        wfm_item.add_alias(alias.lower())
        await self.bot.send_message(ctx, f"Alias {alias} added for item {target_item}",
                                    ephemeral=True)

    @commands.hybrid_command(name='removealias',
                             description="Removes an alias for an item.")
    @app_commands.describe(target_item='Item you want to remove an alias for.')
    @app_commands.describe(alias='Alias you want to remove.')
    @commands.has_any_role(780376440998199296,
                           780376480734904351,
                           780630958368882689,
                           1035644033843855490)
    async def remove_alias(self, ctx: commands.Context, target_item: str, alias: str) -> None:
        """Removes an alias for an item."""
        wfm_item: MarketItem = await self.bot.market_db.get_item(target_item.lower(),
                                                                 fetch_parts=False,
                                                                 fetch_orders=False,
                                                                 fetch_part_orders=False,
                                                                 fetch_price_history=False,
                                                                 fetch_demand_history=False)

        if wfm_item is None:
            await self.bot.send_message(ctx, f"Item {target_item} does not exist on Warframe.Market",
                                                    ephemeral=True)
            return

        if alias.lower() not in wfm_item.aliases:
            await self.bot.send_message(ctx, f"Alias {alias} does not exist for item {target_item}",
                                                    ephemeral=True)
            return

        wfm_item.remove_alias(alias.lower())
        await self.bot.send_message(ctx, f"Alias {alias} removed from item {target_item}",
                                                ephemeral=True)

    @commands.hybrid_command(name='setplatform',
                             description="Sets your platform for market commands.",
                             aliases=["sp", "setp", "setplat"])
    async def set_user_platform(self, ctx: commands.Context, platform: str) -> None:
        """Sets your platform for market commands."""
        if platform.lower() not in ['pc', 'ps4', 'xbox', 'switch']:
            await ctx.send("Invalid platform. Valid platforms are: PC, PS4, Xbox, Switch")
            return

        self.bot.database.set_platform(ctx.author.id, platform.lower())
        await ctx.send(f"Platform set to {platform}")

    def create_item_settings_embed(self, item: MarketItem, item_settings: dict) -> discord.Embed:
        embed = discord.Embed(title=f"{item.item_name} Settings", url=item.item_url, color=discord.Color.dark_gold())
        embed.set_thumbnail(url=item.thumb_url)

        if item_settings["plat_notification_threshold"] is not None:
            embed.add_field(name="Platinum Notification Threshold", value=item_settings["plat_notification_threshold"])

        if item_settings["daily_messages"] is not None:
            embed.add_field(name="Daily Messages", value="Enabled" if item_settings["daily_messages"] else "Disabled")

        if item_settings["favorite"] is not None:
            embed.add_field(name="Favorite", value="Yes" if item_settings["favorite"] else "No")

        return embed

    @commands.hybrid_command(name='favorite',
                             description="Favorite an item for use in the favorites command.",
                             aliases=["fav", "fave", "favourite"])
    @app_commands.describe(item_name='Item name you wish to favorite.')
    async def set_item_settings(self, ctx: commands.Context, *, item_name: str) -> None:
        """Favorite an item for use in the favorites command."""
        if not self.bot.supporter_check(ctx):
            raise commands.CheckFailure()

        user_id = ctx.author.id

        # Check if the user exists in the users table
        user_exists = self.bot.database.user_exists(user_id)

        if not user_exists:
            # Create a new entry for the user in the users table
            self.bot.database.create_user(user_id)

        output_strings, output_items, _, _ = await self.bot.get_valid_items(
            item_name,
            fetch_orders=True,
        )

        for wfm_item in output_items:
            item_id = wfm_item.item_id

            # Update the item settings in the database
            try:
                self.bot.database.set_item_settings(user_id, item_id)

                output_strings.append(f"You've successfully favorited {wfm_item.item_name}")
            except IntegrityError:
                output_strings.append(f"You've already favorited {wfm_item.item_name}")

        await ctx.send('\n'.join(output_strings))

    @commands.hybrid_command(name='unfavorite',
                             description="Unfavorites an item.",
                             aliases=["unfav", "unfave", "unfavourite"])
    @app_commands.describe(item_name='Item name you wish to unfavorite.')
    async def unfavorite(self, ctx: commands.Context, *, item_name: str) -> None:
        """Unfavorites an item."""
        if not self.bot.supporter_check(ctx):
            raise commands.CheckFailure()

        user_id = ctx.author.id

        output_strings, output_items, _, _ = await self.bot.get_valid_items(
            item_name,
            fetch_orders=True,
        )

        for wfm_item in output_items:
            item_id = wfm_item.item_id
            item_name = wfm_item.item_name

            # Check if the item is favorited by the user
            item_settings = self.bot.database.get_item_settings_by_user_and_item(user_id, item_id)
            if item_settings is None or not item_settings["favorite"]:
                output_strings.append(f"Item {item_name} is not in your favorites.")
                continue

            # Remove the item from favorites
            self.bot.database.remove_item_settings_by_user_and_item(user_id, item_id)
            output_strings.append(f"Item {item_name} has been removed from your favorites.")

        await ctx.send('\n'.join(output_strings))

    @commands.hybrid_command(name='favorites',
                             description="Displays the first two orders and average price for each of your favorite items.",
                             aliases=["favs", "favourites"])
    async def get_favorites(self, ctx: commands.Context) -> None:
        """Displays the first two orders and average price for each of your favorite items."""
        if not self.bot.supporter_check(ctx):
            raise commands.CheckFailure()

        user_id = ctx.author.id

        # Retrieve the user's favorite items from the database
        favorite_items = self.bot.database.get_item_settings_by_user(user_id)
        favorite_items = [item for item in favorite_items if item["favorite"]]

        if not favorite_items:
            await ctx.send("You don't have any favorite items set.")
            return

        view = FavoritesView(ctx, favorite_items, self)
        await view.create_embeds()
        await ctx.send(embeds=view.get_page_embeds(), view=view)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.update_usernames.start()
            self.bot.cogs_ready.ready_up("Market")


async def setup(bot):
    await bot.add_cog(Market(bot))
