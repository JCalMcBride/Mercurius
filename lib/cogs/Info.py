from discord.ext.commands import Cog


class Info(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Info")


async def setup(bot):
    await bot.add_cog(Info(bot))
