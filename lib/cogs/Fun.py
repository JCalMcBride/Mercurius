import json
import os
import random
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from random import choice, shuffle
from typing import Optional

import discord
from PIL import Image, ImageFont, ImageDraw
from aiohttp import request
from discord import File, Member, Embed, app_commands
from discord.ext import commands
from discord.ext.commands import command, Cog
from discord.utils import escape_markdown
from simpleeval import simple_eval

with open('lib/data/misc_bot_data.json') as f:
    misc_bot_data = json.load(f)


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def evaluate_expression(expression):
    if expression.lower().replace(" ", "") in misc_bot_data['special_answers']:
        answer = misc_bot_data['special_answers'][expression.lower().replace(" ", "")]
    else:
        try:
            answer = simple_eval(expression.replace("^", "**"))
        except Exception as e:
            answer = None

    if answer is not None:
        if is_number(answer):
            answer = '{:,}'.format(answer)
        else:
            answer = str(answer)

    return f"The answer to the expression {escape_markdown(expression)} " \
           f"{'is ' + '**' + answer + '**' if answer is not None else 'could not be found, make sure you entered it correctly.'}"


def no_botspam_cooldown(interaction: discord.Interaction) -> Optional[app_commands.Cooldown]:
    if interaction.channel.name == 'bot-spam':
        return None
    return app_commands.Cooldown(3, 60)


