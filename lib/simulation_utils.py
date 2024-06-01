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


def get_content(reward_list, simulation_data):
    items_received = calculate_items_received(reward_list, simulation_data)
    total_value, total_ducats = calculate_totals(items_received, simulation_data)

    rewards = format_rewards(items_received, simulation_data)
    traces_used_calc = calculate_traces_used(simulation_data)

    trace_efficiency_calc = calculate_trace_efficiency(traces_used_calc, total_value)

    unparsed_time = calculate_unparsed_time(simulation_data)

    plat_per_hour_calc = calculate_plat_per_hour(total_value, unparsed_time)
    cycle_plat_average_calc = calculate_cycle_plat_average(total_value, simulation_data)
    run_plat_average_calc = calculate_run_plat_average(total_value, simulation_data)

    ducats_per_hour_calc = calculate_ducats_per_hour(total_ducats, unparsed_time)
    cycle_ducat_average_calc = calculate_cycle_ducat_average(total_ducats, simulation_data)
    run_ducat_average_calc = calculate_run_ducat_average(total_ducats, simulation_data)

    update_srconfig(simulation_data, total_value, plat_per_hour_calc, cycle_plat_average_calc)

    totals = create_totals(simulation_data, total_value, total_ducats, traces_used_calc, unparsed_time)
    extra_info = create_extra_info(simulation_data, plat_per_hour_calc, ducats_per_hour_calc,
                                   cycle_plat_average_calc, run_plat_average_calc,
                                   cycle_ducat_average_calc, run_ducat_average_calc,
                                   trace_efficiency_calc)

    return rewards, totals, extra_info


def calculate_items_received(reward_list, simulation_data):
    items_received = []
    reward_counter = Counter(reward_list)
    for item in reward_counter.keys():
        items_received.append([item, reward_counter[item], get_price(item)])
    items_received.sort(key=lambda x: x[2], reverse=True)
    return items_received


def calculate_totals(items_received, simulation_data):
    total_value = sum(get_price(item[0]) * item[1] for item in items_received if simulation_data.drop_order[item[0]] < 100)
    total_ducats = sum(get_ducats(item[0]) * item[1] for item in items_received if simulation_data.drop_order[item[0]] >= 100)
    return total_value, total_ducats


def format_rewards(items_received, simulation_data):
    rewards = []
    num_runs = simulation_engine.num_runs_dict[simulation_data.style] * simulation_data.amount

    for item in items_received:
        if simulation_data.drop_order[item[0]] < 100:
            value = f"{'{:,}'.format(get_price(item[0]) * item[1])} {get_emoji('platinum')}"
        else:
            value = f"{'{:,}'.format(get_ducats(item[0]) * item[1])} {get_emoji('ducats')}"

        if simulation_data.srconfig['item_cycle_average'] or simulation_data.srconfig['item_run_average']:
            item_cycle_calc = item[1] / simulation_data.amount
            item_run_calc = item[1] / num_runs

            if simulation_data.style == '4b4':
                simulation_data.srconfig['item_run_average'] = False
            if simulation_data.srconfig['item_cycle_average'] and simulation_data.srconfig['item_run_average']:
                value = f"{value} - ({'%.2f' % item_cycle_calc} | {'%.2f' % item_run_calc})"
            elif simulation_data.srconfig['item_cycle_average']:
                value = f"{value} - ({'%.2f' % item_cycle_calc})"
            elif simulation_data.srconfig['item_run_average']:
                value = f"{value} - ({'%.2f' % item_run_calc})"

        if item[0] != "Forma Blueprint":
            rewards.append(f"{'{:,}'.format(item[1])}x {fix_name(item[0])} worth {value}")
        else:
            if len(value.split('-')) > 1:
                rewards.append(f"{'{:,}'.format(item[1])}x {fix_name(item[0])}{value.split('-')[1]}")
            else:
                rewards.append(f"{'{:,}'.format(item[1])}x {fix_name(item[0])}")

    return rewards


def calculate_traces_used(simulation_data):
    traces_used_calc = refinement_dict[simulation_data.refinement] * int(simulation_data.amount)

    if simulation_data.style == 'Solo':
        num_drops = 1
    else:
        num_drops = int(simulation_data.style[:1])

    if simulation_data.offcycle_count > 0:
        num_runs = simulation_engine.num_runs_dict[simulation_data.style] * simulation_data.amount

        num_offcycle_drops = get_num_offcycle_drops(simulation_data, num_drops)

        for i in range(len(num_offcycle_drops)):
            traces_used_calc += refinement_dict[simulation_data.offcycle_refinement[i]] * (num_offcycle_drops[i] * num_runs)

    return traces_used_calc


