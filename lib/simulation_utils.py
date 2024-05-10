import json
from collections import Counter
from os.path import isfile
from random import sample

import numpy as np
import relic_engine
from PIL import Image
from discord import Embed
from simulation_engine import SimulationEngine

from strtobool import strtobool

from lib.common import get_emoji
from lib.relic_utils import era_list, style_list, refinement_list, fix_refinement, \
    relic_style_defaults

simulation_engine = SimulationEngine()

def process_quad_rare(refinement):
    refinement_dict = {
        "Intact": 0.02,
        "Exceptional": 0.04,
        "Flawless": 0.06,
        "Radiant": 0.1
    }

    refinement = fix_refinement(refinement.lower())

    chance = refinement_dict[refinement]

    batch_size = 100000
    total_attempts = 0
    while True:
        trials = np.all(np.random.rand(batch_size, 4) < chance, axis=1)
        try:
            first_success_index = np.where(trials)[0][0]
            attempts = total_attempts + first_success_index + 1
            p = chance ** 4  # The probability of success on each trial
            probability = 1 - (1 - p) ** attempts

            return attempts, refinement, probability
        except IndexError:
            total_attempts += batch_size
            continue

def get_set_name(item_name):
    return relic_engine.get_set_name(item_name)



def get_price(item_name):
    return relic_engine.get_price(item_name)


def get_ducats(item_name):
    return relic_engine.get_ducats(item_name)


def parse_time(seconds):
    if seconds > 3600:
        hours = str(int(seconds / 3600)) + "h "
        minutes = str(int((seconds - (3600 * int(seconds / 3600))) / 60)) + "m"
    else:
        hours = ""
        minutes = str(int((seconds / 60))) + "m"
    time = hours + minutes

    return time


refinement_dict = {
    'Intact': 0,
    'Exceptional': 25,
    'Flawless': 50,
    'Radiant': 100
}

with open(f'lib/data/simulation/config/default.json') as f:
    srconfig = json.load(f)

with open(f'lib/data/simulation/config/all_on.json') as f:
    all_on = json.load(f)

with open(f'lib/data/simulation/config/all_off.json') as f:
    all_off = json.load(f)

sr_config_dict = {
    'platinum': {'variants': ['plat', 'platinum'],
                 'type': 'Bool',
                 'default': srconfig['platinum']},
    'ducats': {'variants': ['duc', 'ducat', 'ducats'],
               'type': 'Bool',
               'default': srconfig['ducats']},
    'traces': {'variants': ['trace', 'traces'],
               'type': 'Bool',
               'default': srconfig['traces']},
    'time': {'variants': ['time', 'timespent'],
             'type': 'Bool',
             'default': srconfig['time']},
    'efficiency': {'variants': ['efficiency', 'traceefficiency'],
                   'type': 'Bool',
                   'default': srconfig['efficiency']},
    'plat_per_hour': {'variants': ['plat_per_hour', 'platperhour', 'plathour', 'platphour'],
                      'type': 'Bool',
                      'default': srconfig['plat_per_hour']},
    'ducats_per_hour': {'variants': ['ducats_per_hour', 'ducatperhour', 'ducatsperhour', 'ducatshour', 'ducathour',
                                     'ducatphour', 'ducatsphour'],
                        'type': 'Bool',
                        'default': srconfig['ducats_per_hour']},
    'cycle_plat_average': {'variants': ['cycle_plat_average', 'cycleavg', 'cycleaverage', 'averagecycle',
                                        'averagepercycle', 'avgcycle', 'cycleplatavg', 'cycleplataverage',
                                        'averageplatcycle', 'averageplatpercycle', 'avgplatcycle'],
                           'type': 'Bool',
                           'default': srconfig['cycle_plat_average']},
    'run_plat_average': {'variants': ['run_plat_average', 'runavg', 'runaverage', 'averagerun',
                                      'averageperrun', 'avgrun', 'runplatavg', 'runplataverage',
                                      'averageplatrun', 'averageplatperrun', 'avgplatrun'],
                         'type': 'Bool',
                         'default': srconfig['run_plat_average']},
    'cycle_ducat_average': {'variants': ['cycle_ducat_average', 'cycleducatavg', 'cycleducataverage',
                                         'averageducatcycle', 'averageducatpercycle', 'avgducatcycle'],
                            'type': 'Bool',
                            'default': srconfig['cycle_ducat_average']},
    'run_ducat_average': {'variants': ['run_ducat_average', 'runducatavg', 'runducataverage',
                                       'averageducatrun', 'averageducatperrun', 'avgducatrun'],
                          'type': 'Bool',
                          'default': srconfig['run_ducat_average']},
    'minutes_per_mission': {'variants': ['minutes_per_mission', 'missiontime', 'timepermission', 'minutespermission',
                                         'timemisison', 'minutespermission'],
                            'type': 'Float',
                            'default': srconfig['minutes_per_mission']},
    'minimum_set_price': {'variants': ['minimum_set_price', 'minprice', 'minsetprice', 'minplat'],
                          'type': 'Integer',
                          'default': srconfig['minimum_set_price']},
    'item_cycle_average': {'variants': ['item_cycle_average', 'itemcycleaverage'],
                           'type': 'Bool',
                           'default': srconfig['item_cycle_average']},
    'item_run_average': {'variants': ['item_run_average', 'itemrunaverage'],
                         'type': 'Bool',
                         'default': srconfig['item_run_average']}
}


