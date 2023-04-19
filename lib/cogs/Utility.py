import os
from pathlib import Path

import discord
from discord.ext import commands
from discord.ext.commands import Cog
import git


def fix_cog_name(cog_name):
    return cog_name.replace("_", " ").title()


def get_cog_path(cog: str) -> str:
    return f"lib.cogs.{fix_cog_name(cog)}"


class Utility(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.commit_channel = 1098283737290125344

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

    async def handle_commit(self):
        print('Pulling from GitHub...')
        await self.bot.stdout.send("Pulling from GitHub...")
        repo = git.Repo(".")  # Path to repo

        cogs_dir = Path("lib/cogs")
        cogs_before_pull = set(cogs_dir.glob("*.py"))

        # Get the current modification times of the cogs
        mod_times_before = {cog: os.path.getmtime(cog) for cog in cogs_before_pull}

        repo.git.pull()

        # Get the updated list of cogs after the pull
        cogs_after_pull = set(cogs_dir.glob("*.py"))

        # Determine the cogs that have been updated or added
        cogs_to_reload = {cog: os.path.getmtime(cog) for cog in cogs_after_pull if
                          cog not in mod_times_before or os.path.getmtime(cog) > mod_times_before[cog]}

        # Reload the updated and new cogs
        for cog in cogs_to_reload.keys():
            await self.cog_operation(None, cog.stem, "reload")
        cog_list = '\n'.join([cog.stem for cog in cogs_to_reload.keys()])
        await self.bot.stdout.send(f"Pull complete, Cogs Reloaded:\n"
                                   f"{cog_list}")

    @Cog.listener()
    async def on_message(self, message):
        if message.channel == self.commit_channel:
            await self.handle_commit()

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.commit_channel = self.bot.get_channel(self.commit_channel)
            self.bot.cogs_ready.ready_up("Utility")


async def setup(bot):
    await bot.add_cog(Utility(bot))
