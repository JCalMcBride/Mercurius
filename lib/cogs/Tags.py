from typing import Optional, List

import discord
from discord import Member, Forbidden, NotFound, HTTPException, app_commands
from discord.ext import commands
from discord.ext.commands import command, Cog, has_permissions, BucketType, cooldown

from lib.tag_utils import get_tag, change_attribute, get_tag_embed, new_tag, delete_tag, check_tag_exists, \
    tag_data


class Tags(Cog, name="tags"):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='tag', description="Show the requested tag.")
    @app_commands.describe(tag="The tag you want to show.",
                           target="Person you wish to mention in the tag message.")
    async def get_tag(self, ctx: commands.Context, tag: str, target: Optional[Member]):
        """Shows the tag requested."""
        tag = get_tag(tag)
        if not tag:
            msg = await ctx.send("Could not find the requested tag.", ephemeral=True)
            self.bot.mdh(ctx.message, msg, ctx.channel, 5)
            return

        target_text = ''
        if ctx.guild is not None and target:
            target_text = f"{target.mention} "
        else:
            tag_message = f"{target_text}{tag['content']}"

            if tag['autodelete'] or tag['dm']:
                try:
                    await ctx.message.delete(delay=1)
                except NotFound:
                    pass
                except Forbidden:
                    pass
                except HTTPException:
                    pass
                except AttributeError:
                    pass
            if tag['dm']:
                channel = await ctx.author.create_dm()
                await channel.send(tag_message)
            else:
                await ctx.send(tag_message)

    @has_permissions(manage_messages=True)
    @command(name='changeautodelete', aliases=["delete", "autodelete", "changedelete"])
    async def setautodelete(self, ctx, tag: str):
        """Changes whether the tag command message gets deleted or kept."""
        await ctx.send(change_attribute(tag.lower(), 'autodelete'))

    @has_permissions(manage_messages=True)
    @command(name='changedm', aliases=["setdm"])
    async def setautodm(self, ctx, tag: str):
        """Changes a given tag to be a "DM" tag, meaning it will send the tag content to the user's DMs."""
        await ctx.send(change_attribute(tag.lower(), 'dm'))

    @command(name='tags')
    @cooldown(1, 2, BucketType.user)
    async def tags(self, ctx):
        """Sends a list of all the tags."""
        await ctx.send(embed=get_tag_embed())

    @has_permissions(manage_messages=True)
    @command(name='createtag', aliases=["newtag", "updatetag"])
    async def createtag(self, ctx, tag: str, *, content: str):
        """Creates a new tag and saves it."""
        await ctx.send(content=new_tag(tag, content))

    @has_permissions(manage_messages=True)
    @command(name='deletetag', aliases=["removetag"])
    async def deletetag(self, ctx, tag: str):
        """Deletes the given tag."""
        await ctx.send(content=delete_tag(tag.lower()))

    async def text_tag_handler(self, message):
        ctx = await self.bot.get_context(message)
        if not (ctx.prefix is not None and ctx.command is None):
            return

        if tag := check_tag_exists(message.content[len(ctx.prefix):]):
            await ctx.invoke(self.bot.get_command('tag'), tag=tag, target=None)

    @Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        await self.text_tag_handler(message)

    @get_tag.autocomplete('tag')
    async def tag_ac(self,
                     interaction: discord.Interaction,
                     current: str,
                     ) -> List[app_commands.Choice[str]]:
        return [app_commands.Choice(name=tag, value=tag)
                for tag in list(tag_data) if current.lower() in tag.lower()][:10]

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Tags")


async def setup(bot):
    await bot.add_cog(Tags(bot))
