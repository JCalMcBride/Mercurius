import json
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


class Fun(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.frog_images = None
        with open('lib/data/filelist.json') as f:
            frog_images = json.load(f)

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
                             aliases=['cutegen'])
    @app_commands.checks.dynamic_cooldown(no_botspam_cooldown)
    async def cute_gen(self, ctx: commands.Context, person: str, adjective: Optional[str], verb: Optional[str],
                       text_size: Optional[int]):
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

    @command(name="rank")
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
        """Mercurius credits"""
        heart_list = ["<:pepeheart:780599565039697981>", "<:jaxheart:780515012279402536>", "❤️", "💙", "💚", "💛", "💜"]
        guthix = self.bot.fetch_user(585035501929758721)
        rav = self.bot.fetch_user(113361399727558656)
        mojober = self.bot.fetch_user(492255815160430593)
        snap = self.bot.fetch_user(148706546308612096)

        supporter_role = self.bot.get_guild(780376195182493707).get_role(1086352745390419968)
        patrons = [self.bot.fetch_user(182359932518006794),
                   self.bot.fetch_user(137365776121200650),
                   self.bot.fetch_user(474458695351402497)]

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
                      474458695351402497: "<a:catkiss:1226994912315183145>",}

        for supporter in supporter_role.members + patrons:
            if supporter.id in emoji_dict:
                continue

            emoji_dict[supporter.id] = random.choice(heart_list)

        supporter_string = '\n'.join([f"{member.mention} {emoji_dict[member.id]}"
                                      for member in supporter_role.members + patrons])

        content = f"Bot designed and coded by {guthix.mention}\n" \
                  f"Logo by {mojober.mention} Thank you! {random.choice(heart_list)}\n" \
                  f"Name/Design Help by {rav.mention} Thank you! {random.choice(heart_list)}\n" \
                  f"Special thanks to {snap.mention}\n\n\n" \
                  f"Thank you to all of my supporters and patrons!\n" \
                  f"{supporter_string}"

        embed = discord.Embed(description=content, color=0xb90000)
        embed.set_author(name="Mercurius", icon_url=self.bot.user.display_avatar.url)

        await ctx.send(embed=embed)

    @command(name="shesh")
    async def shesh(self, ctx):
        """Shesh."""
        await ctx.message.delete()
        await ctx.send(f"{ctx.author.mention} shesh (1)")
        await ctx.send("<:sheesh:895290930595254343>")

    @commands.hybrid_command(name='cringe', description="CRINGE.")
    async def get_cringe(self, ctx: commands.Context):
        """CRINGE."""
        await ctx.send(choice(misc_bot_data['cringe_list']))

    @commands.hybrid_command(name='pat', description="pat people :)")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def pat_command(self, ctx: commands.Context):
        """pat people :)"""
        pat_list = [x for x in ctx.guild.emojis if x.name.lower().startswith("pat")]
        await ctx.send(choice(pat_list))

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
        await ctx.send(embed=Embed(title="", description=echoed_message))

    @commands.hybrid_command(name='calculate', description="Calculates the given expression.", aliases=["calc"])
    @app_commands.checks.cooldown(1, 5)
    async def calc_expression(self, ctx: commands.Context, expression: str):
        """Calculates mathematical expressions! (Thanks zach..)"""
        if ctx.interaction is None:
            expression = ctx.message.content.split(maxsplit=1)[1]

        answer = await self.bot.loop.run_in_executor(ThreadPoolExecutor(), evaluate_expression, expression)

        await ctx.send(answer)

    @command(name="becomeselfaware", aliases=["selfaware"])
    async def self_aware(self, ctx):
        """error"""
        await ctx.message.delete()
        await ctx.send("Jokes on you.. I'm already self aware..", delete_after=2)

    @commands.hybrid_command(name='dog', description="Display a random dog.")
    @app_commands.checks.cooldown(1, 5)
    async def dog_picture(self, ctx: commands.Context):
        """Sends an image of a random dog."""
        url = "https://dog.ceo/api/breeds/image/random"

        async with request("GET", url, headers={}) as response:
            if response.status == 200:
                data = await response.json()

                await ctx.send(data["message"])
            else:
                await ctx.send("Could not receive image, please try again later.")

    @commands.hybrid_command(name='capybara', description="Display a random capybara.")
    @app_commands.checks.cooldown(1, 5)
    async def capybara_picture(self, ctx: commands.Context):
        """Sends an image of a random capybara."""
        url = "https://api.capy.lol/v1/capybara?json=true"

        async with request("GET", url, headers={}) as response:
            if response.status == 200:
                data = await response.json()

                await ctx.send(data['data']["url"])
            else:
                await ctx.send("Could not receive image, please try again later.")

    @commands.hybrid_command(name='bunny', description="Display a random bunny.")
    @app_commands.checks.cooldown(1, 5)
    async def bunny_picture(self, ctx: commands.Context):
        """Sends an image of a random bunny."""
        url = "https://api.bunnies.io/v2/loop/random/?media=gif,png"

        async with request("GET", url, headers={}) as response:
            if response.status == 200:
                data = await response.json()

                await ctx.send(data['media']["gif"])
            else:
                await ctx.send("Could not receive image, please try again later.")

    @commands.hybrid_command(name='cat', description="Display a random cat.")
    @app_commands.checks.cooldown(1, 5)
    async def cat_picture(self, ctx: commands.Context):
        """Sends an image of a random cat."""
        url = "https://api.thecatapi.com/v1/images/search"

        async with request("GET", url, headers={}) as response:
            if response.status == 200:
                data = await response.json()

                await ctx.send(data[0]["url"])
            else:
                await ctx.send("Could not receive image, please try again later.")

    @commands.hybrid_command(name='fox', description="Display a random fox.")
    @app_commands.checks.cooldown(1, 5)
    async def fox_picture(self, ctx: commands.Context):
        """Sends an image of a random fox."""
        url = "https://randomfox.ca/floof/?ref=public-apis"

        async with request("GET", url, headers={}) as response:
            if response.status == 200:
                data = await response.json()

                await ctx.send(data["image"])
            else:
                await ctx.send("Could not receive image, please try again later.")

    @commands.hybrid_command(name='panda', description="Display a random panda.")
    @app_commands.checks.cooldown(1, 5)
    async def panda_picture(self, ctx: commands.Context):
        """Sends an image of a random panda."""
        url = "https://some-random-api.ml/img/panda"

        async with request("GET", url, headers={}) as response:
            if response.status == 200:
                data = await response.text()

                data = json.loads(data)

                await ctx.send(data["link"])
            else:
                await ctx.send("Could not receive image, please try again later.")

    @commands.hybrid_command(name='duck', description="Display a random duck.")
    @app_commands.checks.cooldown(1, 5)
    async def duck_picture(self, ctx: commands.Context):
        """Sends an image of a random dog."""
        url = "https://random-d.uk/api/v2/random"

        async with request("GET", url, headers={}) as response:
            if response.status == 200:
                data = await response.json()

                await ctx.send(data["url"])
            else:
                await ctx.send("Could not receive image, please try again later.")

    @commands.hybrid_command(name='frog', description="Display a random frog.")
    @app_commands.checks.cooldown(1, 5)
    async def frog_picture(self, ctx: commands.Context):
        """Sends an image of a random frog."""
        url = random.choice(self.frog_images)

        await ctx.send(url['url'])

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Fun")


async def setup(bot):
    await bot.add_cog(Fun(bot))
