from __future__ import annotations

import asyncio
from typing import Tuple

import discord
import pycountry as pycountry
import relic_engine
from bs4 import BeautifulSoup
from dateutil.parser import parse
from discord import ButtonStyle, app_commands
from discord.ext import commands, tasks
from discord.ext.commands import Cog
from market_engine.Models.MarketDatabase import MarketDatabase
from market_engine.Models.MarketItem import MarketItem
from market_engine.Models.MarketUser import MarketUser


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
        embed = await self.embed()

        for field in self.get_part_price_embed_fields(order_type):
            embed.add_field(name=field[0], value=field[1], inline=True)

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

        embed.add_field(name='Period', value='```\n' + '\n'.join(period) + '```', inline=True)
        embed.add_field(name='Volume', value='```\n' + '\n'.join(volume) + '```', inline=True)
        embed.add_field(name='Daily Average', value='```\n' + '\n'.join(daily_average) + '```', inline=True)

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

        for field in self.get_order_embed_fields(num_orders=num_orders):
            embed.add_field(name=field[0], value=field[1], inline=True)

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


class Market(Cog):
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
        """Shows recent reviews for a given user on warframe.market."""
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

    @app_commands.command(name='addalias',
                          description="Adds an alias for an item.")
    @app_commands.describe(target_item='Item you want to add an alias for.')
    @app_commands.describe(alias='Alias you want to add.')
    @app_commands.checks.has_any_role(780376440998199296,
                                      780376480734904351,
                                      780630958368882689,
                                      1035644033843855490)
    async def add_alias(self, interaction: discord.Interaction, target_item: str, alias: str) -> None:
        wfm_item: MarketItem = await self.bot.market_db.get_item(target_item.lower(),
                                                                 fetch_parts=False,
                                                                 fetch_orders=False,
                                                                 fetch_part_orders=False,
                                                                 fetch_price_history=False,
                                                                 fetch_demand_history=False)

        if wfm_item is None:
            await interaction.response.send_message(f"Item {target_item} does not exist on Warframe.Market",
                                                    ephemeral=True)
            return

        if alias.lower() in wfm_item.aliases:
            await interaction.response.send_message(f"Alias {alias} already exists for item {target_item}",
                                                    ephemeral=True)
            return

        wfm_item.add_alias(alias.lower())
        await interaction.response.send_message(f"Alias {alias} added for item {target_item}",
                                                ephemeral=True)

    @app_commands.command(name='removealias',
                          description="Removes an alias for an item.")
    @app_commands.describe(target_item='Item you want to remove an alias for.')
    @app_commands.describe(alias='Alias you want to remove.')
    @app_commands.checks.has_any_role(780376440998199296,
                                      780376480734904351,
                                      780630958368882689,
                                      1035644033843855490)
    async def remove_alias(self, interaction: discord.Interaction, target_item: str, alias: str) -> None:
        wfm_item: MarketItem = await self.bot.market_db.get_item(target_item.lower(),
                                                                 fetch_parts=False,
                                                                 fetch_orders=False,
                                                                 fetch_part_orders=False,
                                                                 fetch_price_history=False,
                                                                 fetch_demand_history=False)

        if wfm_item is None:
            await interaction.response.send_message(f"Item {target_item} does not exist on Warframe.Market",
                                                    ephemeral=True)
            return

        if alias.lower() not in wfm_item.aliases:
            await interaction.response.send_message(f"Alias {alias} does not exist for item {target_item}",
                                                    ephemeral=True)
            return

        wfm_item.remove_alias(alias.lower())
        await interaction.response.send_message(f"Alias {alias} removed from item {target_item}",
                                                ephemeral=True)

    @commands.hybrid_command(name='setplatform',
                             description="Sets your platform for market commands.",
                             aliases=["sp", "setp", "setplat"])
    async def set_user_platform(self, ctx: commands.Context, platform: str) -> None:
        if platform.lower() not in ['pc', 'ps4', 'xbox', 'switch']:
            await ctx.send("Invalid platform. Valid platforms are: PC, PS4, Xbox, Switch")
            return

        self.bot.database.set_platform(ctx.author.id, platform.lower())
        await ctx.send(f"Platform set to {platform}")

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.update_usernames.start()
            self.bot.cogs_ready.ready_up("Market")


async def setup(bot):
    await bot.add_cog(Market(bot))
