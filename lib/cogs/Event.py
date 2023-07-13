import asyncio
import bisect
import io
import mimetypes
from asyncio import sleep
from datetime import datetime
from typing import Optional

import aiohttp
import discord
import gspread as gspread
from discord import app_commands, Member, File
from discord.ext.commands import Cog, command


async def get_image_as_discord_file(url):
    """
    This function takes a URL as input and returns a discord.File object if the URL points to an image.
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                content_type = response.headers['Content-Type']
                if 'image' in content_type:
                    # We have a valid image URL. We'll download it and create a discord.File object
                    data = await response.read()  # Reads the image data

                    # Infer the file extension from the Content-Type
                    extension = mimetypes.guess_extension(content_type)
                    filename = f'image{extension}' if extension else 'image.png'

                    return discord.File(io.BytesIO(data), filename=filename)  # Creates a discord.File object

        except Exception as e:
            print(f"Error: {e}")

    # If we reached here, the URL was not an image or an error occurred.
    return None


def update_submission_embed(embed, member_mention, timestamp, members_selected, state):
    embed.add_field(name=f"**{state} By:**", value=member_mention, inline=True)
    embed.add_field(name=f"**{state} At:**", value=timestamp)

    embed.set_footer(text=f"{state}")
    embed.set_image(url=None)

    if state == "Accepted":
        embed.color = discord.Color.green()
    elif state == "Rejected":
        embed.color = discord.Color.red()

    embed.description = '\n'.join(members_selected)

    return embed


class Event(Cog):
    def __init__(self, bot):
        self.bot = bot

        gc = gspread.service_account()

        sh = gc.open("Relic Kindred V2.0 Test")

        self.participant_sheet = sh.worksheet("PARTICIPANTS")
        self.submission_sheet = sh.worksheet("SUBMISSIONS")

        self.event_submission_channel = self.bot.get_channel(1127706264743452722)
        self.event_log_channel = self.bot.get_channel(1127706277557043223)

        self.numbers = ['1️⃣', '2️⃣', '3️⃣', '4️⃣',
                        '5️⃣', '6️⃣', '7️⃣', '8️⃣',
                        '9️⃣', '🔟']

        self.reactions = ['✅', '❓', '❌'] + self.numbers

        self.team = ['--TL--Wisp.ES', '--TL--Guthix', 'Agnis', 'leaps.', '--TL--Sui', '--Q--RoboSt3alth']

    def get_submission_embed(self, team, team_members, submitter, ign, points, image_file):
        embed = discord.Embed(title="Event Submission",
                              description=team_members,
                              color=discord.Color.orange())

        embed.add_field(name="**Team:**", value=team, inline=True)
        embed.add_field(name="**Submitter:**", value=submitter, inline=True)
        embed.add_field(name="**IGN:**", value=ign, inline=True)
        embed.add_field(name="**Points:**", value=points, inline=True)

        embed.set_image(url=f"attachment://{image_file.filename}")
        return embed

    async def add_reactions(self, message, num_reactions):
        for reaction in self.reactions[:num_reactions + 3]:
            await message.add_reaction(reaction)

    def get_team_string(self, team_members):
        return '\n'.join(f"{self.numbers[i]}    {member}" for i, member in enumerate(team_members))

    @app_commands.command(name='rego', description="Register for the upcoming event.")
    @app_commands.describe(event_partner="Who do you want your partner to be? "
                                         "If not chosen, a random one will be assigned.")
    async def event_registration(self, interaction: discord.Interaction, event_partner: Optional[Member]):
        current_participants = self.participant_sheet.get_all_records()

        registering_user = interaction.user.name
        registering_user_id = str(interaction.user.id)

        duo_partner = ""
        duo_partner_id = ""
        if event_partner is not None:
            duo_partner = event_partner.name
            duo_partner_id = str(event_partner.id)

        response_message = ""
        if registering_user_id == duo_partner_id:
            response_message = "You cannot register with yourself."
        else:
            for index, participant in enumerate(current_participants):
                if str(participant['User ID']) == registering_user_id:
                    if str(participant['Duo ID']) == duo_partner_id:
                        response_message = f"You are already registered{' with that duo partner.' if duo_partner else '.'}" \
                                           f" If you wish to change your duo partner, " \
                                           f"please register again and choose a different one."
                        break
                    else:
                        # Create a list of lists to match the cell structure
                        values = [[duo_partner, duo_partner_id]]

                        # Get the cell range
                        range_to_update = f'C{index + 2}:D{index + 2}'

                        # Update the cells
                        self.participant_sheet.update(range_to_update, values)

                        response_message = f"You have successfully updated your duo partner to " \
                                           f"{duo_partner + '  Reminder, your duo partner has to register and choose you as well' if duo_partner else 'be no one'}."

            if not response_message:
                self.participant_sheet.append_row([registering_user, registering_user_id, duo_partner, duo_partner_id])

                response_message = f"You have successfully registered for the event with" \
                                   f"{' ' + duo_partner + '. Reminder, your duo partner has to register and choose you as well.' if duo_partner else 'out a partner. A partner will be assigned to you later on.'}" \
                                   f" If you wish to change your duo partner, simply register again and choose a different person."

        await interaction.response.send_message(content=response_message, ephemeral=True)

    @command(name="submitrun")
    async def submit_run(self, ctx, points: int, image_url: Optional[str]):
        await ctx.message.delete()

        max_points = 108
        min_points = 1
        team_members = self.get_team_string(self.team)
        team = "Team"
        submitter = ctx.author.mention
        ign = "--TL--Guthix"

        if image_url is None and not (ctx.message.attachments and 'image' in ctx.message.attachments[0].content_type):
            await ctx.send("No image detected.", delete_after=5)
            return

        if min_points < 1 or points > max_points:
            await ctx.send(
                "Invalid point total, ensure you have the correct points, only include the individual point amount, "
                "not your team amount.\n"
                "Reminder: 2 points for most rares, "
                "1 point for limbo/chroma/mesa and their respective weapons. 1 bonus point for double rare, "
                "10 bonus points for triple rare, 100 bonus points for quad rare.", delete_after=10)
            return

        if image_url:
            log_image_file = await get_image_as_discord_file(image_url)
            if log_image_file is None:
                await ctx.send("Invalid image URL.", delete_after=5)
                return

        else:
            image = ctx.message.attachments[0]
            if 'image' not in image.content_type:
                await ctx.send("No image detected.", delete_after=5)
                return

            log_image_file = await image.to_file()

        submission_embed = self.get_submission_embed(team, team_members, submitter, ign, points, log_image_file)

        log_msg = await self.event_log_channel.send(embed=submission_embed,
                                                    file=log_image_file)

        submission_embed.add_field(name="**Log Message:**", value=log_msg.jump_url, inline=True)

        submission_embed.set_image(url=log_msg.embeds[0].image.url)

        submission_msg = await self.event_submission_channel.send(embed=submission_embed)

        await self.add_reactions(submission_msg, 6)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.event_submission_channel = self.bot.get_channel(1127706264743452722)
            self.event_log_channel = self.bot.get_channel(1127706277557043223)
            self.bot.cogs_ready.ready_up("Event")

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.is_custom_emoji() \
                or payload.member.bot \
                or payload.channel_id != self.event_submission_channel.id \
                or payload.emoji.name not in self.reactions[:3]:
            return

        message = await self.event_submission_channel.fetch_message(payload.message_id)
        team, submitter, ign, points, log_message_id = (field.value for field in message.embeds[0].fields)
        image_url = message.embeds[0].image.url

        emojis = [i - 2 for i, x in enumerate(message.reactions) if
                  x.count > 1 and x.emoji not in self.reactions[:3]]

        log_message = await self.event_log_channel.fetch_message(int(log_message_id.split('/')[-1]))
        log_message_embed: discord.Embed = log_message.embeds[0]

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %I:%M:%S %p UTC")

        submitter_number = self.team.index(ign)

        if submitter_number not in emojis:
            bisect.insort(emojis, submitter_number)

        members_selected = [x for i, x in enumerate(self.team, start=1) if i in emojis]

        if len(members_selected) > 4:
            await self.event_submission_channel.send("You have too many members selected, "
                                                     "make sure you only select the people in the squad.",
                                                     delete_after=5)
            return

        members_selected += ['N/A'] * (4 - len(members_selected))
        member_mention = payload.member.mention

        if payload.emoji.name == self.reactions[0]:
            row = [team, points, image_url] + members_selected + [timestamp]
            self.submission_sheet.insert_row(row, len(self.submission_sheet.col_values(1)) + 1)

            update_submission_embed(log_message_embed, member_mention, timestamp, members_selected, "Accepted")

            await log_message.edit(embed=log_message_embed)
            await message.delete()
        elif payload.emoji.name == self.reactions[1]:
            new_points = None
            msg = await self.event_submission_channel.send("Enter the corrected point total...", delete_after=60)
            try:
                new_points = await self.bot.wait_for('message', check=lambda m: m.author == payload.member,
                                                     timeout=60)
            except asyncio.TimeoutError:
                await self.event_submission_channel.send("Timed out, try again.", delete_after=5)
                return
            finally:
                await msg.delete()

            await new_points.delete()

            if new_points is None or not new_points.content.isdigit():
                await self.event_submission_channel.send("Invalid point total, please try again.", delete_after=5)
                return

            new_points = int(new_points.content)
            log_message_embed.set_field_at(3, name="**Points:**", value=new_points, inline=True)
            message.embeds[0].set_field_at(3, name="**Points:**", value=new_points, inline=True)

            await log_message.edit(embed=log_message_embed)
            await message.edit(embed=message.embeds[0])
            await message.remove_reaction(payload.emoji, payload.member)
        elif payload.emoji.name == self.reactions[2]:
            update_submission_embed(log_message_embed, member_mention, timestamp, members_selected, "Rejected")
            await log_message.edit(embed=log_message_embed)
            await message.delete()


async def setup(bot):
    await bot.add_cog(Event(bot))
