import asyncio
import functools
import json
import math
import os
from concurrent.futures.thread import ThreadPoolExecutor
from io import StringIO, BytesIO
from os import listdir
from typing import Optional

import discord
import numpy as np
import relic_engine
from discord import Embed
from discord.ext.commands import Cog, command, cooldown, BucketType

from lib.simulation_utils import parse_message, get_order, get_content, get_ducats, \
    get_srsettings_embed, get_sr_config, parse_setting, process_quad_rare, simulation_engine

import textwrap

from PIL import Image, ImageDraw, ImageFont

special_image_path = "lib/simulation/special"
base_image_path = "lib/simulation/images"
font_path = "lib/simulation/fonts"


def parse_simulation_data(args, author_id, srsettings):
    msg, relics, offcycle_relics, offcycle_count, style, \
        refinement, offcycle_refinement, amount, mode, verbose = parse_message(args)

    if msg:
        return SimulationData(error_message=msg)

    if style == "3b3" and amount % (3 / 4) != 0:
        return SimulationData(error_message="3b3 runs must be a multiple of 3.")

    if verbose and amount > 1000:
        verbose = False

    srconfig = get_sr_config(author_id)

    relic_dict_list = [{'relics': relics, 'refinement': refinement}] + \
                      [{'relics': offcycle_relic, 'refinement': offcycle_ref}
                       for offcycle_relic, offcycle_ref in zip(offcycle_relics, offcycle_refinement)]

    drop_order = get_order(relic_dict_list, author_id, srsettings, srconfig, mode)

    return SimulationData(
        relics=relics,
        offcycle_relics=offcycle_relics,
        offcycle_count=offcycle_count,
        style=style,
        refinement=refinement,
        offcycle_refinement=offcycle_refinement,
        amount=amount,
        verbose=verbose,
        srconfig=srconfig,
        relic_dict_list=relic_dict_list,
        drop_order=drop_order
    )

async def simulate_relics(simulation_data, loop):
    return await loop.run_in_executor(
        ThreadPoolExecutor(),
        functools.partial(simulation_engine.simulate_relic,
                          simulation_data.relic_dict_list, style=simulation_data.style,
                          amount=simulation_data.amount, drop_priority=simulation_data.drop_order)
    )

def create_simulation_embed(simulation_data):
    title = get_title(simulation_data)

    embed = Embed(title=title, description='\n'.join(simulation_data.rewards) if len('\n'.join(simulation_data.rewards)) <= 4096 else '')

    if simulation_data.totals:
        embed.add_field(name="Totals", value="\n".join(simulation_data.totals), inline=True)
    if simulation_data.info:
        embed.add_field(name="Info", value="\n".join(simulation_data.info), inline=True)

    return embed

async def send_verbose_output(ctx, embed, reward_screen):
    verbose_string = '\n'.join(' | '.join(f"{x[1][0]} {x[0]}" for x in element) for element in reward_screen)
    with StringIO(verbose_string) as f:
        fp = discord.File(f, filename='output.txt')
        await ctx.send(embed=embed, file=fp)

async def send_output(ctx, embed, rewards):
    if len('\n'.join(rewards)) <= 4096:
        await ctx.send(embed=embed)
    else:
        with StringIO('\n'.join(rewards)) as f:
            fp = discord.File(f, filename='output.txt')
            await ctx.send(embed=embed, file=fp)

def get_title(simulation_data):
    title = f"Simulated {simulation_data.amount} {' '.join(simulation_data.relics)} {simulation_data.style} {simulation_data.refinement}" if len(' '.join(simulation_data.relics)) <= 10 \
        else f"Simulated {simulation_data.amount} Relics {simulation_data.style} {simulation_data.refinement}"
    if simulation_data.offcycle_count > 0:
        for lst, ref in zip(simulation_data.offcycle_relics, simulation_data.offcycle_refinement):
            title += f"\nwith {' '.join(lst)} {ref}"
        title += ' offcycle'
    title += ':'
    return title