def get_sr_config(author_id=None, special=None):
    if special == 'all_on':
        return all_on
    elif special == 'all_off':
        return all_off
    else:
        if isfile(f'lib/data/simulation/config/{author_id}.json'):
            with open(f'lib/data/simulation/config/{author_id}.json') as f:
                return json.load(f)
        else:
            return dict(srconfig)


def parse_setting(setting, value):
    if setting == 'all':
        if value in ['reset', 'default']:
            return 'all', get_sr_config(), 'Successfully reset all settings to their default!'
        elif value == 'on':
            return 'all', get_sr_config(special='all_on'), 'Successfully changed all settings to on!'
        elif value == 'off':
            return 'all', get_sr_config(special='all_off'), 'Successfully changed all settings to off!'
        else:
            return

    for key in sr_config_dict:
        if setting in sr_config_dict[key]['variants']:
            if value in ['reset', 'default']:
                value = sr_config_dict[key]['default']
            else:
                if sr_config_dict[key]['type'] == 'Bool':
                    try:
                        value = bool(strtobool(value))
                    except KeyError:
                        break
                elif sr_config_dict[key]['type'] == 'Integer':
                    if value.isnumeric():
                        value = int(value)
                    else:
                        break
                elif sr_config_dict[key]['type'] == 'Float':
                    if is_number(value):
                        value = float(value)
                    else:
                        break

            return key, value, f"Successfully changed {setting} to {value}!"

    return


def fix_name(item_name):
    if len(item_name.split()) > 3:
        if item_name.split(" ")[2] == "Systems" \
                or item_name.split(" ")[2] == "Chassis" \
                or item_name.split(" ")[2] == "Neuroptics" \
                or item_name.split(" ")[2] == "Harness" \
                or item_name.split(" ")[2] == "Wings":
            item_name = item_name.rsplit(' ', 1)[0]

    return item_name


