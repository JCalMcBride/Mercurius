import json
from typing import Optional, List

import discord
import relic_engine
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Cog

from lib.common import get_emoji
from lib.relic_utils import style_list, refinement_list, fix_refinement, era_list, use_default, \
    get_average, refinement_list_new, style_list_new


class Relic(Cog, name="relic"):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='average', description="Get the average return for the given relic.",
                             aliases=['avg'])
    @app_commands.describe(relic="The relic you want to get the averages for.",
                           refinement="The refinement you want to check, default is most popular refinement.",
                           style="What style you wish to check, if not provided shows all styles.")
    async def average(self, ctx: commands.Context, relic: str, refinement: Optional[str],
                      style: Optional[str]):
        """Gets the averages on the relic requested"""
        if ctx.interaction is None:
            relic = None
            refinement = None
            style = None
            era = None
            for word in ctx.message.content.split():
                word = word.lower()
                if word.title() in era_list:
                    era = word.title()
                elif era is not None and f"{era.title()} {word.title()}" in relic_engine.get_relic_list():
                    relic = f"{era.title()} {word.title()}"
                elif word in refinement_list:
                    refinement = fix_refinement(word)
                elif word[0:3] in style_list:
                    style = word[0:3]
                    if style == 'sol':
                        style = 'Solo'
                    if word[3:] in refinement_list:
                        refinement = fix_refinement(word[3:])

        embed_list = []
        embeds = []
        embed_title = None
        embed_description = None
        field_name = None
        if refinement is None and style is None:
            refinement = use_default(relic)[0]
            style = style_list_new
        elif refinement is not None and style is None:
            refinement = [refinement]
            style = style_list_new
        elif refinement is None and style is not None:
            refinement = refinement_list_new
            style = [style]

        relic = relic.title()

        if len(style) == 1 or len(refinement) == 1:
            if len(style) == 1 and len(refinement) != 1:
                embed_title = f"{relic} {style[0]}"
                field_name = 'Refinement'
                for ref in refinement:
                    embed_list.append([ref, get_average(relic, style[0], ref)])
            elif len(style) != 1 and len(refinement) == 1:
                embed_title = f"{relic} {refinement[0]}"
                field_name = 'Style'
                for sty in style:
                    embed_list.append([sty, get_average(relic, sty, refinement[0])])
            elif len(style) == 1 and len(refinement) == 1:
                embed_title = f"{relic}"
                embed_description = f"{style[0]} {refinement[0]} Average: " \
                                    f"{int(get_average(relic, style[0], refinement[0]))} " \
                                    f"{get_emoji('platinum')}"
                field_name = None

            embed = discord.Embed()
            embed.title = embed_title
            if embed_description is not None:
                embed.description = embed_description
            else:
                embed.add_field(name=field_name, value='\n'.join([x[0] for x in embed_list]))
                embed.add_field(name='Average',
                                value='\n'.join([str(int(x[1])) + ' ' + get_emoji('platinum') for x in embed_list]))

            embeds.append(embed)

        if ctx.guild is not None and len(embeds) > 1 and ctx.channel.name != 'bot-spam':
            msg = await ctx.send("The options you selected requires multiple embeds, "
                                 "please try again in bot-spam or DMs.")
        else:
            if len(embeds) == 1:
                await ctx.send(embed=embeds[0])
            else:
                for embed in embeds:
                    self.bot.mdh(ctx.message, await ctx.send(embed=embed), ctx.channel)

    @commands.hybrid_command(name='ducat', description="Get the 45 ducat common relics.",
                             aliases=['d', '45d'])
    async def ducat_relic(self, ctx: commands.Context):
        """Shows all relics that have the Braton Prime Receiver as a 45 ducat common drop."""
        ducat_relics = []
        relic_dict = relic_engine.get_relic_dict()
        for relic in relic_dict:
            for drop in relic_dict[relic]:
                if drop == 'Braton Prime Receiver' and relic_dict[relic][drop] == 1:
                    ducat_relics.append(relic)

        # Split relics by their era and stores them in a dictionary
        era_dict = {}
        for relic in ducat_relics:
            era = relic.split()[0]
            if era not in era_dict:
                era_dict[era] = []
            era_dict[era].append(relic)

        embed = discord.Embed(title='Braton Prime Receiver 45 Ducat Common Relics',
                              color=discord.Color.gold())

        # Add the relics to the embed with each era as a field in the order 'Lith', 'Meso', 'Neo', 'Axi'
        for era in era_list:
            if era in era_dict:
                embed.add_field(name=era, value='\n'.join(era_dict[era]), inline=False)


        await ctx.send(embed=embed)

    @average.autocomplete('relic')
    async def relic_ac(self,
                       interaction: discord.Interaction,
                       current: str,
                       ) -> List[app_commands.Choice[str]]:
        return [app_commands.Choice(name=relic.title(), value=str(relic.title()))
                for relic in relic_engine.get_relic_list() if current.lower() in relic.lower()][:10]

    @average.autocomplete('style')
    async def style_ac(self,
                       interaction: discord.Interaction,
                       current: str,
                       ) -> List[app_commands.Choice[str]]:
        return [app_commands.Choice(name=style, value=style) for style in style_list_new if
                current.lower() in style.lower()]

    @average.autocomplete('refinement')
    async def style_ac(self,
                       interaction: discord.Interaction,
                       current: str,
                       ) -> List[app_commands.Choice[str]]:
        return [app_commands.Choice(name=refinement, value=refinement)
                for refinement in refinement_list_new if current.lower() in refinement.lower()]

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Relic")


async def setup(bot):
    await bot.add_cog(Relic(bot))
