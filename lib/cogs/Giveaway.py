import json
import logging
import pickle
import random
from datetime import datetime, timedelta
from typing import Optional, List

import discord
from apscheduler.jobstores.base import JobLookupError
from discord import NotFound, Forbidden, HTTPException, app_commands, Embed
from discord.app_commands import Choice, CheckFailure
from discord.ext import commands, tasks
from discord.ext.commands import Cog
from pytz import UTC

with open('lib/data/giveaway_data.json') as f:
    x = json.load(f)
    giveaway_data = {int(k): v for k, v in x.items()}


def update_giveaway_data():
    with open('lib/data/giveaway_data.json', 'w') as fp:
        json.dump(giveaway_data, fp, indent=4)


intervals = (
    ('weeks', 604800),  # 60 * 60 * 24 * 7
    ('days', 86400),  # 60 * 60 * 24
    ('hours', 3600),  # 60 * 60
    ('minutes', 60),
    ('seconds', 1),
)


def convert(time):
    pos = ["s", "m", "h", "d"]

    time_dict = {"s": 1, "m": 60, "h": 3600, "d": 86400}

    unit = time[-1]

    if unit not in pos:
        return "Could not detect a valid unit of time. Valid units are s, m, h, and d."
    try:
        val = int(time[:-1])
    except:
        return "Invalid amount of time. Please enter a valid number next time."

    if val * time_dict[unit] < 0 or val * time_dict[unit] > 6048000:
        return "Time must be between 1 second and 10 weeks."

    if time == "cancel":
        return "cancel"

    return val * time_dict[unit]


def display_time(seconds, granularity=2):
    if seconds <= 65:
        return 'Less than 1 minute.'

    result = []

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append("{} {}".format(value, name))
    return ', '.join(result[:granularity])


def get_giveaway_time(start_time, duration, current_time):
    return int((start_time + duration) - current_time.timestamp())


def get_embed(giveaway_prize, author, role, winners, current_time, giveaway_time, winner_list, start_time, duration):
    embed = Embed(title=f"{giveaway_prize}")

    footer_text = ""
    if winners > 1:
        footer_text += f"{winners} Winners | "
    if winner_list is None:
        description_text = f"React with 🎉 to enter!\n" \
                           f"Time remaining: {display_time(giveaway_time)}\n"

        end_time = current_time + timedelta(seconds=giveaway_time)
    else:
        description_text = f"Winners:\n" \
                           f"{chr(10).join(winner_list)}\n"

        end_time = datetime.fromtimestamp(start_time, tz=UTC) + timedelta(seconds=duration)

    description_text += f"Hosted by: {author.mention}"
    footer_text += f"End{'s' if winner_list is None else 'ed'} at {end_time.strftime('%Y-%m-%d %I:%M:%S %p')} UTC"

    if role is not None:
        description_text += f"\nRole Required: {role.mention}"

    embed.description = description_text
    embed.set_footer(text=footer_text)

    return embed


def log_entry(message):
    logging.info(message)


def get_giveaway_winners(role, winners, message_id, reactions=None):
    winner_list = []

    if reactions is None and role is None:
        try:
            reactions = pickle.load(open(f"lib/data/giveaways/{message_id}.p", "rb"))
        except FileNotFoundError:
            log_entry(f"Could not find reactions for {message_id}")
    else:
        reactions = [u for u in reactions if not u.bot]
        if role is not None:
            for reaction in reactions:
                if not hasattr(reaction, 'roles'):
                    reactions.remove(reaction)
            reactions = [u for u in reactions if role in u.roles]

        reactions = [u.mention for u in reactions]

    if len(reactions) > 0:
        for i in range(min(winners, len(reactions))):
            winner = random.choice(reactions)
            reactions.remove(winner)

            winner_list.append(winner)

    pickle.dump(reactions, open(f"lib/data/giveaways/{message_id}.p", "wb"))

    if len(winner_list) == 0:
        winner_list = ['No one!']

    return winner_list


def new_giveaway_handler(msg_id, guild_id, author_id, channel_id, role_id, start_time, duration, winners, prize):
    giveaway_data[msg_id] = {
        'guild': guild_id,
        'author': author_id,
        'channel': channel_id,
        'role': role_id,
        'start_time': start_time,
        'duration': duration,
        'winners': winners,
        'prize': prize,
        'complete': False
    }

    update_giveaway_data()


def get_giveaway_data(msg_id):
    return giveaway_data[msg_id]


