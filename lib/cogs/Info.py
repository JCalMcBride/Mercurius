from datetime import datetime
from typing import Optional

import discord
from discord import Member, Guild
from discord.ext import commands
from discord.ext.commands import Cog
from more_itertools import chunked


def get_author_info(target: discord.Member):
    return {
        "name": f"{target}",
        "icon_url": target.display_avatar.url
    }


def get_guild_info(target: discord.Guild):
    return {
        "name": f"{target}",
        "icon_url": target.icon.url if target.icon else None
    }


def get_member_embed(member: discord.Member):
    embed = discord.Embed(color=member.color,
                          timestamp=datetime.utcnow())

    embed.set_author(**get_author_info(member))

    embed.set_thumbnail(url=member.display_avatar)

    embed.description = f"{member.mention} {member.id}"

    fields = [("Roles", get_roles_list(member), False),
              ("Created", member.created_at.strftime("%Y-%m-%d %H:%M:%S"), True),
              ("Joined server", member.joined_at.strftime("%Y-%m-%d %H:%M:%S"), True),
              ("Server booster?", bool(member.premium_since), True),
              ("In Voice?", bool(member.voice), True),
              ("Bot?", member.bot, True)]

    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)

    return embed


def get_roles_list(target: discord.Member):
    if len(target.roles[1:]) > 0:
        return ' '.join([role.mention for role in target.roles[1:]])

    return "None"


def get_member_target(ctx, target: Optional[Member]):
    if target is None:
        target = ctx.author
    return target


def get_guild_target(ctx, target: Optional[Guild]):
    if target is None:
        target = ctx.guild
    return target


async def get_owner_color(bot, guild):
    owner = await bot.get_or_fetch_member(guild, guild.owner_id)
    return owner.color if owner else discord.Color.default()


async def get_server_embed(bot, guild):
    # Member lists and presences need privileged intents, so use the approximate counts Discord provides instead.
    guild_counts = await bot.fetch_guild(guild.id, with_counts=True)

    embed = discord.Embed(color=await get_owner_color(bot, guild),
                          timestamp=datetime.utcnow())

    embed.set_thumbnail(url=guild.icon)

    embed.set_author(**get_guild_info(guild))

    if guild.description:
        embed.description = guild.description

    fields = [("ID", guild.id, True),
              ("Owner", f"<@{guild.owner_id}>", True),
              ("Boosts", guild.premium_subscription_count, True),

              ("Created", guild.created_at.strftime("%Y-%m-%d %H:%M:%S"), True),
              ("Members", guild_counts.approximate_member_count, True),
              ("Online", guild_counts.approximate_presence_count, True),

              ("Banned members", len([i async for i in guild.bans()]), True),
              ("Text channels", len(guild.text_channels), True),

              ("Voice Channels", len(guild.voice_channels), True),
              ("Roles", len(guild.roles), True),
              ("Invites", len(await guild.invites()), True),

              ("Vanity URL", guild.vanity_url_code, True),
              ("Emoji Count", len(guild.emojis), True),
              ("Sticker Count", len(guild.stickers), True)]

    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)

    return embed


class Info(Cog, name="info"):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='userinfo', description="Display information about the requested user.",
                             aliases=["memberinfo", "user", "member", "ui", "mi", "whois"])
    async def user_info(self, ctx: commands.Context, target: Optional[Member]):
        """Gives info on the given user."""
        target = get_member_target(ctx, target)
        embed = get_member_embed(target)

        await self.bot.send_message(ctx, embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Display information about the current server.",
                             aliases=['guildinfo', 'server', 'guild', 'si', 'gi'])
    async def server_info(self, ctx: commands.Context):
        """Display information about the current server."""
        target = get_guild_target(ctx, None)
        embed = await get_server_embed(self.bot, target)

        await self.bot.send_message(ctx, embed=embed)

    @commands.hybrid_command(name="avatar", description="Display the avatar of the requested user.",
                             aliases=['av', 'pfp'])
    async def avatar(self, ctx: commands.Context, target: Optional[Member]):
        """Display the avatar of the requested user."""
        target = get_member_target(ctx, target)
        embed = discord.Embed(color=target.color,
                              timestamp=datetime.utcnow())

        embed.set_author(**get_author_info(target))

        embed.set_image(url=target.display_avatar)

        await self.bot.send_message(ctx, embed=embed)

    @commands.hybrid_command(name="guildemojis", description="Display all the emojis of the current server.",
                             aliases=['ge', 'serveremojis', 'se'])
    async def guild_emojis(self, ctx: commands.Context):
        """Display all the emojis of the current server."""

        if ctx.guild is None:
            await self.bot.send_message(ctx, "This command can only be used in a server.")
            return

        if ctx.channel.name != 'bot-spam':
            await self.bot.send_message(ctx, "This command can only be used in bot-spam.")
            return

        target = get_guild_target(ctx, None)
        if len(target.emojis) == 0:
            await self.bot.send_message(ctx, "No emojis found.")
            return

        emoji_list = [str(emoji) for emoji in target.emojis if emoji.is_usable()]

        owner_color = await get_owner_color(self.bot, target)
        embeds = []
        for emojis in chunked(emoji_list, 100):
            embed = discord.Embed(color=owner_color,
                                  timestamp=datetime.utcnow())

            embed.set_author(**get_guild_info(target))

            embed.description = " ".join(emojis)

            embeds.append(embed)

        for embed in embeds:
            await self.bot.send_message(ctx, embed=embed)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Info")


async def setup(bot):
    await bot.add_cog(Info(bot))
