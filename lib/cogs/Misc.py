from concurrent.futures.thread import ThreadPoolExecutor
from datetime import timezone, datetime, timedelta

import discord
from discord.ext import commands
from discord.ext.commands import command, Cog, has_permissions

def get_wiki_link(item_name: str):
    return f"[{item_name}](https://warframe.fandom.com/wiki/{item_name.replace(' ', '_')}_Incarnon_Genesis)"


class Misc(Cog, name="misc"):
    def __init__(self, bot):
        self.bot = bot

    @command(name='shutdown')
    @commands.is_owner()
    async def shutdown_bot(self, ctx):
        """
        Shuts down the bot entirely, can only be restarted by manually starting it again.
        """
        await self.bot.close()

    @command(name='duviri', aliases=['incarnon', 'dd', 'id',
                                     'incarnonrotation', 'ir', 'rotation', 'rot', 'duvirirotation', 'dr'])
    async def duviri_dates(self, ctx):
        """
        Shows the upcoming rotations for the incarnon adapters.
        """
        rotations = [['Zylok', 'Sibear', 'Dread', 'Despair', 'Hate'],
                     ['Dera', 'Sybaris', 'Cestra', 'Sicarus', 'Okina'],
                     ['Braton', 'Lato', 'Skana', 'Paris', 'Kunai'],
                     ["Boar", "Gammacor", "Angstrum", "Gorgon", "Anku"],
                     ['Bo', 'Latron', 'Furis', 'Furax', 'Strun'],
                     ['Lex', 'Magistar', 'Boltor', 'Bronco', 'Ceramic Dagger'],
                     ['Torid', 'Dual Toxocyst', 'Dual Ichor', 'Miter', 'Atomos'],
                     ['Ack & Brunt', 'Soma', 'Vasto', 'Nami Solo', 'Burston']]

        # Create a datetime object for July 31st, 2023, at midnight UTC
        start_date = datetime(2023, 7, 9, 0, 0, 0, tzinfo=timezone.utc)

        # Get the current date in UTC and set it to midnight
        current_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Calculate the start of the current week
        current_week_start = current_date - timedelta(days=current_date.weekday())

        # Calculate the difference between the current week start and the start date
        difference = current_week_start - start_date

        # Calculate the number of weeks
        weeks = int(difference / timedelta(weeks=1))

        # Calculate the rotation index (0-6)
        rotation_index = weeks % len(rotations)

        rotation_str = f"**This week's rotation**: {', '.join(get_wiki_link(item) for item in rotations[rotation_index])}\n"

        # Print the rotations for the next six weeks
        for i in range(1, 9):
            rotation_str += '\n'
            future_date = current_week_start + timedelta(weeks=i)
            days_until = (future_date - current_date).days
            future_rotation = ', '.join(
                get_wiki_link(item) for item in rotations[(rotation_index + i) % len(rotations)])
            if days_until <= 23:
                rotation_str += f"**Rotation starting** <t:{int(future_date.timestamp())}:R>: {future_rotation}"
            else:
                rotation_str += f"**Rotation starting** <t:{int(future_date.timestamp())}:D>: {future_rotation}"

        embed = discord.Embed(title="Upcoming Incarnons", description=rotation_str, color=discord.Color.blue())

        await ctx.send(embed=embed)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Misc")


async def setup(bot):
    await bot.add_cog(Misc(bot))
