from typing import Optional, List

import discord
from discord import Member, app_commands
from discord.ext import commands
from discord.ext.commands import Cog

from lib.tag_utils import tag_data


class Tags(Cog, name="tags"):
    def __init__(self, bot):
        self.bot = bot

    async def tag_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        server_tags = self.bot.database.get_server_tags(interaction.guild.id)
        tag_names = [tag["tag_name"] for tag in server_tags]

        if not current:
            # If the user hasn't typed anything, return the first 25 tag names as choices
            return [app_commands.Choice(name=tag, value=tag) for tag in tag_names[:25]]
        else:
            # If the user has typed something, filter the tag names based on the input and return the first 25 matches
            filtered_tags = [tag for tag in tag_names if current.lower() in tag.lower()]
            return [app_commands.Choice(name=tag, value=tag) for tag in filtered_tags[:25]]
    @commands.hybrid_command(name='tag', description="Retrieves a tag by its name and displays its content.", aliases=['t'])
    @app_commands.describe(tag="The name of the tag to retrieve.",
                           target="The member to mention in the tag message.")
    @app_commands.autocomplete(tag=tag_autocomplete)
    async def get_tag(self, ctx: commands.Context,
                      tag: str = commands.parameter(description="The name of the tag to retrieve."),
                      target: Optional[Member] = commands.parameter(description="The member to mention in the tag message.", default=None)):
        """Retrieves a tag by its name and displays its content.  If a target member is provided, the tag will mention them. The tag can be set to automatically delete the command message or send the content as a DM."""
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        tag_info = self.bot.database.retrieve_tag(tag, ctx.guild.id)
        if tag_info:
            content = tag_info["content"]
            if target:
                content = f"{target.mention} {content}"
            if not tag_info["dm"]:
                await ctx.send(content)
            else:
                try:
                    await ctx.author.send(content)
                except discord.Forbidden:
                    await ctx.send("I couldn't send the tag content as a DM.")
            if tag_info["autodelete"]:
                if not ctx.interaction:
                    await ctx.message.delete()
        else:
            await ctx.send(f"Tag '{tag}' not found.")

    @commands.hybrid_command(name='alltags', description="Shows all tags in the server alphabetically.", aliases=['at',
                                                                                                                  'tags'])
    async def all_tags(self, ctx: commands.Context):
        """Shows all tags in the server alphabetically."""
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        server_tags = self.bot.database.get_server_tags(ctx.guild.id)
        if not server_tags:
            await ctx.send("No tags found in this server.")
            return

        # Sort tags alphabetically
        sorted_tags = sorted(server_tags, key=lambda x: x['tag_name'].lower())

        # Create an embed
        embed = discord.Embed(title="Server Tags", color=discord.Color.blue())

        # Group tags by first letter
        tag_groups = {}
        for tag in sorted_tags:
            first_letter = tag['tag_name'][0].upper()
            if first_letter not in tag_groups:
                tag_groups[first_letter] = []
            tag_groups[first_letter].append(f"{tag['tag_name']}")

        # Add tag groups to the embed description
        description = ""
        for letter, tags in tag_groups.items():
            description += f"**[{letter}]**\n{', '.join(tags)}\n\n"

        embed.description = description.strip()

        await self.bot.send_message(ctx, embed=embed,
                                         ephemeral=True)

    @commands.hybrid_command(name='createtag', description="Creates a new tag with the provided name and content.", aliases=['newtag', 'newt', 'createt', 'ct'])
    @app_commands.describe(tag_name="The name of the new tag.",
                           content="The content of the new tag.",
                           autodelete="Whether to automatically delete the command message.",
                           dm="Whether to send the tag content as a DM.")
    @commands.has_permissions(manage_roles=True)
    async def create_tag(self, ctx: commands.Context,
                         tag_name: str = commands.parameter(description="The name of the new tag."),
                         content: str = commands.parameter(description="The content of the new tag."),
                         autodelete: bool = commands.parameter(description="Whether to automatically delete the command message.", default=False),
                         dm: bool = commands.parameter(description="Whether to send the tag content as a DM.", default=False)):
        """Creates a new tag with the provided name and content. You can set the tag to automatically delete the command message or send the content as a DM."""
        self.bot.database.store_tag(tag_name, content, autodelete, dm, ctx.guild.id)
        await self.bot.send_message(ctx, f"Tag '{tag_name}' created.", ephemeral=True)

    @commands.hybrid_command(name='deletetag', description="Deletes a tag by its name.", aliases=['removetag', 'deltag', 'removet', 'delt', 'dt'])
    @app_commands.describe(tag_name="The name of the tag to delete.")
    @commands.has_permissions(manage_roles=True)
    async def delete_tag(self, ctx: commands.Context,
                         tag_name: str = commands.parameter(description="The name of the tag to delete.")):
        """Deletes a tag by its name."""
        tag_id = self.bot.database.get_tag_id(tag_name, ctx.guild.id)
        if tag_id:
            self.bot.database.delete_tag(tag_id, ctx.guild.id)
            await self.bot.send_message(ctx, f"Tag '{tag_name}' deleted.", ephemeral=True)
        else:
            await self.bot.send_message(ctx, f"Tag '{tag_name}' not found.", ephemeral=True)

    @commands.hybrid_command(name='changetagautodelete', description="Changes the autodelete setting of a tag.", aliases=['changedelete', 'setdelete', 'cta'])
    @app_commands.describe(tag_name="The name of the tag to modify.",
                           autodelete="Whether to enable or disable autodelete for the tag.")
    @commands.has_permissions(manage_roles=True)
    async def change_tag_autodelete(self, ctx: commands.Context,
                                    tag_name: str = commands.parameter(description="The name of the tag to modify."),
                                    autodelete: bool = commands.parameter(description="Whether to enable or disable autodelete for the tag.")):
        """Changes the autodelete setting of a tag. If enabled, the command message will be automatically deleted when the tag is retrieved."""
        tag_id = self.bot.database.get_tag_id(tag_name, ctx.guild.id)
        if tag_id:
            self.bot.database.update_autodelete(tag_id, autodelete, ctx.guild.id)
            await self.bot.send_message(ctx, f"Autodelete setting for tag '{tag_name}' updated.", ephemeral=True)
        else:
            await self.bot.send_message(ctx, f"Tag '{tag_name}' not found.", ephemeral=True)

    @commands.hybrid_command(name='changetagdm', description="Changes the DM setting of a tag.", aliases=['changedm', 'pmtag', 'settagdm', 'dmtag', 'ctd'])
    @app_commands.describe(tag_name="The name of the tag to modify.",
                           dm="Whether to enable or disable DM sending for the tag.")
    @commands.has_permissions(manage_roles=True)
    async def change_tag_dm(self, ctx: commands.Context,
                            tag_name: str = commands.parameter(description="The name of the tag to modify."),
                            dm: bool = commands.parameter(description="Whether to enable or disable DM sending for the tag.")):
        """Changes the DM setting of a tag. If enabled, the tag content will be sent as a DM when retrieved."""
        tag_id = self.bot.database.get_tag_id(tag_name, ctx.guild.id)
        if tag_id:
            self.bot.database.update_dm(tag_id, dm, ctx.guild.id)
            await self.bot.send_message(ctx, f"DM setting for tag '{tag_name}' updated.", ephemeral=True)
        else:
            await self.bot.send_message(ctx, f"Tag '{tag_name}' not found.", ephemeral=True)

    @commands.hybrid_command(name='linktagtoserver', description="Links a tag to a server, allowing it to be used in that server.", aliases=['linktag', 'ltts'])
    @app_commands.describe(tag_name="The name of the tag to link.",
                           server_id="The ID of the server to link the tag to.")
    @commands.has_permissions(manage_roles=True)
    async def link_tag_to_server(self, ctx: commands.Context,
                                 tag_name: str = commands.parameter(description="The name of the tag to link."),
                                 server_id: int = commands.parameter(description="The ID of the server to link the tag to.")):
        """Links a tag to a server."""
        tag_id = self.bot.database.get_tag_id(tag_name, ctx.guild.id)
        if tag_id:
            self.bot.database.link_tag_to_server(tag_id, server_id)
            await self.bot.send_message(ctx, f"Tag '{tag_name}' linked to server {server_id}.", ephemeral=True)
        else:
            await self.bot.send_message(ctx, f"Tag '{tag_name}' not found.", ephemeral=True)

    @commands.hybrid_command(name='linkserver', description="Links the current server to another server, allowing tags to be shared between them.", aliases=['ls'])
    @app_commands.describe(server_id="The ID of the server to link to the current server.")
    @commands.is_owner()
    async def link_server(self, ctx: commands.Context,
                          server_id: int = commands.parameter(description="The ID of the server to link to the current server.")):
        """Links the current server to another server."""
        if ctx.guild:
            self.bot.database.link_servers(ctx.guild.id, server_id)
            await self.bot.send_message(ctx, f"Server {ctx.guild.id} linked to server {server_id}.", ephemeral=True)
        else:
            await self.bot.send_message(ctx, "This command can only be used in a server.", ephemeral=True)

    @commands.hybrid_command(name='bulkinserttags', description="Inserts multiple predefined tags into the specified server.", aliases=['bit'])
    @app_commands.describe(server_id="The ID of the server to insert the tags into.")
    @commands.is_owner()
    async def bulk_insert_tags(self, ctx: commands.Context,
                               server_id: int = commands.parameter(description="The ID of the server to insert the tags into.")):
        """Inserts multiple tags at once."""
        self.bot.database.bulk_insert_tags(tag_data, [server_id])
        await self.bot.send_message(ctx, f"Tags inserted into server {server_id}.", ephemeral=True)

    @Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        prefixes = await self.bot.get_prefix(message)
        if not isinstance(prefixes, list):
            prefixes = [prefixes]

        for prefix in prefixes:
            if message.content.startswith(prefix):
                tag_name = message.content[len(prefix):].strip()
                tag_info = self.bot.database.retrieve_tag(tag_name.lower(), message.guild.id)
                if not tag_info:
                    tag_info = self.bot.database.retrieve_tag(tag_name, message.guild.id)

                if tag_info:
                    content = tag_info["content"]
                    if not tag_info["dm"]:
                        await message.channel.send(content)
                    else:
                        await message.author.send(content)
                    if tag_info["autodelete"]:
                        await message.delete()
                    break

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Tags")


async def setup(bot):
    await bot.add_cog(Tags(bot))
