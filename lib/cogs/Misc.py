from datetime import datetime

import discord
from discord import app_commands
from discord.ext.commands import Cog

from dateutil.relativedelta import relativedelta
from dateutil.parser import parse
import datetime


def parse_time_expression(time_expr: str) -> datetime:
    time_mapping = {'s': 'seconds', 'm': 'minutes', 'h': 'hours', 'd': 'days', 'w': 'weeks'}
    unit = time_expr[-1].lower()
    value = int(time_expr[:-1])

    if unit not in time_mapping:
        raise ValueError(f"Invalid time expression: {time_expr}")

    return datetime.datetime.now() + relativedelta(**{time_mapping[unit]: value})


class Misc(Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def remove_role(member: discord.Member, role: discord.Role):
        await member.remove_roles(role)

    @app_commands.command(name='temprole', description="Assigns a role for a given period of time.")
    @app_commands.describe(member="The member to assign the role to.",
                           role="The role to assign to the member.",
                           time="The amount of time to assign the role for.")
    async def temprole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role, time: str):
        """Assigns a role for a given period of time."""
        parsed_time = parse_time_expression(time)

        await member.add_roles(role)
        self.bot.scheduler.add_job(self.remove_role,
                                   'date', run_date=parsed_time,
                                   args=[member, role])

        await interaction.response.send_message(f"Role {role.name} has been assigned to "
                                                f"{member.display_name} for {time}.", ephemeral=True)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Misc")


async def setup(bot):
    await bot.add_cog(Misc(bot))
