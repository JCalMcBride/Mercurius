from asyncio import sleep
from datetime import datetime

from discord import Embed, HTTPException
from discord.ext import tasks
from discord.ext.commands import command, Cog, has_permissions, MissingRequiredArgument
from discord.utils import get

from lib.starboard_utils import add_new_starboard, update_star_count, get_guild_starboard_emojis, \
    get_guild_starboard_channels, add_new_sb_message, get_sb_message, get_sb_data, update_sb_message_data


class Starboard(Cog, name="starboard"):
    def __init__(self, bot):
        self.bot = bot

        self.kekboard_posts = []

    @tasks.loop(seconds=60.0, reconnect=True)
    async def update_sb_data(self):
        update_sb_message_data()

    @has_permissions(manage_messages=True)
    @command(name="starboard", aliases=["sb"])
    async def create_starboard(self, ctx, channel: str, emoji: str, needed: int):
        """
        Creates a starboard for the server.
        """
        if channel[2:-1].isnumeric() and (emoji.split(":")[2][:-1].isnumeric or ":" not in emoji) and 0 < needed < 100:
            channel_id = channel[2:-1]
            if ":" in emoji:
                emoji_id = int(emoji.split(":")[2][:-1])
            else:
                emoji_id = emoji

            await ctx.send(add_new_starboard(ctx.guild.id, emoji_id, int(channel_id), needed))
        else:
            await ctx.send("Sorry, there was an erorr with this command, "
                           "please try again. Syntax is (starboard channel) (emoji) (stars needed)")

    @create_starboard.error
    async def create_starboard_error(self, ctx, exc):
        if isinstance(exc, MissingRequiredArgument):
            await ctx.send("Sorry, you are missing one or more of the required arguments for this command. "
                           "Syntax is (starboard channel) (emoji) (stars needed)")

    @has_permissions(manage_messages=True)
    @command(name="changestars")
    async def change_starcount(self, ctx, emoji: str, needed: int):
        """
        Changes the number of stars needed for a message to be posted to the starboard.
        """
        if (emoji.split(":")[2][:-1].isnumeric or ":" not in emoji) and 0 < needed < 100:
            if ":" in emoji:
                emoji_id = emoji.split(":")[2][:-1]
            else:
                emoji_id = emoji

            await ctx.send(update_star_count(ctx.guild.id, emoji_id, needed))

    @change_starcount.error
    async def change_starcount_error(self, ctx, exc):
        if isinstance(exc, MissingRequiredArgument):
            await ctx.send(
                "Sorry, you are missing one or more of the required arguments for this command. Syntax is (emoji) (new stars needed)")

    async def kekboard_handler(self, message_reactions):
        user_ids = set()
        for reaction in message_reactions:
            try:
                if 'kek' in reaction.emoji.name.lower():
                    async for user in reaction.users():
                        user_ids.add(user.id)
            except AttributeError:
                continue

        return len(user_ids)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.is_custom_emoji():
            emoji = payload.emoji.id
        else:
            emoji = payload.emoji.name

        guild_starboard_emojis = get_guild_starboard_emojis(payload.guild_id)
        if guild_starboard_emojis is None:
            return

        try:
            if 'kek' in payload.emoji.name.lower():
                emoji = 780515029031976980
        except AttributeError:
            pass

        if emoji in guild_starboard_emojis:
            message = await self.bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
            starboard_data = get_sb_data(payload.guild_id, emoji)

            starboard_channels = get_guild_starboard_channels(payload.guild_id)
            if payload.member.id != message.author.id and payload.channel_id not in starboard_channels:
                emoji_count = 0

                if emoji == 780515029031976980:
                    emoji_count = await self.kekboard_handler(message.reactions)
                    emoji_str = "<:kekx:780515029031976980>"
                else:
                    if payload.emoji.is_custom_emoji():
                        reaction = get(message.reactions, emoji=payload.emoji)
                    else:
                        reaction = get(message.reactions, emoji=emoji)

                    emoji_count = reaction.count
                    emoji_str = str(payload.emoji)

                if emoji_count >= starboard_data['needed']:
                    msg_id = get_sb_message(payload.message_id, emoji)

                    if message.content:
                        embed_msg = f"[Jump to message!]({message.jump_url})\n" + message.content
                    else:
                        embed_msg = f"[Jump to message!]({message.jump_url})"
                    embed = Embed(title=message.author.display_name,
                                  description=embed_msg,
                                  color=message.author.color,
                                  timestamp=datetime.utcnow())

                    embed.set_thumbnail(url=message.author.display_avatar)

                    if len(message.attachments):
                        embed.set_image(url=message.attachments[0].url)
                    elif ".png" in message.content or ".jpg" in message.content or ".gif" in message.content:
                        for content in message.content.split("\n"):
                            if any(x in content for x in ['.png', '.jpg', 'gif']):
                                embed.set_image(url=content)

                    sb_channel = self.bot.get_channel(starboard_data['channel'])

                    await sleep(1)

                    posted = False
                    while not posted:
                        try:
                            if msg_id is None:
                                if payload.message_id in self.kekboard_posts:
                                    return

                                self.kekboard_posts.append(payload.message_id)

                                star_message = await sb_channel.send(
                                    content=emoji_str + " " + str(emoji_count) + " <#" + str(payload.channel_id) + ">",
                                    embed=embed)
                                add_new_sb_message(payload.message_id, emoji, star_message.id)
                            else:
                                star_message = await sb_channel.fetch_message(msg_id)
                                await star_message.edit(
                                    content=emoji_str + " " + str(emoji_count) + " <#" + str(payload.channel_id) + ">",
                                    embed=embed)
                            posted = True
                        except HTTPException:
                            await sleep(1)
            else:
                await message.remove_reaction(payload.emoji, payload.member)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.update_sb_data.start()

            self.bot.cogs_ready.ready_up("Starboard")


async def setup(bot):
    await bot.add_cog(Starboard(bot))