class SimulationData:
    def __init__(self, error_message=None, relics=None, offcycle_relics=None, offcycle_count=None,
                 style=None, refinement=None, offcycle_refinement=None, amount=None, verbose=None,
                 srconfig=None, relic_dict_list=None, drop_order=None, rewards=None, totals=None, info=None):
        self.error_message = error_message
        self.relics = relics
        self.offcycle_relics = offcycle_relics
        self.offcycle_count = offcycle_count
        self.style = style
        self.refinement = refinement
        self.offcycle_refinement = offcycle_refinement
        self.amount = amount
        self.verbose = verbose
        self.srconfig = srconfig
        self.relic_dict_list = relic_dict_list
        self.drop_order = drop_order
        self.rewards = rewards
        self.totals = totals
        self.info = info



def get_relic_drop_image(relic_drop):
    item_type = 'background'
    if "Blueprint" in relic_drop:
        relic_drop = relic_drop.replace(" Blueprint", "")
        item_type = 'blueprint'

    if "1200X" in relic_drop:
        relic_drop = "Kuva"

    relic_drop_path = f"{base_image_path}/{relic_drop}.png"
    item_type_path = f"{special_image_path}/{item_type}.png"

    try:
        relic_drop_image = Image.open(relic_drop_path).convert("RGBA")
        item_type_image = Image.open(item_type_path).convert("RGBA")

        # Resize the relic_drop image to match the size of item_type
        relic_drop_resized = relic_drop_image.resize(item_type_image.size)

        # Create a new image with the same size as item_type
        combined_image = Image.new("RGBA", item_type_image.size)

        # Paste the item_type image as the background
        combined_image.paste(item_type_image, (0, 0), mask=item_type_image)

        # Paste the resized relic_drop image on top of the background, respecting transparency
        combined_image.alpha_composite(relic_drop_resized)

        # Add text at the bottom of the image with a drop shadow
        draw = ImageDraw.Draw(combined_image)
        font_size = 36
        font = ImageFont.truetype(f"{font_path}/Roboto-Regular.ttf", font_size)
        text_color = (2, 127, 217)  # RGB color code for 027fd9
        shadow_color = (0, 0, 0)  # Black color for the shadow
        shadow_offset = 2  # Offset distance for the shadow

        if item_type == 'blueprint':
            relic_drop = f"{relic_drop} Blueprint"

        # Wrap the text to fit within the image width
        text_lines = textwrap.wrap(relic_drop, width=18)

        text_height = len(text_lines) * font_size
        text_y = combined_image.height - text_height - 10

        for line in text_lines:
            text_bbox = draw.textbbox((0, 0), line, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_x = (combined_image.width - text_width) // 2

            # Draw the shadow text
            draw.text((text_x + shadow_offset, text_y + shadow_offset), line, font=font, fill=shadow_color)

            # Draw the main text
            draw.text((text_x, text_y), line, font=font, fill=text_color)

            text_y += font_size

        return combined_image

    except FileNotFoundError:
        print(f"Image not found for {relic_drop}")
        return None


def generate_base_image(reward_screen):
    first_reward = reward_screen[0][0][0]
    relic_drop_image = get_relic_drop_image(first_reward)
    divider = Image.open(f"{special_image_path}/divider.png").convert("RGBA")

    num_rewards = len(reward_screen[0])
    base_width = (relic_drop_image.width + divider.width) * num_rewards

    rarities = [f"{special_image_path}/Common.png", f"{special_image_path}/Uncommon.png",
                f"{special_image_path}/Rare.png"]
    max_height = max(Image.open(rarity).height for rarity in rarities)

    base_height = relic_drop_image.height + max_height
    base_image = Image.new("RGBA", (base_width, base_height))

    return base_image


def combine_image(reward, rarity):
    relic_drop_image = get_relic_drop_image(reward)
    rarity_image = Image.open(f"{special_image_path}/{rarity}.png").convert("RGBA")
    divider = Image.open(f"{special_image_path}/divider.png").convert("RGBA")

    combined_width = relic_drop_image.width + divider.width
    combined_height = relic_drop_image.height + rarity_image.height

    combined_image = Image.new("RGBA", (combined_width, combined_height))
    combined_image.paste(relic_drop_image, (0, 0))
    combined_image.paste(rarity_image, (0, relic_drop_image.height))
    combined_image.paste(divider, (relic_drop_image.width, 0))

    return combined_image


def create_reward_screen(reward_screen):
    base_image = generate_base_image(reward_screen)

    x_offset = 0
    for reward, rarity in reward_screen[0]:
        combined_image = combine_image(reward, rarity)
        base_image.paste(combined_image, (x_offset, 0))
        x_offset += combined_image.width

    return base_image


class Simulator(Cog, name="simulator"):
    def __init__(self, bot):
        self.bot = bot
        self.srsettings = listdir('lib/data/simulation/settings')
        self.leaderboard = None
        if os.path.isfile('lib/data/simulation/leaderboard.json'):
            with open('lib/data/simulation/leaderboard.json', 'r') as f:
                self.leaderboard = json.load(f)

            for key in self.leaderboard:
                self.leaderboard[key] = {int(k): v for k, v in self.leaderboard[key].items()}
        else:
            self.leaderboard = {'intact': {},
                                'exceptional': {},
                                'flawless': {},
                                'radiant': {}}

        self.refinement_dict = {'i': 'intact', 'e': 'exceptional', 'f': 'flawless', 'r': 'radiant'}

    @command(name="simulate", aliases=["sr", "simulaterelic", "sim"])
    async def simulator(self, ctx, *, args):
        """
        Simulates relic runs and returns rewards.

        Usage: --sr [relic(s)] [refinement] [style] [number of runs (optional)]
               --sr [relic(s)] [refinement] [style] with [offcycle relic(s)] [offcycle refinement] offcycle

        Examples:
        --sr Axi L4 4b4 rad
        --sr Axi L4 2b2 rad with Axi N3 rad offcycle
        --sr Axi L1 Axi L4 2b2 rad
        --sr Axi L1 Axi L4 2b2 rad with Axi V1 Axi V8 flaw offcycle

        Settings:
        --srsettings [relic]: Set reward selection order
        --srconfig: Modify display and constants
        """
        if ctx.guild is None or ctx.channel.name == "relic-simulation":
            simulation_data = parse_simulation_data(args, ctx.author.id, self.srsettings)
            if simulation_data.error_message:
                await ctx.send(simulation_data.error_message)
                return

            reward_list, reward_screen = await simulate_relics(simulation_data, self.bot.loop)

            simulation_data.rewards, simulation_data.totals, simulation_data.info = get_content(reward_list,
                                                                                                simulation_data)

            embed = create_simulation_embed(simulation_data)

            if simulation_data.verbose:
                await send_verbose_output(ctx, embed, reward_screen)
            else:
                await send_output(ctx, embed, simulation_data.rewards)

        else:
            msg = await ctx.send(content="This command is only allowed to be used in the relic-simulation channel.")
            self.bot.mdh(ctx.message, msg, ctx.channel)

    @command(name="srsettings")
    async def simulator_settings(self, ctx, *, args):
        """
        Allows you to set the order in which the bot will choose rewards in the future.

        When using this command, the bot will show you the current order and ask you to reply with the new order.

        Any part you do not choose will be treated as ducats in future calculations.

        If you choose "None" as the order, the bot will treat all parts as ducats.
        """
        if ctx.guild is None or ctx.channel.name == "relic-simulation":
            msg, relics, offcycle_relics, offcycle = parse_message(args)[:4]

            if msg is not None:
                await ctx.send(msg)
                return

            relic_dict_list = [
                {'relics': relics, 'refinement': []},
            ]

            for offcycle_relic in offcycle_relics:
                relics.append({'relics': offcycle_relic, 'refinement': []})

            drop_order = simulation_engine.get_drop_priority(relic_dict_list, 0)

            await ctx.send(embed=get_srsettings_embed(drop_order, args))

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            message = "If you wish change order, reply to this with the new order ordered by the number of the " \
                      "part in the current order. Otherwise, reply with cancel.\nFormat is \"1,2,3,4,5,6\"\n" \
                      "Any part you do not choose will be treated as ducats in future calculations. " \
                      "If you do not wish to choose any item, reply with \"None\""
            question = await ctx.channel.send(message)

            try:
                msg = await self.bot.wait_for('message', timeout=120.0, check=check)
            except asyncio.TimeoutError:
                await question.delete()
                return
            await question.delete()
            if 'cancel' in msg.content:
                return

            new_order = msg.content
            new_order = new_order.replace(' ', '').split(',')
            if 'none' in new_order:
                new_order = []

            custom_drop_prio = []
            drop_order_keys = list(drop_order.keys())
            drop_order_values = list(drop_order.values())
            for item in new_order:
                if not item.isnumeric():
                    await ctx.send(
                        "Non-number detected, "
                        "please make sure you only reply with numbers seperated by commas.")
                    return
                elif item not in ['1', '2', '3', '4', '5', '6']:
                    await ctx.send(
                        "Number not found in original order, "
                        "are you sure you entered it right? Please try again.")
                    return
                else:
                    custom_drop_prio.append(drop_order_keys[drop_order_values.index(int(item))])

            ducat_list = []
            for item in drop_order_keys:
                if item not in custom_drop_prio:
                    ducat_list.append([item, get_ducats(item)])

            drop_prioity = {k: v + 1 for v, k in enumerate([item for item in custom_drop_prio])}

            drop_prioity.update({k: v + 101 for v, k in enumerate([item[0] for item in
                                                                   sorted(ducat_list, key=lambda x: x[1],
                                                                          reverse=True)])})

            with open(f"lib/data/simulation/settings/{''.join(relics)}"
                      f"{''.join(['w' + ''.join(x) for x in offcycle_relics])}{ctx.author.id}.json", 'w') as fp:
                json.dump(drop_prioity, fp)
            self.srsettings = listdir('lib/data/simulation/settings')

            await ctx.send(embed=get_srsettings_embed(drop_prioity, args))
        else:
            msg = await ctx.send(content="This command is only allowed to be used in the relic-simulation channel.")
            self.bot.mdh(ctx.message, msg, ctx.channel)

    @command(name="getscreen", aliases=["gs"])
    @cooldown(1, 3, BucketType.channel)
    async def get_reward_screen(self, ctx, *, args):
        """
        Simulates a single relic run and returns the reward screen.

        Type a relic, refinement, and style like so:
        --gs Axi L4 4b4 rad
        """
        msg, relics, offcycle_relics, offcycle_count, style, \
            refinement, offcycle_refinement = parse_message(args)[:7]


        if msg is not None:
            await ctx.send(msg)
            return
        else:
            if style in ['1b1', '2b2', '3b3']:
                if offcycle_count == 0:
                    offcycle_count += 1
                    non_vaulted_relics = relic_engine.get_non_vaulted_relics()
                    offcycle_relics.append([x for x in non_vaulted_relics if 'Requiem' not in x])
                    offcycle_refinement.append('Intact')

            relic_dict_list = [
                {'relics': relics, 'refinement': refinement},
            ]

            for offcycle_relic, offcycle_ref in zip(offcycle_relics, offcycle_refinement):
                relic_dict_list.append({'relics': offcycle_relic, 'refinement': offcycle_ref})

            _, reward_screen = await self.bot.loop.run_in_executor(
                ThreadPoolExecutor(), functools.partial(simulation_engine.simulate_relic,
                                                        relic_dict_list, style=style, amount=1))

            new_img = await self.bot.loop.run_in_executor(ThreadPoolExecutor(), create_reward_screen, reward_screen)

            b = BytesIO()
            new_img.save(b, "PNG")
            b.seek(0)

            await ctx.send(file=discord.File(fp=b, filename="image.png"))

    @command(name="quadrare", aliases=["qr", 'qrs'])
    @cooldown(1, 30, BucketType.user)
    async def quad_rare_simulator(self, ctx, refinement: str = 'Radiant'):
        """
       Simulates the number of runs needed to get a quad rare reward screen.

       By default, simulates a radiant quad rare reward screen.
       You can provide a refinement as an argument, like so:
       --qr f
        """
        if ctx.channel.id not in [1089587184987811961, 1094699732577828884]:
            await ctx.send("This command is only allowed to be used in the s!pam channel.", delete_after=3)
            try:
                await ctx.message.delete(delay=1)
            except discord.Forbidden:
                pass
            except discord.NotFound:
                pass
            except discord.HTTPException:
                pass
            return

        counter, refinement, probability = await self.bot.loop.run_in_executor(
            ThreadPoolExecutor(), process_quad_rare,
            refinement
        )
        # Calculate equivalent number of runs with a success chance of .3439
        equivalent_run_unlucky = np.log(1 - probability) / np.log(1 - .3439)
        equivalent_run_lucky = np.log(probability) / np.log(.3439)

        prob_formatted = "{:.2f}".format(probability * 100) + '%'

        prob_string = f"You had a {prob_formatted} chance of needing that many runs!"

        if equivalent_run_unlucky > 3:
            prob_string += f"\nThat is equivalent to going {math.floor(equivalent_run_unlucky)} dry in 4b4 rad" \
                           f"{' <:despairge:1040757033089114242>' if equivalent_run_unlucky > 8 else ''}."

        if equivalent_run_lucky > 3:
            prob_string += f"\nThat is equivalent to getting {math.floor(equivalent_run_lucky)} " \
                           f"rares in a row in 4b4 rad" \
                           f"{' <:WTFFFF:890180639247175680>' if equivalent_run_lucky > 8 else ''}."

        pb_check, old_run_val, old_run_prob = self.save_to_leaderboard(ctx.author, refinement.lower(), int(counter),
                                                                       prob_formatted)

        if pb_check is not None:
            old_run = f"{'{:,}'.format(int(old_run_val))} {old_run_prob}"
            prob_string += f"\nYou got a new personal {'best' if pb_check else 'worst'}!\n" \
                           f"Previous was {old_run}."

        await ctx.send(
            f"It took you ... {'{:,}'.format(counter)} runs to get a {refinement.lower()} quad rare reward screen!\n"
            f"{prob_string}", reference=ctx.message)

    async def get_leaderboard_embed(self, leaderboard: dict, refinement: str, best: bool = True,
                                    ctx_user_id: int = None):
        user_dict = leaderboard[refinement]

        # Choose index 0 (best runs) or 1 (worst runs)
        index = 0 if best else 1

        # Sort by runs, parsed from the tuples, ignoring probabilities
        sorted_items = sorted(user_dict.items(),
                              key=lambda item: (int(item[1][index].split(' ')[0]), item[0]),
                              reverse=not best)

        user_list, rank, last_run = [], 0, None
        user_in_list = False
        for i, (user_id, run) in enumerate(sorted_items, 1):
            run_val, run_prob = run[index].split(' ')
            run_val = int(run_val)
            if run_val != last_run:
                rank = i

            user = self.bot.get_user(user_id)
            if user is None:
                user = user_id

            if ctx_user_id == user_id:
                user_in_list = True

                if i > 10:
                    user_list.append(["...", "...", "..."])

                user_list.append([f"**{rank}**", f"**{user}**", f"**{'{:,}'.format(run_val)} {run_prob}**"])
            elif i <= 10:
                user_list.append([rank, user, f"{'{:,}'.format(run_val)} {run_prob}"])

            last_run = run_val

            if i >= 10 and user_in_list:
                break

        embed = discord.Embed(title=f"{refinement.title()} Quad Rare {'Leader' if best else 'Loser'}board",
                              colour=discord.Colour.blue())
        embed.add_field(name="Rank", value='\n'.join([str(user[0]) for user in user_list]), inline=True)
        embed.add_field(name="User", value='\n'.join([str(user[1]) for user in user_list]), inline=True)
        embed.add_field(name="Run", value='\n'.join([str(user[2]) for user in user_list]), inline=True)

        return embed

    def save_to_leaderboard(self, user, refinement, new_run, probability):
        result = None
        old_run_val = None
        old_run_prob = None

        # Check if the user already has stored runs
        if user.id in self.leaderboard[refinement]:
            best_run, worst_run = self.leaderboard[refinement][user.id]
            best_run_val, best_run_prob = best_run.split(' ')
            worst_run_val, worst_run_prob = worst_run.split(' ')

            # Update best and/or worst run if necessary
            if new_run < int(best_run_val):
                old_run_val = best_run_val
                old_run_prob = best_run_prob
                best_run = f"{new_run} ({probability})"
                result = True
            if new_run > int(worst_run_val):
                old_run_val = worst_run_val
                old_run_prob = worst_run_prob
                worst_run = f"{new_run} ({probability})"
                result = False
        else:
            # If the user is not in the dictionary yet, both their best and worst runs are the new run
            best_run = worst_run = f"{new_run} ({probability})"

        self.leaderboard[refinement][user.id] = [best_run, worst_run]

        with open('lib/data/simulation/leaderboard.json', 'w') as f:
            json.dump(self.leaderboard, f, indent=4)

        return result, old_run_val, old_run_prob

    @command(name='quadrareleaderboard', aliases=['qrlb', 'qlb', 'qleader'])
    async def quad_rare_leaderboard(self, ctx, refinement: str = 'radiant'):
        """Shows the quad rare leaderboard for the specified refinement.

        The leaderboard shows the top 10 users with the best "runs" as in the lowest number of runs needed to get a quad rare reward screen.
        Your personal best will be highlighted in the leaderboard.

        By default, shows the radiant quad rare leaderboard."""
        refinement = self.refinement_dict[refinement.lower()[0]]
        embed = await self.get_leaderboard_embed(self.leaderboard, refinement, True, ctx.author.id)

        await ctx.send(embed=embed)

    @command(name='quadrareloserboard', aliases=['qrloser', 'qloser'])
    async def quad_rare_loserboard(self, ctx, refinement: str = 'radiant'):
        """Shows the quad rare loserboard for the specified refinement.

        The loserboard shows the top 10 users with the worst "runs" as in the highest number of runs needed to get a quad rare reward screen.

        By default, shows the radiant quad rare loserboard.
        """
        refinement = self.refinement_dict[refinement.lower()[0]]
        embed = await self.get_leaderboard_embed(self.leaderboard, refinement, False, ctx.author.id)

        await ctx.send(embed=embed)

    # noinspection PyRedundantParentheses
    @command(name="srconfig")
    async def sr_config(self, ctx, setting: Optional[str], value: Optional[str]):
        """
        Allows you to change the settings for the relic simulator.

        If you do not provide a setting and a value, the bot will show you your current settings.

        If you provide a setting and a value, the bot will change the setting to the value you provided.

        To see the current settings, type --srconfig
        """
        srconfig = get_sr_config(ctx.author.id)
        if setting is not None and value is not None:
            if value := parse_setting(setting.lower(), value.lower()):
                if value[0] == 'all':
                    srconfig = value[1]
                else:
                    srconfig[value[0]] = value[1]

                with open(f"lib/data/simulation/config/{ctx.author.id}.json", 'w') as fp:
                    json.dump(srconfig, fp)

                await ctx.send(value[2])
            else:
                await ctx.send("Could not find a value to change!")
        else:
            await ctx.send("You are missing the config value to change."
                           "\nYour current settings and their values are listed below. "
                           "To change one add the setting and the value."
                           "\nExample: --srconfig time off")

            value_list = []
            for value in srconfig.values():
                if type(value) == bool:
                    value_list.append('On' if value else 'Off')
                else:
                    value_list.append(str(value))

            embed = discord.Embed(title='Relic Simulator Config', description="")
            embed.add_field(name="Setting", value="\n".join(srconfig.keys()), inline=True)
            embed.add_field(name="Value", value="\n".join(value_list), inline=True)

            await ctx.send(embed=embed)

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Simulator")


async def setup(bot):
    await bot.add_cog(Simulator(bot))