def get_num_offcycle_drops(simulation_data, num_drops):
    if simulation_data.offcycle_count == 1:
        return [4 - num_drops]
    elif simulation_data.offcycle_count == 2:
        if simulation_data.style == "2b2":
            return [1, 1]
        elif simulation_data.style == "1b1":
            return sample([1, 2], 2)
    elif simulation_data.offcycle_count == 3:
        if simulation_data.style == "2b2":
            return sample([0, 1, 2], 3)
        elif simulation_data.style == "1b1":
            return [1, 1, 1]
    else:
        return [4 - num_drops]


def calculate_trace_efficiency(traces_used_calc, total_value):
    if traces_used_calc > 0 and int(total_value > 0):
        return int(traces_used_calc) / int(total_value)
    else:
        return 0


def calculate_unparsed_time(simulation_data):
    num_runs = simulation_engine.num_runs_dict[simulation_data.style] * simulation_data.amount
    return num_runs * 60 * float(simulation_data.srconfig['minutes_per_mission'])


def calculate_plat_per_hour(total_value, unparsed_time):
    return int(total_value / (unparsed_time / 3600))


def calculate_cycle_plat_average(total_value, simulation_data):
    return total_value / simulation_data.amount


def calculate_run_plat_average(total_value, simulation_data):
    num_runs = simulation_engine.num_runs_dict[simulation_data.style] * simulation_data.amount
    return total_value / num_runs


def calculate_ducats_per_hour(total_ducats, unparsed_time):
    return int(total_ducats / (unparsed_time / 3600))


def calculate_cycle_ducat_average(total_ducats, simulation_data):
    return total_ducats / simulation_data.amount


def calculate_run_ducat_average(total_ducats, simulation_data):
    num_runs = simulation_engine.num_runs_dict[simulation_data.style] * simulation_data.amount
    return total_ducats / num_runs


def update_srconfig(simulation_data, total_value, plat_per_hour_calc, cycle_plat_average_calc):
    if total_value == 0 or plat_per_hour_calc == 0 or cycle_plat_average_calc == 0:
        simulation_data.srconfig['ducats_per_hour'] = True
        simulation_data.srconfig['run_ducat_average'] = True
        simulation_data.srconfig['cycle_ducat_average'] = True


def create_totals(simulation_data, total_value, total_ducats, traces_used_calc, unparsed_time):
    totals = []
    total_info = [
        (simulation_data.srconfig['platinum'], total_value, 'platinum'),
        (simulation_data.srconfig['ducats'], total_ducats, 'ducats'),
        (simulation_data.srconfig['traces'], traces_used_calc, 'voidtraces'),
        (simulation_data.srconfig['time'], unparsed_time, None)
    ]

    for condition, value, emoji in total_info:
        if condition and value > 0:
            if emoji:
                totals.append(f"{'{:,}'.format(value)} {get_emoji(emoji)}")
            else:
                totals.append(f"{parse_time(value)}")

    return totals