def get_content(rewards, style, amount, refinement, offcycle_count, offcycle_refinement, drop_order, sr_config):
    items_received = []
    total_value = 0
    total_ducats = 0
    num_runs = simulation_engine.num_runs_dict[style] * amount
    reward_list = Counter(rewards)
    for item in reward_list.keys():
        items_received.append([item, reward_list[item], get_price(item)])
        if drop_order[item] >= 100:
            total_ducats += (reward_list[item] * get_ducats(item))
        else:
            total_value += (reward_list[item] * get_price(item))

    items_received.sort(key=lambda x: x[2], reverse=True)

    rewards = []
    for item in items_received:
        if drop_order[item[0]] < 100:
            value = f"{'{:,}'.format(get_price(item[0]) * item[1])} {get_emoji('platinum')}"
        else:
            value = f"{'{:,}'.format(get_ducats(item[0]) * item[1])} {get_emoji('ducats')}"

        if sr_config['item_cycle_average'] or sr_config['item_run_average']:
            item_cycle_calc = item[1] / amount
            item_run_calc = item[1] / num_runs

            if style == '4b4':
                sr_config['item_run_average'] = False
            if sr_config['item_cycle_average'] and sr_config['item_run_average']:
                value = f"{value} - ({'%.2f' % item_cycle_calc} | {'%.2f' % item_run_calc})"
            elif sr_config['item_cycle_average']:
                value = f"{value} - ({'%.2f' % item_cycle_calc})"
            elif sr_config['item_run_average']:
                value = f"{value} - ({'%.2f' % item_run_calc})"

        if item[0] != "Forma Blueprint":
            rewards.append(f"{'{:,}'.format(item[1])}x {fix_name(item[0])} worth {value}")
        else:
            if len(value.split('-')) > 1:
                rewards.append(f"{'{:,}'.format(item[1])}x {fix_name(item[0])}{value.split('-')[1]}")
            else:
                rewards.append(f"{'{:,}'.format(item[1])}x {fix_name(item[0])}")

    platinum = f"{'{:,}'.format(total_value)} {get_emoji('platinum')}"
    ducats = f"{'{:,}'.format(total_ducats)} {get_emoji('ducats')}"

    traces_used_calc = refinement_dict[refinement] * int(amount)

    if style == 'Solo':
        num_drops = 1
    else:
        num_drops = int(style[:1])
    if offcycle_count > 0:
        if style == "1b1":
            offcycle_amount = num_runs / (4 / 3)
        elif style == "2b2" or style == "4b4":
            offcycle_amount = amount
        elif style == "3b3":
            offcycle_amount = num_runs * (4 / 3)

        if offcycle_count == 1:
            num_offcycle_drops = [4 - num_drops]
        elif offcycle_count == 2:
            if style == "2b2":
                num_offcycle_drops = [1, 1]
            elif style == "1b1":
                num_offcycle_drops = sample([1, 2], 2)
        elif offcycle_count == 3:
            if style == "2b2":
                num_offcycle_drops = sample([0, 1, 2], 3)
            elif style == "1b1":
                num_offcycle_drops = [1, 1, 1]
        else:
            num_offcycle_drops = [4 - num_drops]

        for i in range(len(num_offcycle_drops)):
            traces_used_calc += refinement_dict[offcycle_refinement[i]] * (num_offcycle_drops[i] * num_runs)

    traces = f"{'{:,}'.format(traces_used_calc)} {get_emoji('voidtraces')}"

    if traces_used_calc > 0 and int(total_value > 0):
        trace_efficiency_calc = int(traces_used_calc) / int(total_value)
    else:
        trace_efficiency_calc = 0
    trace_efficiency = f"Trace Efficiency: {'%.2f' % trace_efficiency_calc}"

    unparsed_time = num_runs * 60 * float(sr_config['minutes_per_mission'])
    total_time = f"{parse_time(unparsed_time)}"

    plat_per_hour_calc = int(total_value / (unparsed_time / 3600))
    plat_per_hour = f"Plat Per Hour: {'{:,}'.format(plat_per_hour_calc)} {get_emoji('platinum')}"

    cycle_plat_average_calc = total_value / amount
    cycle_plat_average = f"Cycle Average: {'%.0f' % cycle_plat_average_calc} {get_emoji('platinum')}"

    run_plat_average_calc = total_value / num_runs
    run_plat_average = f"Run Average: {'%.0f' % run_plat_average_calc} {get_emoji('platinum')}"

    ducats_per_hour_calc = int(total_ducats / (unparsed_time / 3600))
    ducats_per_hour = f"Ducats Per Hour: {'{:,}'.format(ducats_per_hour_calc)} {get_emoji('ducats')}"

    cycle_ducat_average_calc = total_ducats / amount
    cycle_ducat_average = f"Cycle Average: {'%.0f' % cycle_ducat_average_calc} {get_emoji('ducats')}"

    run_ducat_average_calc = total_ducats / num_runs
    run_ducat_average = f"Run Average: {'%.0f' % run_ducat_average_calc} {get_emoji('ducats')}"

    if total_value == 0 or plat_per_hour_calc == 0 or cycle_plat_average_calc == 0:
        sr_config['ducats_per_hour'] = True
        sr_config['run_ducat_average'] = True
        sr_config['cycle_ducat_average'] = True

    totals = []
    if sr_config['platinum'] and total_value > 0:
        totals.append(platinum)

    if sr_config['ducats'] and total_ducats > 0:
        totals.append(ducats)

    if sr_config['traces'] and traces_used_calc > 0:
        totals.append(traces)

    if sr_config['time']:
        totals.append(total_time)

    extra_info = []
    if sr_config['plat_per_hour'] and plat_per_hour_calc > 0:
        extra_info.append(plat_per_hour)

    if sr_config['ducats_per_hour'] and ducats_per_hour_calc > 0:
        extra_info.append(ducats_per_hour)

    if sr_config['cycle_plat_average'] and cycle_plat_average_calc > 0:
        extra_info.append(cycle_plat_average)

    if sr_config['run_plat_average'] and style != "4b4" and run_plat_average_calc > 0:
        extra_info.append(run_plat_average)

    if sr_config['cycle_ducat_average'] and cycle_ducat_average_calc > 0:
        extra_info.append(cycle_ducat_average)

    if sr_config['run_ducat_average'] and style != "4b4" and run_ducat_average_calc > 0:
        extra_info.append(run_ducat_average)

    if sr_config['efficiency'] and trace_efficiency_calc > 0:
        extra_info.append(trace_efficiency)

    return rewards, totals, extra_info


