from __future__ import annotations

import io
from datetime import datetime, timedelta
from typing import List, Optional

import discord
import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import mplcyberpunk
import pandas as pd
from discord.ext import commands
from discord.ext.commands import Cog
from market_engine.Models.MarketDatabase import MarketDatabase
from market_engine.Models.MarketItem import MarketItem
import relic_engine

from lib.relic_utils import style_list


class DateSelectMenu(discord.ui.Select):
    def __init__(self, market_graph_view: MarketItemGraphView):
        options = [discord.SelectOption(label="90 Days", value=90),
                   discord.SelectOption(label="180 Days", value=180),
                   discord.SelectOption(label="1 Year", value=365),
                   discord.SelectOption(label="All", value=9999)]
        self.market_graph_view = market_graph_view

        super().__init__(placeholder="Select a time period.", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.market_graph_view.change_date_handler(interaction, self.values[0])


class RelicValueGraphView(discord.ui.View):
    def __init__(self, relic_names: List[str], price_histories: List[dict], bot: commands.Bot,
                 user: discord.Member):
        super().__init__()
        self.message = None
        self.user = user
        self.relic_names = relic_names
        self.price_histories = price_histories
        self.bot = bot
        self.date_menu = DateSelectMenu(self)
        self.add_item(self.date_menu)
        self.date_window = 365

    async def send_message(self, ctx, output_string):
        buf = self.get_graph()

        message = await ctx.send(content='\n'.join([x for x in output_string if x]),
                                 file=discord.File(buf, 'plot.png'),
                                 view=self)

        buf.close()

        self.message = message

    def get_dataframe(self, price_history):
        price_series = pd.Series(price_history, name="Average Return")

        # create a DataFrame from the price series
        df = pd.DataFrame(price_series)
        df.index = pd.to_datetime(df.index)

        # fill missing values with the closest day's value
        df['Average Return'].fillna(method='ffill', inplace=True)

        # If there's still NaNs (e.g., at the beginning of the series), do a backward fill
        df['Average Return'].fillna(method='bfill', inplace=True)

        df['Average Return'] = df['Average Return'].rolling(window=3).median()
        df['Average Return'] = df['Average Return'].rolling(window=3).mean()

        return df

    def get_graph(self):
        # create plot
        style = self.bot.database.get_graph_style(self.user.id)
        with plt.style.context(style):
            fig, ax = plt.subplots(figsize=(10, 6))

            for relic_name, price_history in zip(self.relic_names, self.price_histories):
                df = self.get_dataframe(price_history)

                # filter the dataframe if date window is specified
                if self.date_window is not None:
                    start_date = (datetime.now() - timedelta(days=int(self.date_window))).strftime('%Y-%m-%d')
                    df = df.loc[df.index >= start_date]

                ax.plot(df.index, df['Average Return'], label=relic_name.title())

            # rotate and increase size of x-axis labels
            fig.autofmt_xdate(rotation=30)
            ax.tick_params(axis='x', labelsize=10)

            # increase size of y-axis labels
            ax.tick_params(axis='y', labelsize=10)

            # set axis labels and title
            ax.set_xlabel("Date")
            ax.set_ylabel("Average Return")
            ax.set_title(f"Average Return History: {', '.join([name for name in self.relic_names])}")

            # add legend
            ax.legend(fancybox=True, framealpha=0.5, fontsize='small')

            # format date axis
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())

            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

            ax.yaxis.grid(True)

            # save plot to a file-like object
            fig.tight_layout()
            plt.margins(x=0.002)

            if style == 'cyberpunk':
                mplcyberpunk.make_lines_glow(ax)

            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            buf.seek(0)

            plt.close()

            return buf

    async def change_date_handler(self, interaction, date):
        if interaction.user != self.user:
            await interaction.response.send_message("Only the user who initiated this command "
                                                    "can change the date window",
                                                    ephemeral=True)
            return

        self.date_window = date

        buf = self.get_graph()

        await self.message.edit(attachments=[discord.File(buf, 'plot.png')])

        buf.close()

        await interaction.response.send_message(f"Date window changed to {f'{date} days' if date != '9999' else 'all'}",
                                                ephemeral=True)

