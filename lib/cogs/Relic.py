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
from lib.simulation_utils import simulation_engine


def parse_command_args(content):
    relic = None
    refinements = []
    styles = []
    era = None
    vanguard = False
    for word in content.split():
        word = word.lower()
        if word.title() in era_list:
            era = word.title()
        elif word.title() == "Vanguard":
            vanguard = True
            era = "Axi"
        elif era is not None and f"{era.title()} {word.title()}" in relic_engine.get_relic_list() and not vanguard:
            relic = f"{era.title()} {word.title()}"
        elif vanguard and f"Vanguard {word.title()}" in relic_engine.get_relic_list():
            relic = f"Vanguard {word.title()}"
        elif word in refinement_list:
            refinements.append(fix_refinement(word))
        elif word[0:3] in style_list:
            style = 'Solo' if word[0:3] == 'sol' else word[0:3]
            styles.append(style)
            if len(word) > 3 and word[3:] in refinement_list:
                refinements.append(fix_refinement(word[3:]))
    return relic, refinements, styles, era


def generate_embeds(relic, refinements, styles):
    embeds = []
    if not refinements and not styles:
        refinements = use_default(relic)[0]
        styles = style_list_new
    elif refinements and not styles:
        styles = style_list_new
    elif not refinements and styles:
        refinements = refinement_list_new

    if len(styles) == 1 or len(refinements) == 1:
        embed_list = []
        embed_title = embed_description = field_name = None

        if len(styles) == 1 and len(refinements) != 1:
            embed_title = f"{relic} {styles[0]}"
            field_name = 'Refinement'
            embed_list = [[ref, get_average(relic, styles[0], ref)] for ref in refinements]
        elif len(styles) != 1 and len(refinements) == 1:
            embed_title = f"{relic} {refinements[0]}"
            field_name = 'Style'
            embed_list = [[sty, get_average(relic, sty, refinements[0])] for sty in styles]
        elif len(styles) == 1 and len(refinements) == 1:
            embed_title = f"{relic}"
            embed_description = f"{styles[0]} {refinements[0]} Average: {int(get_average(relic, styles[0], refinements[0]))} {get_emoji('platinum')}"

        embed = create_embed(embed_title, embed_description, field_name, embed_list)
        embeds.append(embed)
    else:
        for sty in styles:
            for ref in refinements:
                embed_title = f"{relic} {sty} {ref}"
                embed_description = f"Average: {int(get_average(relic, sty, ref))} {get_emoji('platinum')}"
                embed = create_embed(embed_title, embed_description, None, [])
                embeds.append(embed)

    return embeds


def create_embed(embed_title, embed_description, field_name, embed_list):
    embed = discord.Embed()
    embed.title = embed_title
    if embed_description is not None:
        embed.description = embed_description
    else:
        embed.add_field(name=field_name, value='\n'.join([x[0] for x in embed_list]))
        embed.add_field(name='Average', value='\n'.join([str(int(x[1])) + ' ' +
                                                         get_emoji('platinum') for x in embed_list]))
        per_run = [str(int(x[1] / simulation_engine.num_runs_dict[x[0]])) + ' ' +
                   get_emoji('platinum') for x in embed_list
                   if x[0] in simulation_engine.num_runs_dict]
        if per_run:
            embed.add_field(name='Per Run', value='\n'.join(per_run))
    return embed

class Relic(Cog, name="relic"):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='average', description="Get the average return for the given relic.", aliases=['avg'])
    @app_commands.describe(relic="The relic you want to get the averages for.",
                           refinement="The refinement you want to check, default is most popular refinement.",
                           style="What style you wish to check, if not provided shows all styles.")
    async def average(self, ctx: commands.Context, relic: str, refinement: Optional[str], style: Optional[str]):
        """Gets the averages on the relic requested"""
        try:
            if ctx.interaction is None:
                relic, refinement, style, era = parse_command_args(ctx.message.content)

            if relic is None:
                await ctx.send("Please provide a valid relic name.")
                return

            relic = relic.title()
            embeds = generate_embeds(relic, refinement, style)

            if ctx.guild is not None and len(embeds) > 1 and ctx.channel.name != 'bot-spam':
                await ctx.send("The options you selected require multiple embeds, please try again in bot-spam or DMs.")
            else:
                for embed in embeds:
                    self.bot.mdh(ctx.message, await ctx.send(embed=embed), ctx.channel)
        except Exception as e:
            await ctx.send(f"An error occurred while processing your request: {str(e)}")

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