def get_order(relic_dict_list, user_id, srsettings, srconfig, mode=''):
    if mode == 'plat':
        min_set_price = 0
    elif mode == 'ducat':
        min_set_price = 9999
    else:
        min_set_price = srconfig['minimum_set_price']

    relic_dict_str = ''.join(relic_dict_list[0]['relics']) + ''.join(['w' + ''.join(x) for x in relic_dict_list[1:]])

    if f"{relic_dict_str}{user_id}.json" in srsettings and not mode:
        with open(
                f"lib/data/simulation/settings/{relic_dict_str}{user_id}.json") as f:
            return json.load(f)
    else:
        return simulation_engine.get_drop_priority(relic_dict_list, int(min_set_price))


def add_rarity(image, rarity):
    result = Image.new('RGB', (339, 393))
    result.paste(im=image, box=(0, 0))

    rarity_image = Image.open(fr'lib/data/simulation/image_db/{rarity}.png')
    result.paste(im=rarity_image, box=(0, 339))

    return result


def get_img(reward_screen):
    divider = Image.open(fr'lib/data/simulation/image_db/divider.png')
    images = [divider]
    for drop in reward_screen:
        image = Image.open(fr'lib/data/simulation/image_db/{drop[0]}.png')

        image_rarity = add_rarity(image, drop[1])

        images.append(image_rarity)
        images.append(divider)

    return merge_images(images)


def merge_images(images):
    result_width = 0
    result_height = []
    widths = [0]
    for image in images:
        (width, height) = image.size
        result_width += width
        widths.append(result_width)
        result_height.append(height)

    result_height = max(result_height)

    result = Image.new('RGB', (result_width, result_height))
    i = 0
    for image in images:
        result.paste(im=image, box=(widths[i], 0))
        i += 1
    return result


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


# Uses default if no style selected
def use_default(relics):
    def find_style(current_relic):
        if current_relic not in relic_style_defaults:
            return '4b4r'
        else:
            return relic_style_defaults[current_relic]['styles']['default']

    ref_count = {}
    for relic in relics:
        ref = find_style(relic)
        if ref in list(ref_count):
            ref_count[ref] += 1
        else:
            ref_count[ref] = 1

    most_ref = list(ref_count)[0]
    for ref in list(ref_count):
        if ref_count[ref] > ref_count[most_ref]:
            most_ref = ref
    if '4b4r' in list(ref_count):
        if ref_count['4b4r'] == ref_count[most_ref]:
            most_ref = '4b4r'

    return fix_refinement(most_ref[-1:]), most_ref[:-1]


def get_relic_value(relic):
    split_relic = relic.split()
    fixed_relic = f"{split_relic[0]} {split_relic[1]}"

    refinement, style = use_default([fixed_relic])

    try:
        average_return = relic_engine.get_average_return(fixed_relic, style, refinement)
    except KeyError:
        average_return = 0

    return average_return


