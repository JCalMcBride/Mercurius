import discord
from discord.ext import commands
from discord.ext.commands import Cog


def fix_cog_name(cog_name):
    return cog_name.replace("_", " ").title()


def get_cog_path(cog: str) -> str:
    return f"lib.cogs.{fix_cog_name(cog)}"


class Utility(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def execute_operation(self, ctx, cog_path, operation, func, cog):
        try:
            await func(cog_path)
            await self.bot.send_message(ctx, f"Cog {operation}ed: {cog}")
        except commands.ExtensionNotLoaded:
            await self.handle_extension_not_loaded(ctx, cog_path, cog)
        except commands.ExtensionNotFound:
            await self.bot.send_message(ctx, f"Cog not found: {cog}")
        except commands.ExtensionAlreadyLoaded:
            await self.bot.send_message(ctx, f"Cog already loaded: {cog}")
        except (commands.ExtensionFailed, commands.ExtensionError) as e:
            await self.bot.send_message(ctx, f"Cog failed to {operation}: {cog}", e)

    async def handle_extension_not_loaded(self, ctx, cog_path, cog):
        try:
            await self.bot.load_extension(cog_path)
            await self.bot.send_message(ctx, f"Cog loaded: {cog}")
        except commands.ExtensionNotFound:
            await self.bot.send_message(ctx, f"Cog not found: {cog}")
            return
        await self.bot.send_message(ctx, f"Cog not loaded: {cog}")

    async def cog_operation(self, ctx: commands.Context, cog: str, operation: str):
        cog_path = get_cog_path(cog)
        operation_methods = {
            "load": self.bot.load_extension,
            "unload": self.bot.unload_extension,
            "reload": self.bot.reload_extension
        }

        if operation not in operation_methods:
            raise ValueError(f"Invalid operation: {operation}")

        await self.execute_operation(ctx, cog_path, operation, operation_methods[operation], cog)

    @commands.command(name="load", description="Load a cog.", aliases=[])
    async def load_cog(self, ctx: commands.Context, cog: str):
        """Load a cog."""
        await self.cog_operation(ctx, cog, "load")

    @commands.command(name="unload", description="Unload a cog.", aliases=[])
    async def unload_cog(self, ctx: commands.Context, cog: str):
        """Unload a cog."""
        await self.cog_operation(ctx, cog, "unload")

    @commands.command(name="reload", description="Reload a cog.", aliases=[])
    async def reload_cog(self, ctx: commands.Context, cog: str):
        """Reload a cog."""
        await self.cog_operation(ctx, cog, "reload")

    @commands.command(name='sync_slash', description='Syncs slash commands.', aliases=[])
    async def sync_slash(self, ctx):
        """Syncs slash commands."""
        try:
            for guild in self.bot.guilds:
                await self.bot.tree.sync(guild=guild)
            await self.bot.tree.sync()

            await ctx.send("Slash commands successfully synced.")
        except Exception as e:
            await ctx.send(
                f"Slash commands could not be synced, try again later, exception: {e}")

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Utility")


async def setup(bot):
    await bot.add_cog(Utility(bot))