def set_giveaway_complete(msg_id):
    giveaway_data[msg_id]['complete'] = True

    update_giveaway_data()


def get_active_giveaways():
    giveaway_list = []
    for giveaway in giveaway_data:
        if not giveaway_data[giveaway]['complete']:
            giveaway_list.append(giveaway)

    return giveaway_list


class Giveaway(Cog, name="giveaway"):
    def __init__(self, bot):
        self.bot = bot
        self.gcreate_user = None
        self.giveaway_posts = {}

    @tasks.loop(seconds=60, reconnect=True)
    async def update_giveaway_posts(self):
        active_giveaways = get_active_giveaways()

        for giveaway in active_giveaways:
            await self.update_post(giveaway)

    async def update_post(self, message_id):
        giveaway_data = get_giveaway_data(message_id)

        current_time = datetime.now(tz=UTC)

        giveaway_time = get_giveaway_time(giveaway_data['start_time'], giveaway_data['duration'], current_time)

        if giveaway_time <= 15:
            return

        channel_obj = self.bot.get_channel(giveaway_data['channel'])
        if channel_obj is None:
            log_entry(f"Channel: {giveaway_data['channel']} for guild {giveaway_data['guild']} "
                      f"and giveaway_prize {giveaway_data['prize']} could not be found.")
            return

        if message_id not in self.giveaway_posts:
            try:
                message_obj = await channel_obj.fetch_message(message_id)
                self.giveaway_posts[message_id] = message_obj
            except NotFound:
                log_entry(f"Message: {message_id} for guild {giveaway_data['guild']} and "
                          f"giveaway_prize {giveaway_data['prize']} could not be found.")
                return
            except Forbidden:
                log_entry(f"Message: {message_id} for guild {giveaway_data['guild']} and "
                          f"giveaway_prize {giveaway_data['prize']} has improper permissions.")
                return
            except HTTPException:
                log_entry(f"Message: {message_id} for guild {giveaway_data['guild']} and "
                          f"giveaway_prize {giveaway_data['prize']}  had an "
                          f"unspecified error while attempting to retrieve the message.")
                return
        else:
            message_obj = self.giveaway_posts[message_id]

        try:
            role_obj = None
            if giveaway_data['role'] != 0:
                guild_obj = self.bot.get_guild(giveaway_data['guild'])
                if guild_obj is None:
                    log_entry(
                        f"Error while attempting to fetch guild {giveaway_data['guild']} for giveaway {message_id} "
                        f"with prize {giveaway_data['prize']}, could not find guild.")
                    return
                guild_roles = guild_obj.roles

                role_obj = discord.utils.get(guild_roles, id=giveaway_data['role'])
                if role_obj is None:
                    log_entry(f"Error while attempting to fetch role {giveaway_data['role']} for giveaway {message_id} "
                              f"with prize {giveaway_data['prize']}, could not find role.")
                    return

            author = self.bot.get_user(giveaway_data['author'])
            if author is None:
                log_entry(f"Error while attempting to get author for giveaway {message_id} "
                          f"with prize {giveaway_data['prize']}, could not find author.")
                return

            embed = get_embed(giveaway_data['prize'], author, role_obj, giveaway_data['winners'], current_time,
                              giveaway_time, None, giveaway_data['start_time'], giveaway_data['duration'])
            await message_obj.edit(embed=embed)
        except HTTPException:
            log_entry(f"Unspecified error for channel: {giveaway_data['channel']} and guild: {giveaway_data['guild']}"
                      f" for giveaway {message_id} with prize {giveaway_data['prize']} "
                      f"had an unspecified error while editing the message.")
            return

    async def complete_giveaway(self, message_id):
        try:
            giveaway_data = get_giveaway_data(message_id)
        except KeyError:
            return "Could not find a giveaway with that ID."

        channel_obj = self.bot.get_channel(giveaway_data['channel'])
        if channel_obj is None:
            log_entry(f"Channel: {giveaway_data['channel']} for guild {giveaway_data['guild']} "
                      f"and giveaway_prize {giveaway_data['prize']} could not be found.")
            return

        try:
            message_obj = await channel_obj.fetch_message(message_id)
        except NotFound:
            log_entry(f"Message: {message_id} for guild {giveaway_data['guild']} and giveaway_prize "
                      f"{giveaway_data['prize']} could not be found.")
            return
        except Forbidden:
            log_entry(f"Message: {message_id} for guild {giveaway_data['guild']} "
                      f"and giveaway_prize {giveaway_data['prize']} has improper permissions.")
            return
        except HTTPException:
            log_entry(f"Message: {message_id} for guild {giveaway_data['guild']} and giveaway_prize "
                      f"{giveaway_data['prize']}  had an unspecified error while attempting to retrieve the message.")
            return

        try:
            role_obj = None
            if giveaway_data['role'] != 0:
                guild_obj = self.bot.get_guild(giveaway_data['guild'])
                if guild_obj is None:
                    log_entry(
                        f"Error while attempting to fetch guild {giveaway_data['guild']} for giveaway {message_id} "
                        f"with prize {giveaway_data['prize']}, could not find guild.")
                    return
                guild_roles = guild_obj.roles

                role_obj = discord.utils.get(guild_roles, id=giveaway_data['role'])
                if role_obj is None:
                    log_entry(f"Error while attempting to fetch role {giveaway_data['role']} for giveaway {message_id} "
                              f"with prize {giveaway_data['prize']}, could not find role.")
                    return

            author = self.bot.get_user(giveaway_data['author'])
            if author is None:
                log_entry(f"Error while attempting to get author for giveaway {message_id} "
                          f"with prize {giveaway_data['prize']}, could not find author.")
                return

            reactions = message_obj.reactions

            users = [user async for user in reactions[0].users()]

            winner_list = get_giveaway_winners(role_obj, giveaway_data['winners'], message_id, users)
        except HTTPException:
            log_entry(f"Unspecified error for channel: {giveaway_data['channel']} and guild: {giveaway_data['guild']}"
                      f" for giveaway {message_id} with prize {giveaway_data['prize']} "
                      f"had an unspecified error while editing the message.")
            return

        embed = discord.Embed(title="Congratulations!",
                              description=f"Prize: {giveaway_data['prize']}\n"
                                          f"Winner(s):\n"
                                          f"{chr(10).join(winner_list)}\n"
                                          f"Hosted by: {author.mention}\n"
                                          f"[Jump to giveaway!]({message_obj.jump_url})")
        try:
            set_giveaway_complete(message_id)
            msg_embed = get_embed(giveaway_data['prize'], author, role_obj, giveaway_data['winners'], datetime.now(tz=UTC),
                                  None, winner_list, giveaway_data['start_time'], giveaway_data['duration'])
            await message_obj.edit(embed=msg_embed)
            await channel_obj.send(content=" ".join(winner_list), embed=embed)
        except Forbidden:
            log_entry(f"Unspecified error for channel: {giveaway_data['channel']} and guild: {giveaway_data['guild']}"
                      f" for giveaway {message_id} with prize {giveaway_data['prize']} "
                      f" when trying to post giveaway winners.")
            return
        except HTTPException:
            log_entry(f"Unspecified error for channel: {giveaway_data['channel']} and guild: {giveaway_data['guild']}"
                      f" for giveaway {message_id} with prize {giveaway_data['prize']} "
                      f"when trying to post giveaway winners.")
            return

    async def create_giveaway(self, guild_id, channel_id, author_id, role_id, duration, winners, giveaway_prize):
        channel_obj = self.bot.get_channel(channel_id)
        if channel_obj is None:
            log_entry(f"Channel: {channel_id}"
                      f" could not be found during giveaway creation process.")
            return

        current_time = datetime.now(tz=UTC)

        winner_list = None

        author = self.bot.get_user(author_id)
        if author is None:
            log_entry(f"Error while attempting to get author during giveaway creation process "
                      f"with prize {giveaway_prize}, could not find author.")
            return

        role_obj = None
        if role_id != 0:
            guild_obj = self.bot.get_guild(guild_id)
            if guild_obj is None:
                log_entry(f"Error while attempting to fetch guild {guild_id} during giveaway creation process "
                          f"with prize {giveaway_prize}, could not find guild.")
                return
            guild_roles = guild_obj.roles

            role_obj = discord.utils.get(guild_roles, id=role_id)
            if role_obj is None:
                log_entry(f"Error while attempting to fetch role {role_id} during giveaway creation process "
                          f"with prize {giveaway_prize}, could not find role.")
                return

        embed = get_embed(giveaway_prize, author, role_obj, winners, current_time, duration, winner_list, current_time,
                          duration)

        giveaway_msg = await channel_obj.send(embed=embed)

        await giveaway_msg.add_reaction("🎉")

        new_giveaway_handler(giveaway_msg.id, guild_id, author_id, channel_id, role_id, int(current_time.timestamp()),
                             duration,
                             winners, giveaway_prize)

        test = self.bot.scheduler.add_job(self.complete_giveaway, "date",
                                   run_date=datetime.now(tz=UTC) + timedelta(seconds=duration),
                                   args=[giveaway_msg.id],
                                   id=str(giveaway_msg.id))


    @commands.hybrid_command(name='startgiveaway', description="Starts a giveaway.")
    @app_commands.describe(giveaway_prize="The prize you want to give away.",
                           giveaway_time="How long you want your giveaway to last for. Format: (Number)(Period) Ex. 15d for 15 days.",
                           giveaway_winners="How many winners you want there to be. Default 1",
                           giveaway_channel="What channel do you want to host your giveaway in? Defaults to current channel.",
                           giveaway_role="What role you wish to be required for the giveaway. (Optional)")
    @commands.has_role("Donor")
    async def startgiveaway(self, interaction: discord.Interaction, giveaway_prize: str, giveaway_time: str,
                            giveaway_winners: Optional[int],
                            giveaway_channel: Optional[str],
                            giveaway_role: Optional[str]):
        """
        Starts a giveaway with the given parameters.
        giveaway_prize: The prize you want to give away.
        giveaway_time: How long you want your giveaway to last for. Format: (Number)(Period) Ex. 15d for 15 days.
        giveaway_winners: How many winners you want there to be. Default 1
        giveaway_channel: What channel do you want to host your giveaway in? Defaults to current channel.
        giveaway_role: What role you wish to be required for the giveaway. (Optional)

        Requires the Donor role.
        """
        if len(giveaway_prize) > 255:
            await interaction.response.send_message("Length of prize is too long, please shorten it.")
            return

        if giveaway_winners is None:
            giveaway_winners = 1

        if giveaway_channel is None:
            giveaway_channel = interaction.channel_id

        if giveaway_winners > 50 or giveaway_winners < 1:
            await interaction.response.send_message("Invalid number of winners, max is 50 and minimum is 1.")
            return

        if giveaway_role is None:
            giveaway_role = 0

        giveaway_time = convert(giveaway_time)
        if not str(giveaway_time).isnumeric():
            await interaction.response.send_message(giveaway_time)
            return

        await self.create_giveaway(interaction.guild_id, int(giveaway_channel), interaction.user.id,
                                   int(giveaway_role), giveaway_time, giveaway_winners, giveaway_prize)

        await interaction.response.send_message(content="Successfully started giveaway.", ephemeral=True)

    @startgiveaway.error
    async def startgiveaway_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, CheckFailure):
            await interaction.response.send_message("You do not have the required permissions to run this command.",
                                                    ephemeral=True)

    @startgiveaway.autocomplete('giveaway_role')
    async def role_autocomplete(self, interaction: discord.Interaction, current: str) -> List[
        app_commands.Choice[str]]:
        return [app_commands.Choice(name=role.name, value=str(role.id)) for role in interaction.guild.roles if
                current.lower() in role.name.lower()][:10]

    @startgiveaway.autocomplete('giveaway_channel')
    async def channel_autocomplete(self, interaction: discord.Interaction, current: str) -> List[
        app_commands.Choice[str]]:
        return [app_commands.Choice(name=channel.name, value=str(channel.id)) for channel in
                interaction.guild.text_channels if
                current.lower() in channel.name.lower()][:10]

    async def cancel_giveaway(self, message_id):
        """Cancels giveaway by id."""
        try:
            giveaway_data = get_giveaway_data(message_id)

            channel_obj = self.bot.get_channel(giveaway_data['channel'])
            if channel_obj is None:
                log_entry(f"Channel: {giveaway_data['channel']} for giveaway {message_id}"
                          f" could not be found.")
                return

            try:
                message_obj = await channel_obj.fetch_message(message_id)
            except NotFound:
                log_entry(f"Message: {message_id}"
                          f" could not be found.")
                return
            except Forbidden:
                log_entry(f"Message: {message_id}"
                          f" has improper permissions.")
                return
            except HTTPException:
                log_entry(f"Message: {message_id}"
                          f" had an unspecified error while attempting to retrieve the message.")
                return

            try:
                await message_obj.delete()
            except Forbidden:
                log_entry(f"Improper permissions for channel: {giveaway_data['channel']} and message: {message_id}"
                          f" when trying to delete giveaway message.")
                return
            except NotFound:
                pass
            except HTTPException:
                log_entry(f"Unspecified error for channel: {giveaway_data['channel']} and message: {message_id}"
                          f" when trying to delete giveaway message.")
                return

            set_giveaway_complete(message_id)
            try:
                self.bot.scheduler.remove_job(str(message_id))
            except JobLookupError:
                pass

            return "Giveaway has been successfully cancelled."
        except KeyError:
            return "Could not a find a giveaway with that ID."

    @commands.hybrid_command(name='cancelgiveaway', description="Cancels the given giveaway.")
    @app_commands.describe(message_id="Message ID of the giveaway post")
    @commands.has_role("Donor")
    async def cancel_giveaway_cmd(self, ctx: commands.Context, message_id: str):
        """
        Immediately cancels and deletes the provided giveaway.

        Provide the message ID of the giveaway post.
        """
        await ctx.send(await self.cancel_giveaway(int(message_id)))

    @commands.hybrid_command(name='endgiveaway', description="Ends the given giveaway.")
    @app_commands.describe(message_id="Message ID of the giveaway post")
    @commands.has_role("Donor")
    async def end_giveaway(self, ctx: commands.Context, message_id: str):
        """
        Immediately ends and picks a winner for the provided giveaway.

        Provide the message ID of the giveaway post.
        """
        if return_statement := await self.complete_giveaway(int(message_id)):
            await ctx.send(return_statement)
        else:
            try:
                self.bot.scheduler.remove_job(str(message_id))
            except JobLookupError:
                pass

    @commands.hybrid_command(name='rerollgiveaway', description="Rerolls the given giveaway.")
    @app_commands.describe(message_id="Message ID of the giveaway post",
                           winners="Number of winners to roll for, default 1",
                           regen="Whether or not to regenerate the potential winner list, default false.")
    @commands.has_role("Donor")
    async def reroll_giveaway(self, ctx: commands.Context, message_id: str, winners: int = 1, regen: bool = False):
        """
        Rerolls the given giveaway, picking a new winner or winners.

        Provide the message ID of the giveaway post.

        Giveaways by default not pick a previous winner - reroll with regen true if you would like to regenerate the winner list.
        """
        try:
            giveaway = get_giveaway_data(int(message_id))
        except:
            await ctx.send("Could not find that post, make sure you have the right ID.")
            return

        users = None
        role = None
        if regen:
            if giveaway['role'] != 0:
                role = discord.utils.get(ctx.guild.roles, id=int(giveaway['role']))

            message_obj = await ctx.message.channel.fetch_message(message_id)

            reactions = message_obj.reactions

            users = [user async for user in reactions[0].users()]
        winner_list = get_giveaway_winners(role, winners, message_id, users)
        if winner_list[0] != 'No one!':
            await ctx.send(
                f"The new winner{' is' if winners == 1 else 's are'}: {chr(10).join(winner_list)}")
        else:
            await ctx.send(f"There is no one else able to be chosen!\n"
                           f"Reroll with regen true "
                           f"if you would like to regenerate the winner list.")

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        active_giveaways = get_active_giveaways()

        if payload.message_id in active_giveaways:
            message = await self.bot.get_channel(payload.channel_id).fetch_message(payload.message_id)

            disqualified = discord.utils.get(self.bot.get_guild(payload.guild_id).roles, name="Disqualified")

            giveaway_data = get_giveaway_data(payload.message_id)

            role = discord.utils.get(self.bot.get_guild(payload.guild_id).roles, id=giveaway_data['role'])

            if disqualified in payload.member.roles:
                await message.remove_reaction(payload.emoji, payload.member)

            if role is not None:
                if role not in payload.member.roles and not payload.member.bot:
                    await message.remove_reaction(payload.emoji, payload.member)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            giveaway_list = get_active_giveaways()

            for giveaway in giveaway_list:
                giveaway_data = get_giveaway_data(giveaway)
                current_time = datetime.now(tz=UTC)
                start_time = datetime.fromtimestamp(giveaway_data['start_time'], tz=UTC)

                if start_time + timedelta(seconds=giveaway_data['duration']) > current_time:
                    self.bot.scheduler.add_job(self.complete_giveaway, "date",
                                               run_date=start_time +
                                                        timedelta(seconds=giveaway_data['duration']),
                                               args=[giveaway],
                                               id=str(giveaway))
                else:
                    await self.complete_giveaway(giveaway)

            self.update_giveaway_posts.start()

            self.bot.cogs_ready.ready_up("Giveaway")


async def setup(bot):
    await bot.add_cog(Giveaway(bot))