def create_extra_info(simulation_data, plat_per_hour_calc, ducats_per_hour_calc, cycle_plat_average_calc,
                      run_plat_average_calc, cycle_ducat_average_calc, run_ducat_average_calc, trace_efficiency_calc):
    extra_info = []
    extra_info_data = [
        (simulation_data.srconfig['plat_per_hour'], plat_per_hour_calc, 'platinum', "Plat Per Hour", '{:,}'),
        (simulation_data.srconfig['ducats_per_hour'], ducats_per_hour_calc, 'ducats', "Ducats Per Hour", '{:,}'),
        (simulation_data.srconfig['cycle_plat_average'], cycle_plat_average_calc, 'platinum', "Cycle Average", '{:.0f}'),
        (simulation_data.srconfig['run_plat_average'] and simulation_data.style != "4b4", run_plat_average_calc, 'platinum', "Run Average", '{:.0f}'),
        (simulation_data.srconfig['cycle_ducat_average'], cycle_ducat_average_calc, 'ducats', "Cycle Average", '{:.0f}'),
        (simulation_data.srconfig['run_ducat_average'] and simulation_data.style != "4b4", run_ducat_average_calc, 'ducats', "Run Average", '{:.0f}'),
        (simulation_data.srconfig['efficiency'], trace_efficiency_calc, None, "Trace Efficiency", '{:.2f}')
    ]

    for condition, value, emoji, label, format_str in extra_info_data:
        if condition and value > 0:
            if emoji:
                extra_info.append(f"{label}: {format_str.format(value)} {get_emoji(emoji)}")
            else:
                extra_info.append(f"{label}: {format_str.format(value)}")

    return extra_info



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
    args = content.replace(', ', ' ').replace(',', ' ').split()
    relics, offcycle_relics = [], []
    era = refinement = style = msg = mode = None
    offcycle_count, amount, verbose = -1, 1, False
    offcycle_refinement = []

    def append_relic(relic):
        if offcycle_count == -1:
            relics.append(relic)
        else:
            offcycle_relics[offcycle_count].append(relic)

    def handle_style_and_refinement(arg):
        nonlocal style, refinement, offcycle_refinement
        arg = arg.lower()

        def set_refinement(ref):
            nonlocal refinement, offcycle_refinement
            if offcycle_count == -1:
                refinement = ref
            else:
                offcycle_refinement[offcycle_count] = ref

        for s in style_list + ['8b8', '16b16']:
            if arg == s:
                style = s
                return
            if arg.startswith(s):
                style = s
                arg = arg[len(s):]
                break

        for r in refinement_list:
            if arg == r:
                set_refinement(fix_refinement(r))
                return
            if arg.startswith(r):
                set_refinement(fix_refinement(r))
                break

    def handle_offcycle():
        nonlocal offcycle_count
        offcycle_count += 1
        offcycle_relics.append([])
        offcycle_refinement.append(None)

    def validate_amount():
        nonlocal msg
        if not 1 <= amount <= 100000:
            msg = f"{amount} is not recognized as a valid number between 1 and 100000."

    def validate_offcycle_count():
        nonlocal msg
        if style == "3b3" and offcycle_count > 1:
            msg = "You can only a maximum of 1 offcycle in a 3b3 run."
        elif style == "2b2" and offcycle_count > 2:
            msg = "You can only have a maxmimum of 2 offcycles in a 2b2 run."
        elif style == "1b1" and offcycle_count > 3:
            msg = "You can only have a maximum of 3 offcycles in a 1b1 run."
        elif style == "4b4" and offcycle_count > 4:
            msg = "You can only have a maximum of 4 offcycles in a 4b4 run."
        elif offcycle_count > 0 and style == "8b8":
            msg = "You cannot have offcycles in an 8b8 run, please choose another running style."

    def replace_by_with_b(arg):
        if 'by' in arg:
            parts = arg.split('by')
            if len(parts) == 2 and parts[0].isnumeric() and parts[1].isnumeric():
                return f"{parts[0]}b{parts[1]}"
        return arg

    for arg in args:
        arg = replace_by_with_b(arg)
        if arg.title() in era_list:
            era = arg.title()
        elif f"{era} {arg.title()}" in relic_engine.get_relic_list():
            append_relic(f"{era} {arg.title()}")
        elif f"{era} {arg.upper()}" in relic_engine.get_relic_list():
            append_relic(f"{era} {arg.upper()}")
        elif arg == "special":
            if style is None:
                style = '1b1'
            if refinement is None:
                refinement = 'Intact'
            offcycle_count, offcycle_refinement = 2, ['Exceptional', 'Flawless', 'Radiant']
            offcycle_relics = [relics] * 3
        elif arg == "random":
            relics += [x for x in relic_engine.get_relic_list() if x.split()[0] == era]
        elif arg.lower() in ['w', 'w/', 'with']:
            handle_offcycle()
        elif arg.isnumeric():
            amount = int(arg)
        elif arg.lower() in ['ducats', 'duc', 'ducat']:
            mode = 'ducat'
        elif arg.lower() in ['plat', 'platinum']:
            mode = 'plat'
        elif arg.lower() in ['debug', 'verbose']:
            verbose = True
        else:
            handle_style_and_refinement(arg)

    msg = "Could not find any relics to simulate." if not relics else "Could not detect a valid relic era." if not era else None
    offcycle_count = sum(1 for lst in offcycle_relics if lst)

    if msg is None:
        if refinement is None and style is None:
            refinement, style = use_default(relics)
        elif refinement is None:
            refinement = use_default(relics)[0]
        elif style is None:
            style = use_default(relics)[1]

        for i in range(offcycle_count):
            offcycle_refinement[i] = use_default(offcycle_relics[i])[0] if offcycle_refinement[i] is None else \
            offcycle_refinement[i]

    validate_amount()
    validate_offcycle_count()

    return msg, sorted(relics), sorted(offcycle_relics), offcycle_count, style, refinement, offcycle_refinement, amount, mode, verbose


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