class MarketItemGraphView(discord.ui.View):
    def __init__(self, items: List[MarketItem], database: MarketDatabase, bot: commands.Bot,
                 user: discord.Member, history_type: str = 'price', platform: str = 'pc'):
        super().__init__()
        self.message = None
        self.user = user
        self.items = items
        self.database = database
        self.bot = bot
        self.history_type = history_type
        self.platform = platform
        self.date_menu = DateSelectMenu(self)
        self.add_item(self.date_menu)
        self.date_window = 365

    async def send_message(self, ctx, output_string):
        buf = self.get_graph()

        message = await ctx.send(content='\n'.join([x for x in output_string if x]),
                                 file=discord.File(buf, 'plot.png'),
                                 view=self)

        buf.close()

        self.message = message

    @staticmethod
    def get_dataframe(item):
        price_series = pd.Series({k: float(v) for k, v in item.price_history.items()}, name="Price")
        volume_series = pd.Series({k: float(v) for k, v in item.demand_history.items()}, name="Volume")

        # then, concatenate them into a DataFrame
        df = pd.concat([price_series, volume_series], axis=1)
        df.index = df.index.date

        # create a full range of dates from the first to the last date in your data
        full_date_range = pd.date_range(start=df.index.min(), end=df.index.max() + pd.DateOffset(days=1))
        df = df.reindex(full_date_range)

        # fill missing values with the closest day's value
        df['Price'].fillna(method='ffill', inplace=True)
        df['Volume'].fillna(method='ffill', inplace=True)

        # If there's still NaNs (e.g., at the beginning of the series), do a backward fill
        df['Price'].fillna(method='bfill', inplace=True)
        df['Volume'].fillna(method='bfill', inplace=True)

        df['Price'] = df['Price'].rolling(window=3).median()
        df['Price'] = df['Price'].rolling(window=3).mean()

        df['Volume'] = df['Volume'].rolling(window=3).mean()

        return df

    def get_graph(self):
        # create plot
        style = self.bot.database.get_graph_style(self.user.id)
        with plt.style.context(style):
            fig, ax = plt.subplots(figsize=(10, 6))

            plot_list = []
            for item in self.items:
                df = self.get_dataframe(item)

                # filter the dataframe if date window is specified
                if self.date_window is not None:
                    start_date = (datetime.now() - timedelta(days=int(self.date_window))).strftime('%Y-%m-%d')
                    df = df.loc[df.index >= start_date]

                plot_list += [(df, item)]

            for dataframe, item in plot_list:
                item_name = item.item_name.title()

                if len(plot_list) == 1:
                    ax.plot(dataframe.index, dataframe['Price'], label=item_name)
                    ax.bar(dataframe.index, dataframe['Volume'], alpha=0.4, label=f"{item_name} Demand")
                else:
                    if self.history_type == 'price':
                        ax.plot(dataframe.index, dataframe['Price'], label=item_name)
                    elif self.history_type == 'demand':
                        ax.plot(dataframe.index, dataframe['Volume'], label=item_name)

            # rotate and increase size of x-axis labels
            fig.autofmt_xdate(rotation=30)
            ax.tick_params(axis='x', labelsize=10)

            # increase size of y-axis labels
            ax.tick_params(axis='y', labelsize=10)

            # set axis labels and title
            ax.set_xlabel("Date")
            ax.set_ylabel(self.history_type.title())
            ax.set_title(f"{self.history_type.title()} History ({self.platform.upper()}): ")

            # add legend
            ax.legend(fancybox=True, framealpha=0.5, fontsize='small')

            # format date axis
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())

            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

            ax.yaxis.grid(True)

            # save plot to a file-like object
            fig.tight_layout()
            plt.margins(x=0.002)

            if style == 'cyberpunk':
                mplcyberpunk.make_lines_glow(ax)

            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            buf.seek(0)

            plt.close()

            return buf

    async def change_date_handler(self, interaction, date):
        if interaction.user != self.user:
            await interaction.response.send_message("Only the user who initiated this command "
                                                    "can change the date window",
                                                    ephemeral=True)
            return

        self.date_window = date

        buf = self.get_graph()

        await self.message.edit(attachments=[discord.File(buf, 'plot.png')])

        buf.close()

        await interaction.response.send_message(f"Date window changed to {f'{date} days' if date != '9999' else 'all'}",
                                                ephemeral=True)