# Parses user's relic message
def parse_message(content):
    formatted_content = content.replace(', ', ' ').replace(',', ' ')
    args = formatted_content.split(" ")

    relics = []
    era = None
    refinement = None
    offcycle_relics = []
    offcycle_count = -1
    offcycle_refinement = []
    style = None
    msg = None
    amount = 1
    mode = None
    verbose = False

    for i in range(len(args)):
        if len(args[i]) >= 4 and 'by' in args[i]:
            if args[i][0].isnumeric() and args[i][3].isnumeric():
                args[i] = args[i].replace('by', 'b')
        if args[i].title() in era_list:
            era = args[i].title()
        elif f"{era} {args[i].title()}" in relic_engine.get_relic_list():
            if offcycle_count == -1:
                relics.append(f"{era} {args[i].title()}")
            else:
                offcycle_relics[offcycle_count].append(f"{era} {args[i].title()}")
        elif f"{era} {args[i].upper()}" in relic_engine.get_relic_list():
            if offcycle_count == -1:
                relics.append(f"{era} {args[i].upper()}")
            else:
                offcycle_relics[offcycle_count].append(f"{era} {args[i].upper()}")
        elif args[i] == "special":
            style = '1b1'
            refinement = 'Intact'
            offcycle_count = 2
            offcycle_refinement = ['Exceptional', 'Flawless', 'Radiant']
            offcycle_relics = [relics, relics, relics]
        elif args[i] == "random":
            relics += [x for x in relic_engine.get_relic_list() if x.split()[0] == era]
        elif args[i].lower()[0:3] in style_list + ['8b8', '16b']:
            style = args[i].lower()[0:3]
            if style == '16b':
                style = '16b16'

            if style == 'sol':
                style = 'Solo'
            if args[i].lower()[3:] in refinement_list or (style == '16b16' and args[i].lower()[5:] in refinement_list):
                if style != '16b16':
                    ref = fix_refinement(args[i].lower()[3:])
                else:
                    ref = fix_refinement(args[i].lower()[5:])

                if offcycle_count == -1:
                    refinement = ref
                else:
                    offcycle_refinement[offcycle_count] = ref

        elif args[i].lower() in refinement_list:
            ref = fix_refinement(args[i].lower())
            if offcycle_count == -1:
                refinement = ref
            else:
                offcycle_refinement[offcycle_count] = ref
        elif args[i].lower() in ['w', 'w/', 'with']:
            offcycle_count += 1
            offcycle_relics.append([])
            offcycle_refinement.append(None)
        elif args[i].isnumeric():
            amount = int(args[i])
        elif args[i].lower() in ['ducats', 'duc', 'ducat']:
            mode = 'ducat'
        elif args[i].lower() in ['plat', 'platinum']:
            mode = 'plat'
        elif args[i].lower() in ['debug', 'verbose']:
            verbose = True

    if len(relics) == 0:
        msg = "Could not find any relics to simulate."

    if era is None:
        msg = "Could not detect a valid relic era."

    for lst in offcycle_relics:
        if len(lst) == 0:
            offcycle_count -= 1
            del lst

    offcycle_count += 1
    if msg is None:
        if refinement is None and style is None:
            refinement, style = use_default(relics)
        elif refinement is None and style is not None:
            refinement, _ = use_default(relics)
        elif refinement is not None and style is None:
            _, style = use_default(relics)

        for i in range(offcycle_count):
            if offcycle_refinement[i] is None:
                offcycle_refinement[i], _ = use_default(offcycle_relics[i])

    if amount > 100000 or amount < 1:
        msg = f"{amount} is not recognized as a valid number between 1 and 100000."
    elif style == "3b3" and offcycle_count > 1:
        msg = "You can only a maximum of 1 offcycle in a 3b3 run."
    elif style == "2b2" and offcycle_count > 2:
        msg = "You can only have a maxmimum of 2 offcycles in a 2b2 run."
    elif style == "1b1" and offcycle_count > 3:
        msg = "You can only have a maximum of 3 offcycles in a 1b1 run."
    elif style == "4b4" and offcycle_count > 4:
        msg = "You can only have a maximum of 4 offcycles in a 4b4 run."
    elif offcycle_count > 0 and style == "8b8":
        msg = "You cannot have offcycles in an 8b8 run, please choose another running style."

    return msg, sorted(relics), sorted(
        offcycle_relics), offcycle_count, style, refinement, offcycle_refinement, amount, mode, verbose


def get_srsettings_embed(drop_order, args):
    names = []
    prices = []
    order = []
    for item in drop_order:
        names.append(item)
        prices.append(str(get_price(item)))
        if drop_order[item] <= 100:
            order.append(str(drop_order[item]))
        else:
            order.append(get_emoji('ducats'))

    embed = Embed(title=args.title(), description="")
    embed.add_field(name="Item", value="\n".join(names), inline=True)
    embed.add_field(name="Price", value="\n".join(prices), inline=True)
    embed.add_field(name="Order", value="\n".join(order), inline=True)

    return embed