class Fun(Cog, name="fun"):
    def __init__(self, bot):
        self.bot = bot
        self.frog_images = None
        with open('lib/data/filelist.json') as f:
            self.frog_images = json.load(f)

        self.allowed_channels = [780377679227650079, 1089587184987811961]

    @commands.hybrid_command(name='hello', description="Says hello",
                             aliases=['hi', 'hey'])
    @app_commands.checks.cooldown(1, 5)
    async def say_hello(self, ctx: commands.Context):
        """Says hello!"""
        await ctx.send(f"Hello {ctx.author.mention}!")

    @commands.hybrid_command(name='goodbye', description="Says goodbye",
                             aliases=['bye'])
    @app_commands.checks.cooldown(1, 5)
    async def say_goodbye(self, ctx: commands.Context):
        """Says goodbye!"""
        await ctx.send(f"Goodbye {ctx.author.mention}!")

    @commands.hybrid_command(name='signgen',
                             description="Creates a sign with the given text. Default is {person} is cute!",
                             aliases=['cutegen', 'sign'])
    @app_commands.checks.dynamic_cooldown(no_botspam_cooldown)
    async def cute_gen(self, ctx: commands.Context, person: str, adjective: Optional[str], verb: Optional[str],
                       text_size: Optional[int]):
        """
        Creates a sign with the given text. Default is {person} is cute!
        """
        if adjective is None:
            adjective = "cute!"

        if verb is None:
            verb = "is"

        if text_size is None:
            text_size = 22

        img = Image.open("lib/data/misc/signblank.png")
        fnt = ImageFont.truetype("lib/data/misc/arial-bold.ttf", text_size)
        d = ImageDraw.Draw(img)
        d.text((2, 0), person, font=fnt, fill=(0, 0, 0))
        d.text((10, 25), f"{verb} {adjective}", font=fnt, fill=(0, 0, 0))
        b = BytesIO()
        img.save(b, "PNG")
        b.seek(0)

        await ctx.send(file=File(fp=b, filename="image.png"))

    @command(name="rank",
             hidden=True)
    async def get_rank(self, ctx, *, args):
        """Test command."""
        if "add Test --role Peacekeeper" in args:
            await ctx.send(f"{ctx.author.mention} Role added to list of join-able roles")
        elif "join Test" in args:
            await ctx.send(f"{ctx.author.mention} 👍")

    @command(name="supporter")
    @commands.has_role(1086352745390419968)
    async def supporter_command(self, ctx):
        """Thanks VRC's supporters!"""
        heart_list = ["<:pepeheart:780599565039697981>", "<:jaxheart:780515012279402536>", "❤️", "💙", "💚", "💛", "💜"]
        await ctx.send(f"{ctx.author.mention} Thanks for supporting VRC! {choice(heart_list)}")

    @command(name="credits")
    async def credits_command(self, ctx):
        """
        Shows the credits for the bot.
        """
        heart_list = ["<:pepeheart:780599565039697981>", "<:jaxheart:780515012279402536>", "❤️", "💙", "💚", "💛", "💜"]
        guthix = await self.bot.fetch_user(585035501929758721)
        rav = await self.bot.fetch_user(113361399727558656)
        mojober = await self.bot.fetch_user(492255815160430593)
        snap = await self.bot.fetch_user(148706546308612096)
        robo = await self.bot.fetch_user(166903506551177216)

        supporter_role = self.bot.get_guild(780376195182493707).get_role(1086352745390419968)
        patrons = [await self.bot.fetch_user(182359932518006794),
                   await self.bot.fetch_user(137365776121200650)]

        emoji_dict = {419095972568891403: "<:Sui:1097540744958459977>",
                      137914401658241024: "<:Hathena:1097540748557160508>",
                      326726258102632448: "<:Wholesuhm:1117337992353296455>",
                      182359932518006794: "<:Azz:1108081401644990545>",
                      137365776121200650: "<:Morbid:1108416979548782683>",
                      111156393049866240: "<:Jt10x:1108416978261135475>",
                      107317852612075520: "<:TheKappaChrist:1117338005150109826>",
                      355712978462572544: "<:voidge:1226996241628401726>",
                      280792322134900737: "<:baran:1135263593332494368>",
                      328145199845081088: "🐢",
                      281471947177459712: "<:silvaandaege:1124178791665766410>",
                      474458695351402497: "<a:catkiss:1226994912315183145>",
                      715200888217534475: "<:jolyrno:1246045514336833548>",
                      991633609511415849: "<:ahsoka:1246046592151195679>"}

        for supporter in supporter_role.members + patrons:
            if supporter.id in emoji_dict:
                continue

            emoji_dict[supporter.id] = random.choice(heart_list)

        supporter_string = '\n'.join([f"{member.mention} {emoji_dict[member.id]}" for member in supporter_role.members + patrons])


        content = f"Bot designed and coded by {guthix.mention}\n" \
                  f"Logo by {mojober.mention} Thank you! {random.choice(heart_list)}\n" \
                  f"Name/Design Help by {rav.mention} Thank you! {random.choice(heart_list)}\n" \
                  f"Special thanks to {snap.mention} and {robo.mention}\n\n\n" \
                  f"Thank you to all of my supporters and patrons!\n" \
                  f"{supporter_string}"

        embed = discord.Embed(description=content, color=0xb90000)
        embed.set_author(name="Mercurius", icon_url=self.bot.user.display_avatar.url)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='cringe', description="CRINGE.")
    async def get_cringe(self, ctx: commands.Context):
        """Shows a random cringe video."""
        await ctx.send(choice(misc_bot_data['cringe_list']))

    @commands.hybrid_command(name='pat', description="pat people :)")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def pat_command(self, ctx: commands.Context):
        """pat people :)"""
        pat_list = [x for x in ctx.guild.emojis if x.name.lower().startswith("pat")]
        if not pat_list:
            await ctx.send("No pat emojis found.", delete_after=5)
            return
        await ctx.send(choice(pat_list))

    @commands.hybrid_command(
        name='raiserevenantprice',
        description="Raises the revenant price by 0.1",
        aliases=['raiserevprice', 'raise_rev_price', 'raise-rev-price']
    )
    @app_commands.checks.cooldown(1, 120)
    @commands.cooldown(1, 120, commands.BucketType.user)
    async def raise_revenant_price(self, ctx: commands.Context):
        """Raises the revenant price counter by 0.1"""
        if ctx.channel.id not in self.allowed_channels:
            await ctx.send("This command cannot be used in this channel.", delete_after=5, ephemeral=True)
            return

        price_file = 'lib/data/revenant_price.json'

        try:
            if os.path.exists(price_file):
                with open(price_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {'price': 60.0}

            data['price'] = round(data['price'] + 0.1, 1)

            with open(price_file, 'w') as f:
                json.dump(data, f, indent=4)

            try:
                await ctx.message.delete(delay=1)
            except discord.Forbidden:
                pass

            await ctx.send(f"Revenant price raised to **{data['price']}**", delete_after=5)
        except Exception as e:
            await ctx.send(f"Error updating price: {e}")

    @commands.hybrid_command(
        name='lowerrevenantprice',
        description="Lowers the revenant price by 0.1",
        aliases=['lowerrevprice', 'lower_rev_price', 'lower-rev-price']
    )
    @app_commands.checks.cooldown(1, 120)
    @commands.cooldown(1, 120, commands.BucketType.user)
    async def lower_revenant_price(self, ctx: commands.Context):
        """Lowers the revenant price counter by 0.1"""
        if ctx.channel.id not in self.allowed_channels:
            await ctx.send("This command cannot be used in this channel.", delete_after=5, ephemeral=True)
            return

        price_file = 'lib/data/revenant_price.json'

        try:
            if os.path.exists(price_file):
                with open(price_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {'price': 60.0}

            data['price'] = round(max(0.0, data['price'] - 0.1), 1)

            with open(price_file, 'w') as f:
                json.dump(data, f, indent=4)

            try:
                await ctx.message.delete(delay=1)
            except discord.Forbidden:
                pass

            await ctx.send(f"Revenant price lowered to **{data['price']}**", delete_after=5)
        except Exception as e:
            await ctx.send(f"Error updating price: {e}")

    @commands.hybrid_command(name='extremelyconcerning', description="When something is just..too concerning.")
    async def extremely_concerning(self, ctx: commands.Context):
        """extremely concerning."""
        shuffle(misc_bot_data['concerning_list'])
        await ctx.send(f"{''.join(misc_bot_data['concerning_list'][:3])}\n"
                       f"{''.join(misc_bot_data['concerning_list'][3:])}")

    @commands.hybrid_command(name='ping', description="Ping pong!")
    @app_commands.checks.dynamic_cooldown(no_botspam_cooldown)
    async def ping(self, ctx: commands.Context, target: Optional[Member]):
        """Ping pong!"""
        if target:
            target = target.mention
        else:
            target = ctx.author.mention
        msg = await ctx.send(f"+!Pong {target}!", ephemeral=True)
        current_time = datetime.now()
        if ctx.interaction:
            ping = current_time.timestamp() - ctx.interaction.created_at.timestamp()
        else:
            ping = current_time.timestamp() - ctx.message.created_at.timestamp()
        await msg.edit(content=f"+!Pong {target}! Latency: `{round(ping * 1000)}ms`")

    @commands.hybrid_command(name='ban', description="The ban hammer.")
    @app_commands.checks.dynamic_cooldown(no_botspam_cooldown)
    async def ban_cmd(self, ctx: commands.Context, target: Optional[Member]):
        """The ban hammer."""
        if target:
            target = target.mention
        else:
            target = ctx.author.mention
        await ctx.send(f"User {target} has been banned.")

    @commands.hybrid_command(name='unban', description="The unban hammer.")
    @app_commands.checks.dynamic_cooldown(no_botspam_cooldown)
    async def unban_cmd(self, ctx: commands.Context, target: Optional[Member]):
        """The unban hammer."""
        if target:
            target = target.mention
        else:
            target = ctx.author.mention
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass
        await ctx.send(f"User {target} has been unbanned.")

    @commands.hybrid_command(name='hug', description="Hug someone <3.")
    @app_commands.checks.dynamic_cooldown(no_botspam_cooldown)
    async def hug_cmd(self, ctx: commands.Context, target: Optional[Member]):
        """Hug someone <3."""
        if target:
            target = target.mention
        else:
            target = ctx.author.mention
        await ctx.send(f"User {target} has been hugged. <:pepeheart:780599565039697981>")

    @commands.hybrid_command(name='say', description="Echoes whatever text was given in embed format.")
    @app_commands.checks.cooldown(1, 5)
    async def echo_message(self, ctx: commands.Context, echoed_message: str):
        """Echoes whatever text was given in embed format."""
        if ctx.interaction is None:
            echoed_message = ctx.message.content.split(maxsplit=1)[1]
        await ctx.send(embed=Embed(title="", description=echoed_message))

    @commands.hybrid_command(name='calculate', description="Calculates the given expression.", aliases=["calc"])
    @app_commands.checks.cooldown(1, 5)
    async def calc_expression(self, ctx: commands.Context, expression: str):
        """Calculates mathematical expressions! (Thanks zach..)"""
        if ctx.interaction is None:
            expression = ctx.message.content.split(maxsplit=1)[1]
        answer = await self.bot.loop.run_in_executor(ThreadPoolExecutor(), evaluate_expression, expression)
        await ctx.send(answer)

    @command(name="becomeselfaware", aliases=["selfaware"], hidden=True)
    async def self_aware(self, ctx):
        """error"""
        await ctx.message.delete()
        await ctx.send("Jokes on you.. I'm already self aware..", delete_after=2)

    async def get_image(self, ctx: commands.Context, url: str, data_type: str = "json"):
        async with request("GET", url, headers={}) as response:
            if response.status == 200:
                data = await response.read()
                return json.loads(data)
            else:
                await ctx.send("Could not receive image, please try again later.")

    @commands.hybrid_command(name='dog', description="Display a random dog.")
    @app_commands.checks.cooldown(1, 5)
    async def dog_picture(self, ctx: commands.Context):
        """Sends an image of a random dog."""
        data = await self.get_image(ctx, "https://dog.ceo/api/breeds/image/random")
        if data:
            await ctx.send(data["message"])

    @commands.hybrid_command(name='capybara', description="Display a random capybara.")
    @app_commands.checks.cooldown(1, 5)
    async def capybara_picture(self, ctx: commands.Context):
        """Sends an image of a random capybara."""
        data = await self.get_image(ctx, "https://api.capy.lol/v1/capybara?json=true")
        if data:
            await ctx.send(data['data']["url"])

    @commands.hybrid_command(name='bunny', description="Display a random bunny.")
    @app_commands.checks.cooldown(1, 5)
    async def bunny_picture(self, ctx: commands.Context):
        """Sends an image of a random bunny."""
        data = await self.get_image(ctx, "https://api.bunnies.io/v2/loop/random/?media=gif,png")
        if data:
            await ctx.send(data['media']["gif"])

    @commands.hybrid_command(name='cat', description="Display a random cat.")
    @app_commands.checks.cooldown(1, 5)
    async def cat_picture(self, ctx: commands.Context):
        """Sends an image of a random cat."""
        data = await self.get_image(ctx, "https://api.thecatapi.com/v1/images/search")
        if data:
            await ctx.send(data[0]["url"])

    @commands.hybrid_command(name='fox', description="Display a random fox.")
    @app_commands.checks.cooldown(1, 5)
    async def fox_picture(self, ctx: commands.Context):
        """Sends an image of a random fox."""
        data = await self.get_image(ctx, "https://randomfox.ca/floof/?ref=public-apis")
        if data:
            await ctx.send(data["image"])

    @commands.hybrid_command(name='panda', description="Display a random panda.")
    @app_commands.checks.cooldown(1, 5)
    async def panda_picture(self, ctx: commands.Context):
        """Sends an image of a random panda."""
        data = await self.get_image(ctx, "https://some-random-api.com/animal/panda")
        if data:
            await ctx.send(data["image"])

    @commands.hybrid_command(name='redpanda', description="Display a random panda.")
    @app_commands.checks.cooldown(1, 5)
    async def red_panda_picture(self, ctx: commands.Context):
        """Sends an image of a random panda."""
        data = await self.get_image(ctx, "https://some-random-api.com/animal/red_panda")
        if data:
            await ctx.send(data["image"])

    @commands.hybrid_command(name='racoon', description="Display a random panda.")
    @app_commands.checks.cooldown(1, 5)
    async def racoon_picture(self, ctx: commands.Context):
        """Sends an image of a random panda."""
        data = await self.get_image(ctx, "https://some-random-api.com/animal/racoon")
        if data:
            await ctx.send(data["image"])

    @commands.hybrid_command(name='koala', description="Display a random panda.")
    @app_commands.checks.cooldown(1, 5)
    async def koala_picture(self, ctx: commands.Context):
        """Sends an image of a random panda."""
        data = await self.get_image(ctx, "https://some-random-api.com/animal/koala")
        if data:
            await ctx.send(data["image"])

    @commands.hybrid_command(name='kangaroo', description="Display a random panda.")
    @app_commands.checks.cooldown(1, 5)
    async def kangaroo_picture(self, ctx: commands.Context):
        """Sends an image of a random panda."""
        data = await self.get_image(ctx, "https://some-random-api.com/animal/kangaroo")
        if data:
            await ctx.send(data["image"])

    @commands.hybrid_command(name='whale', description="Display a random panda.")
    @app_commands.checks.cooldown(1, 5)
    async def whale_picture(self, ctx: commands.Context):
        """Sends an image of a random panda."""
        data = await self.get_image(ctx, "https://some-random-api.com/animal/whale")
        if data:
            await ctx.send(data["image"])

    @commands.hybrid_command(name='duck', description="Display a random duck.")
    @app_commands.checks.cooldown(1, 5)
    async def duck_picture(self, ctx: commands.Context):
        """Sends an image of a random duck."""
        data = await self.get_image(ctx, "https://random-d.uk/api/v2/random")
        if data:
            await ctx.send(data["url"])

    @commands.hybrid_command(name='frog', description="Display a random frog.")
    @app_commands.checks.cooldown(1, 5)
    async def frog_picture(self, ctx: commands.Context):
        """Sends an image of a random frog."""
        url = random.choice(self.frog_images)
        await ctx.send(url['url'])

    def get_image_file(self, image_type):
        if image_type == "bird":
            bird_type = random.choice(os.listdir("lib/data/images/birds"))
            bird_image = random.choice(os.listdir(f"lib/data/images/birds/{bird_type}"))
            return f"lib/data/images/birds/{bird_type}/{bird_image}"

    @commands.hybrid_command(name='bird', description="Display a random bird.")
    @app_commands.checks.cooldown(1, 5)
    async def bird_picture(self, ctx: commands.Context):
        """Sends an image of a random bird."""
        file_path = self.get_image_file("bird")
        await ctx.send(file=File(file_path, filename="image.png"))

    @commands.hybrid_command(
        name='buymercoin',
        description="Buy exactly 1 mercoin and see your total.",
        aliases=['buy_mercoin', 'buy-mercoin']
    )
    @app_commands.checks.cooldown(1, 30)
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def buy_mercoin(self, ctx: commands.Context):
        """
        Gives the invoking user exactly 1 mercoin and reports their total.
        Requires the bot to have a database instance at self.bot.db supporting add_mercoins/get_mercoins.
        """
        if ctx.interaction is None:
            await ctx.message.delete(delay=1)

        db = getattr(self.bot, 'database', None)
        if db is None or not hasattr(db, 'add_mercoins') or not hasattr(db, 'get_mercoins'):
            await ctx.send("Database is not configured for mercoins.", delete_after=10)
            return

        user_id = ctx.author.id
        try:
            if hasattr(db, 'user_exists') and hasattr(db, 'create_user'):
                if not db.user_exists(user_id):
                    db.create_user(user_id)
            db.add_mercoins(user_id, 1)  # increment by exactly 1
            total = db.get_mercoins(user_id)
        except Exception:
            await ctx.send("There was an error processing your mercoin purchase.", delete_after=10)
            return

        await ctx.send(
            f"{ctx.author.mention} purchased **1** mercoin. "
            f"You now have **{total}** mercoin{'s' if total != 1 else ''}."
            f"You will be invoiced **${total:.2f}** when mercoin officially launches. Thank you.", delete_after=10
        )

    @commands.hybrid_command(
        name='stealmercoin',
        description="You wouldn't....",
        aliases=['steal_mercoin', 'steal-mercoin']
    )
    @app_commands.checks.cooldown(1, 30)
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def steal_mercoin(self, ctx: commands.Context, target: Optional[Member]):
        """
        Has a 50% chance to steal exactly 1 mercoin from the target user and gives it to the invoking user.
        Requires the bot to have a database instance at self.bot.db supporting add_mercoins/get_mercoins.
        50% chance to fail and lose 1 mercoin instead.
        50% chance to succeed and steal 1 mercoin from the target user.
        """
        if ctx.interaction is None:
            await ctx.message.delete(delay=1)

        if "<@" in ctx.message.content:
            await ctx.send("You are only allowed to target members by their ID, server name, or username.", delete_after=10)
            return

        db = getattr(self.bot, 'database', None)
        if db is None or not hasattr(db, 'add_mercoins') or not hasattr(db, 'get_mercoins'):
            await ctx.send("Database is not configured for mercoins.", delete_after=10)
            return

        user_id = ctx.author.id
        try:
            if hasattr(db, 'user_exists') and hasattr(db, 'create_user'):
                if not db.user_exists(user_id):
                    db.create_user(user_id)

            if target is None or target.id == ctx.author.id:
                await ctx.send("You cannot steal from yourself.", delete_after=10)
                return

            if target is not None and hasattr(db, 'user_exists') and hasattr(db, 'create_user'):
                if not db.user_exists(target.id) or not db.get_mercoins(target.id):
                    await ctx.send("Target user does not have any mercoins to steal.", delete_after=10)
                    return

            if db.get_mercoins(user_id) < 1:
                await ctx.send("You need at least 1 mercoin to attempt a theft.", delete_after=10)
                return

            if random.random() < 0.5:
                db.remove_mercoins(target.id, 1)  # remove 1 from target
                db.add_mercoins(user_id, 1)
                success = True
            else:
                db.remove_mercoins(user_id, 1)  # remove 1 from self
                db.add_mercoins(target.id, 1)  # give 1 to target
                success = False
            total = db.get_mercoins(user_id)
        except Exception:
            await ctx.send("There was an error processing your mercoin purchase.", delete_after=10)
            return

        await ctx.send(
            f"{ctx.author.mention} {'successfully stole 1 mercoin from ' + target.display_name if success else 'failed and lost 1 mercoin to ' + target.display_name}. "
            f"You now have **{total}** mercoin{'s' if total != 1 else ''}."
            f"You will be invoiced **${total:.2f}** when mercoin officially launches. Thank you.", delete_after=10
        )

    @commands.hybrid_command(
        name='mercoinleaderboard',
        description="Shows the top mercoin holders.",
        aliases=['mercoin_leaderboard', 'mercoin-leaderboard', 'mlb']
    )
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def mercoin_leaderboard(self, ctx: commands.Context):
        db = getattr(self.bot, 'database', None)
        if db is None or not hasattr(db, 'get_mercoins'):
            await ctx.send("Database is not configured for mercoins.", delete_after=10)
            return

        # Fetch all users and their mercoin counts
        query = "SELECT user_id, amount FROM mercoins ORDER BY amount DESC"
        results = db._execute_query(query, fetch='all')
        leaderboard = [(user_id, amount) for user_id, amount in results]

        user_list, rank, last_amount = [], 0, None
        user_in_list = False
        ctx_user_id = ctx.author.id

        for i, (user_id, amount) in enumerate(leaderboard, 1):
            if amount != last_amount:
                rank = i

            user = self.bot.get_user(user_id)
            user_display = user.mention if user else str(user_id)

            if ctx_user_id == user_id:
                user_in_list = True
                if i > 10:
                    user_list.append(["...", "...", "..."])
                user_list.append([f"**{rank}**", f"**{user_display}**", f"**{'{:,}'.format(amount)}**"])
            elif i <= 10:
                user_list.append([rank, user_display, f"{'{:,}'.format(amount)}"])

            last_amount = amount

            if i >= 10 and user_in_list:
                break

        embed = discord.Embed(title="Mercoin Leaderboard", colour=discord.Colour.gold())
        embed.add_field(name="Rank", value='\n'.join([str(user[0]) for user in user_list]), inline=True)
        embed.add_field(name="User", value='\n'.join([str(user[1]) for user in user_list]), inline=True)
        embed.add_field(name="Mercoins", value='\n'.join([str(user[2]) for user in user_list]), inline=True)

        await ctx.send(embed=embed)

    @Cog.listener()
    async def on_ready(self):
        # Auto-initialize schema on first startup (idempotent)
        db = getattr(self.bot, 'database', None)
        if db and hasattr(db, 'maybe_initialize_schema'):
            try:
                db.maybe_initialize_schema()
            except Exception:
                # Avoid blocking startup if migration fails; admin command can repair.
                pass

        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Fun")


async def setup(bot):
    await bot.add_cog(Fun(bot))