class Statistics(Cog, name="statistics"):
    def __init__(self, bot):
        self.bot = bot

    async def graph_embed_handler(self, input_string: str, ctx: commands.Context, history_type: str) -> None:
        platform = self.bot.database.get_platform(ctx.author.id)

        output_string, output_items, _, _ = await self.bot.get_valid_items(input_string,
                                                                           fetch_price_history=True,
                                                                           fetch_demand_history=True,
                                                                           platform=platform)

        view = MarketItemGraphView(output_items, self.bot.market_db, self.bot, ctx.author,
                                   history_type=history_type, platform=platform)

        await view.send_message(ctx, output_string)

    @commands.hybrid_command(name='pricehistory',
                             description="Gets price history for the requested item, if it exists.",
                             aliases=["ph", "priceh", "pricehist", "pricehis"])
    async def get_price_history(self, ctx: commands.Context, *, input_string: str) -> None:
        """
        Shows the price history for the requested item.

        The price history is shown in a graph, with the x-axis representing the date and the y-axis representing the price.

        The user can select the time period to display using the dropdown menu.
        """
        await self.graph_embed_handler(input_string, ctx, 'price')

    @commands.hybrid_command(name='demandhistory',
                             description="Gets demand history for the requested item, if it exists.",
                             aliases=["dh", "demandh", "demandhist", "demandhis"])
    async def get_demand_history(self, ctx: commands.Context, *, input_string: str) -> None:
        """
        Shows the demand history for the requested item.

        The price history is shown in a graph, with the x-axis representing the date and the y-axis representing the price.

        The user can select the time period to display using the dropdown menu.
        """
        await self.graph_embed_handler(input_string, ctx, 'demand')

    @commands.hybrid_command(name='setstyle', description="Sets the graph style for the user. (PREMIUM ONLY)",
                             aliases=["ss"])
    async def set_style(self, ctx: commands.Context, style: Optional[str]) -> None:
        """
        Sets the graph style for the user.

        If no style is provided, or an invalid style is provided, the user will be shown a list of valid styles.

        This command is only available to supporters and patrons.
        """
        if not self.bot.supporter_check(ctx):
            raise commands.CheckFailure()

        if style not in plt.style.available + ['cyberpunk'] or style is None:
            await ctx.send(f"Invalid style. Valid styles are: ``{'``, ``'.join(plt.style.available + ['cyberpunk'])}``")
            return

        self.bot.database.set_graph_style(ctx.author.id, style)
        await ctx.send(f"Graph style set to {style}")

    @commands.hybrid_command(name='relic_value_history',
                             description="Gets the average return history for one or more relics.",
                             aliases=["rvh"])
    async def relic_value_history(self, ctx: commands.Context, *, relic_names: str) -> None:
        """
        Shows the average return history for one or more relics.

        The average return history is shown in a graph, with the x-axis representing the date and the y-axis representing the average return.

        Multiple relics can be specified by separating them with commas.

        The user can select the time period to display using the dropdown menu.
        """
        relic_names = [name.strip() for name in relic_names.split(',')]

        style_list = ['1b1', '2b2', '3b3', '4b4']
        refinement_list = ['i', 'e', 'f', 'r']

        processed_relics = []
        for relic_name in relic_names:
            style = '4b4'
            refinement = 'r'
            original_relic_name = relic_name

            # Check if the user concatenated style and refinement values
            for style_val in style_list:
                for ref_val in refinement_list:
                    concat_val = style_val + ref_val
                    if concat_val in relic_name.lower():
                        relic_name = relic_name.replace(concat_val, '').strip()
                        style = style_val
                        refinement = ref_val
                    elif ref_val + style_val in relic_name.lower():
                        relic_name = relic_name.replace(ref_val + style_val, '').strip()
                        style = style_val
                        refinement = ref_val

            # Check if the user included any of the style or refinement values separately
            for style_ref in style_list:
                if style_ref in relic_name.lower() and not any(
                        char.isalnum() for char in relic_name.lower().split(style_ref)[0][-1:]):
                    relic_name = relic_name.replace(style_ref, '').strip()
                    style = style_ref
            for ref_val in refinement_list:
                if ref_val in relic_name.lower() and not any(
                        char.isalnum() for char in relic_name.lower().split(ref_val)[0][-1:]):
                    relic_name = relic_name.replace(ref_val, '').strip()
                    refinement = ref_val

            processed_relics.append((relic_name.title(), style, refinement))

            if len(processed_relics) >= 5:
                await ctx.send("You can only request the average return history for up to 5 relics at a time.")
                return

        invalid_relics = [name for name, _, _ in processed_relics if name.title() not in relic_engine.get_relic_list()]
        if invalid_relics:
            await ctx.send(f"Invalid relic name(s): {', '.join(invalid_relics)}. Please provide valid relic names.")
            return

        price_histories = []
        for relic_name, style, refinement in processed_relics:
            relic_drops = list(relic_engine.get_relic_drops(relic_name.title(), refinement))
            price_dicts = self.bot.market_db.get_price_history_dicts(relic_drops)

            average_returns = {}
            for day in price_dicts:
                average_return = relic_engine.get_average_return(relic_name.title(), style, refinement,
                                                                 price_dicts[day])
                average_returns[day] = average_return

            price_histories.append(average_returns)

        view = RelicValueGraphView([f"{name.title()} {style.lower()}{refinement.lower()}"
                                    for name, style, refinement in processed_relics], price_histories, self.bot, ctx.author)

        await view.send_message(ctx, [f"Average Return History for "
                                      f"{', '.join([name.title() for name, _, _ in processed_relics])}"])

    @set_style.error
    async def set_style_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send("Sorry, this feature is limited to supporters and patrons.", delete_after=5)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Statistics")


async def setup(bot):
    await bot.add_cog(Statistics(bot))
