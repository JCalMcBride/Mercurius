import json
import os
from io import BytesIO
from typing import Optional, List

import discord
import relic_engine
from discord import Embed, NotFound, HTTPException, app_commands, ButtonStyle
from discord.app_commands import Choice
from discord.ext import commands
from discord.ext.commands import command, Cog, GroupCog
from more_itertools import chunked

from lib.common import get_config
from lib.relic_utils import refinement_list, fix_refinement, refinement_list_new
from lib.simulation_utils import fix_name, get_relic_value, get_set_name

import datetime
import io
import json
import os.path
import pickle

import relic_engine
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


with open('lib/data/wfcd_api.json', encoding='utf-8') as f:
    wfcd_api = json.load(f)

with open('lib/data/blueprint_parser.json', encoding='utf-8') as f:
    blueprint_parser = json.load(f)

with open('lib/data/solNodes.json', encoding='utf-8') as f:
    node_parser = json.load(f)


def parse_inventory(overwolf_data):
    inventory_items = {
        'Relics': {},
        'Prime Parts': {},
        'Other': {}
    }

    for item in overwolf_data['MiscItems']:
        if item['ItemType'] in wfcd_api:
            item_name = wfcd_api[item['ItemType']]
            inventory_items[get_category(item_name)][item_name] = item['ItemCount']

    for item in overwolf_data['Recipes']:
        if item['ItemType'] in wfcd_api:
            item_name = wfcd_api[item['ItemType']]
            inventory_items[get_category(item_name)][item_name] = item['ItemCount']
        elif item['ItemType'] in blueprint_parser:
            if blueprint_parser[item['ItemType']] in wfcd_api:
                item_name = f"{wfcd_api[blueprint_parser[item['ItemType']]]} Blueprint"
                inventory_items[get_category(item_name)][item_name] = item['ItemCount']

    for key in inventory_items:
        inventory_items[key] = {k: v for k, v in sorted(inventory_items[key].items())}

    return inventory_items


def parse_forma(overwolf_data):
    translation_dict = {
        'Suits': 'Warframes',
        'LongGuns': 'Primary',
        'Pistols': 'Secondary',
        'Melee': 'Melee',
        'SpaceSuits': 'Archwing',
        'SpaceMelee': 'Archwing',
        'SpaceGuns': 'Archwing',
        'SentinelWeapons': 'Sentinels',
        'Sentinels': 'Sentinels',
        'KubrowPets': 'Pets',
        'Hoverboards': 'K-Drives',
        'MoaPets': 'Pets',
        'MechSuits': 'Necramech',
        'SpecialItems': 'Other'
    }

    forma_dict = {}

    for item in translation_dict:
        forma_dict[translation_dict[item]] = 0

    keys = ['Suits', 'LongGuns', 'Pistols', 'Melee', 'SpaceSuits', 'SpaceMelee', 'SpaceGuns',
            'SentinelWeapons', 'Sentinels', 'KubrowPets', 'SpecialItems', 'Hoverboards',
            'MoaPets', 'MechSuits']

    for key in keys:
        for item in overwolf_data[key]:
            if 'Polarized' in item:
                forma_dict[translation_dict[key]] += item['Polarized']

    return forma_dict


def parse_missions(overwolf_data):
    mission_completions = {}

    for mission in overwolf_data['Missions']:
        try:
            mission_completions[node_parser[mission['Tag']]['node']] = mission['Completes']
        except KeyError:
            pass

    mission_completions = {k: v for k, v in sorted(mission_completions.items(), key=lambda item: item[1], reverse=True)}

    return mission_completions


def parse_xp(overwolf_data):
    xp_data = {}

    for item in overwolf_data['XPInfo']:
        try:
            xp_data[wfcd_api[item['ItemType']]] = item['XP']
        except KeyError:
            pass

    xp_data = {k: v for k, v in sorted(xp_data.items(), key=lambda item: item[1], reverse=True)}

    return xp_data


def diff_handler(dict1, dict2):
    if isinstance(dict1, dict):
        difference = dict(dict1.items() - dict2.items())
        for item in difference:
            try:
                difference[item] -= dict2[item]
            except TypeError:
                pass
            except KeyError:
                pass

        difference = {k: v for k, v in sorted(difference.items(), key=lambda item: item[1], reverse=True)}
    else:
        difference = sorted(list(set(dict1) - set(dict2)))

    return difference


def overwolf_update_handler(old_data, new_data):
    if 'sync_time' in old_data:
        sync_time = old_data['sync_time']
    else:
        sync_time = 0
    changes_dict = {'last_sync': sync_time}

    for key in new_data:
        if key not in ['Arsenal', 'sync_time', 'changes', 'encrypted_data']:
            if not any(isinstance(i, dict) for i in new_data[key].values()):
                changes_dict[key] = diff_handler(new_data[key], old_data[key])
            else:
                changes_dict[key] = {}
                for sub_key in new_data[key]:
                    changes_dict[key][sub_key] = diff_handler(new_data[key][sub_key], old_data[key][sub_key])

    return changes_dict


def decrypt_overwolf_data(encrypted_data):
    config = get_config("config.bot.json")

    # Extract the 'key' and 'iv' values.
    key_str = config['key']
    iv_str = config['iv']


    key = key_str.encode('utf-8')
    iv = iv_str.replace('\\0', '\0').encode('utf-8')
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)

    original_data = unpad(cipher.decrypt(encrypted_data), AES.block_size)

    overwolf_data = json.load(io.BytesIO(original_data))

    return overwolf_data


def parse_overwolf(author_id, sync_time, reparse):
    with open(f"lib/data/overwolf/raw/{author_id}", "rb") as f:
        encrypted_data = f.read()

    return_value = True

    try:
        overwolf_data = decrypt_overwolf_data(encrypted_data)
    except ValueError:
        return_value = False
        with open(f'lib/data/overwolf/raw/{author_id}', encoding='utf-8') as f:
            overwolf_data = json.load(f)

    if 'InventoryJson' in overwolf_data:
        overwolf_data = json.loads(overwolf_data['InventoryJson'])

        with open(f'lib/data/overwolf/raw/{author_id}', 'w') as f0:
            json.dump(overwolf_data, f0, indent=4)

    xp_data = parse_xp(overwolf_data)
    parsed_data = parse_data(overwolf_data, sync_time, return_value)

    if os.path.isfile(f'lib/data/overwolf/data/{author_id}'):
        with open(f'lib/data/overwolf/data/{author_id}', encoding='utf-8') as f:
            old_data = json.load(f)

        if not reparse:
            parsed_data['changes'] = overwolf_update_handler(old_data, parsed_data)
        else:
            if 'sync_time' in old_data:
                parsed_data['sync_time'] = old_data['sync_time']
            else:
                parsed_data['sync_time'] = datetime.datetime.utcnow().timestamp()

            if 'changes' in old_data:
                parsed_data['changes'] = old_data['changes']

    with open(f'lib/data/overwolf/xp/{author_id}', 'w') as f0:
        json.dump(xp_data, f0, indent=4)

    with open(f'lib/data/overwolf/data/{author_id}', 'w') as f0:
        json.dump(parsed_data, f0, indent=4)

    return return_value


def get_category(item_name):
    if any(era in item_name for era in ['Lith ', 'Meso ', 'Neo ', 'Axi ', 'Requiem ']):
        return "Relics"
    if "Prime" in item_name and 'Extractor' not in item_name:
        return "Prime Parts"

    return 'Other'


def parse_name(name):
    if name in parser:
        if isinstance(parser[name], dict):
            mission_node = parser[name]['node']
            if 'planet' in parser[name]:
                mission_node += f" - {parser[name]['planet']}"
            return mission_node
        else:
            if parser[name] == '':
                print(name)

            if parser[name] in parser:
                return parser[parser[name]]
            else:
                return parser[name]
    else:
        return name


def build_data_dict(weapon, forma_count, upgrade_dict):
    data_dict = {'Configs': [], 'Polarity': {}, 'Name': parse_name(weapon['ItemType'])}

    if 'ItemName' in weapon:
        data_dict['PlayerName'] = weapon['ItemName']

    if 'XP' in weapon:
        data_dict['XP'] = weapon['XP']

    if 'Polarized' in weapon:
        data_dict['FormaCount'] = weapon['Polarized']
        forma_count += weapon['Polarized']

    if 'FocusLens' in weapon:
        data_dict['FocusLens'] = parse_name(weapon['FocusLens'])

    if 'ModSlotPurchases' in weapon:
        data_dict['ConfigSlotsPurchased'] = weapon['ModSlotPurchases']

    if 'CustomizationSlotPurchases' in weapon:
        data_dict['AppearanceSlotsPurchased'] = weapon['CustomizationSlotPurchases']

    if 'Configs' in weapon:
        for config in weapon['Configs']:
            config_dict = {'Mods': []}
            mod_list = []

            if 'Upgrades' in config:
                for upgrade in config['Upgrades']:
                    try:
                        mod_list.append(upgrade_dict[upgrade])
                    except KeyError:
                        pass

                config_dict['Mods'] = mod_list

            if 'AbilityOverride' in config and config['AbilityOverride']['Ability']:
                config_dict['HelminthAbility'] = parse_name(config['AbilityOverride']['Ability'])
                config_dict['HelminthSlot'] = config['AbilityOverride']['Index'] + 1

            data_dict['Configs'].append(config_dict)

    if 'Polarity' in weapon:
        for polarity in weapon['Polarity']:
            data_dict['Polarity'][polarity['Slot']] = parse_name(polarity['Value'])

    return data_dict, forma_count


with open('lib/data/parser.json') as f:
    parser = json.load(f)

with open('lib/data/item_type_dict.json') as f:
    item_type_dict = json.load(f)

with open('lib/data/mission_autocomplete', mode='rb') as f:
    mission_autocomplete = pickle.load(f)

with open('lib/data/mod_list', mode='rb') as f:
    mod_list = pickle.load(f)

inventory_autocomplete = []
for prime_set in relic_engine.get_set_list():
    inventory_autocomplete.append(prime_set)
    for prime_part in relic_engine.get_set_parts(prime_set):
        inventory_autocomplete.append(prime_part)

prime_autocomplete = []
relic_autocomplete = relic_engine.get_relic_list()
for prime_set in relic_engine.get_set_list():
    prime_autocomplete.append(prime_set)
    relic_autocomplete.append(prime_set)
    for prime_part in relic_engine.get_set_parts(prime_set):
        prime_autocomplete.append(prime_part)
        relic_autocomplete.append(prime_part)


def parse_data(overwolf_data, sync_time, return_value):
    arsenal_dict = {'Suits': 'Warframe',
                    'LongGuns': 'Primary',
                    'Pistols': 'Secondary',
                    'Melee': 'Melee',
                    'SpaceSuits': 'Archwing',
                    'SpaceGuns': 'Archgun',
                    'SpaceMelee': 'Archmelee',
                    'Sentinels': 'Sentinel',
                    'SentinelWeapons': 'SentinelWeapon',
                    'KubrowPets': 'Pets',
                    'SpecialItems': 'ExaltedWeapons',
                    'MoaPets': 'Moas',
                    'MechSuits': 'Necramech',
                    'CrewShipHarnesses': 'Railjack',
                    'Hoverboards': 'K-Drives',
                    'DataKnives': 'Parazon'}

    parsed_data = {'Profile': {},
                   'Intrinsics': {},
                   'Boosters': {},
                   'Missions': {},
                   'Slots': {'Warframe': {},
                             'Weapon': {},
                             'Sentinel': {},
                             'Archwing': {},
                             'Archweapon': {},
                             'Amp': {},
                             'Salvage': {},
                             'Necramech': {},
                             'CrewMember': {},
                             'Riven': {}},
                   'Inventory': {'Mods': {},
                                 'Skins': [],
                                 'Resources': {},
                                 'SyndicateMedallions': {},
                                 'Relics': {},
                                 'PrimeParts': {},
                                 'PrimeSets': {},
                                 'Fish': {},
                                 'FocusLens': {},
                                 'Components': {},
                                 'Decorations': {},
                                 'Plants': {},
                                 'Forma': {},
                                 'Gems': {},
                                 'AyatanStars': {},
                                 'AyatanSculptures': {},
                                 'Consumables': {},
                                 'Misc': {}},
                   'Arsenal': {'Warframe': [],
                               'Primary': [],
                               'Secondary': [],
                               'Melee': [],
                               'Archwing': [],
                               'Archgun': [],
                               'Archmelee': [],
                               'Sentinel': [],
                               'SentinelWeapon': [],
                               'Pets': [],
                               'ExaltedWeapons': [],
                               'Moas': [],
                               'Necramech': [],
                               'Railjack': [],
                               'K-Drives': [],
                               'Parazon': []},
                   'FormaCount': {'Warframe': 0,
                                  'Primary': 0,
                                  'Secondary': 0,
                                  'Melee': 0,
                                  'Archwing': 0,
                                  'Archgun': 0,
                                  'Archmelee': 0,
                                  'Sentinel': 0,
                                  'SentinelWeapon': 0,
                                  'Pets': 0,
                                  'ExaltedWeapons': 0,
                                  'Moas': 0,
                                  'Necramech': 0,
                                  'Railjack': 0,
                                  'K-Drives': 0},
                   'sync_time': sync_time,
                   'encrypted_data': return_value
                   }

    translation_dict = {'Profile': {'RegularCredits': 'Credits',
                                    'PremiumCredits': 'Platinum',
                                    'PlayerLevel': 'MasteryRank'},
                        'Slots': {'SuitBin': 'Warframe',
                                  'WeaponBin': 'Weapon',
                                  'SentinelBin': 'Sentinel',
                                  'SpaceSuitBin': 'Archwing',
                                  'SpaceWeaponBin': 'Archweapon',
                                  'OperatorAmpBin': 'Amp',
                                  'CrewShipSalvageBin': 'Salvage',
                                  'CrewMemberBin': 'CrewMember',
                                  'MechBin': 'Necramech',
                                  'RandomModBin': 'Riven'},
                        'Inventory': {'RawUpgrades': 'Mods',
                                      'FlavourItems': 'Skins',
                                      'ShipDecorations': 'Decorations',
                                      'FusionTreasures': 'AyatanSculptures',
                                      'WeaponSkins': 'Skins',
                                      'Consumables': 'Consumables'}}

    if 'Created' in overwolf_data:
        parsed_data['Profile']['CreationTime'] = int(overwolf_data['Created']['$date']['$numberLong'][:-3])

    if 'PlayerSkills' in overwolf_data:
        for item in overwolf_data['PlayerSkills']:
            parsed_data['Intrinsics'][parse_name(item)] = overwolf_data['PlayerSkills'][item]

    if 'Boosters' in overwolf_data:
        for item in overwolf_data['Boosters']:
            parsed_data['Boosters'][parse_name(item['ItemType'])] = int(item['ExpiryDate'])

    for key in translation_dict['Profile']:
        if key in overwolf_data:
            parsed_data['Profile'][translation_dict['Profile'][key]] = overwolf_data[key]

    for key in translation_dict['Slots']:
        if key in overwolf_data:
            if 'Slots' in overwolf_data[key]:
                parsed_data['Slots'][translation_dict['Slots'][key]]['Available'] = overwolf_data[key]['Slots']

            if 'Extra' in overwolf_data[key]:
                parsed_data['Slots'][translation_dict['Slots'][key]]['Purchased'] = overwolf_data[key]['Extra']

    for key in translation_dict['Inventory']:
        if key in overwolf_data:
            for item in overwolf_data[key]:
                if 'ItemCount' in item:
                    if parse_name(item['ItemType']) not in parsed_data['Inventory'][translation_dict['Inventory'][key]]:
                        parsed_data['Inventory'][translation_dict['Inventory'][key]][parse_name(item['ItemType'])] = \
                            item[
                                'ItemCount']
                    else:
                        parsed_data['Inventory'][translation_dict['Inventory'][key]][parse_name(item['ItemType'])] += \
                            item[
                                'ItemCount']
                else:
                    parsed_data['Inventory'][translation_dict['Inventory'][key]].append(parse_name(item['ItemType']))

        if 'MiscItems' in overwolf_data:
            for item in overwolf_data['MiscItems']:
                item_name = parse_name(item['ItemType'])

                if any(era in item_name for era in ['Lith ', 'Meso ', 'Neo ', 'Axi ', 'Requiem ']):
                    parsed_data['Inventory']['Relics'][item_name] = item['ItemCount']
                elif "Prime" in item_name and 'Extractor' not in item_name and 'Projections' not in item_name:
                    parsed_data['Inventory']['PrimeParts'][item_name] = item['ItemCount']
                elif item['ItemType'] in item_type_dict:
                    parsed_data['Inventory'][item_type_dict[item['ItemType']]][parse_name(item['ItemType'])] = item[
                        'ItemCount']
                else:
                    parsed_data['Inventory']['Misc'][parse_name(item['ItemType'])] = item['ItemCount']

    upgrade_dict = {}
    if 'Upgrades' in overwolf_data:
        for mod in overwolf_data['Upgrades']:
            try:
                upgrade_dict[mod['ItemId']['$oid']] = parse_name(mod['ItemType'])
            except KeyError:
                continue

            mod_name = parse_name(mod['ItemType'])
            if mod_name in parsed_data['Inventory']['Mods']:
                parsed_data['Inventory']['Mods'][mod_name] += 1
            else:
                parsed_data['Inventory']['Mods'][mod_name] = 1

    for item_Type in arsenal_dict:
        if item_Type in overwolf_data:
            forma_count = 0
            for item in overwolf_data[item_Type]:
                data_dict, forma_count = build_data_dict(item, forma_count, upgrade_dict)

                parsed_data['Arsenal'][arsenal_dict[item_Type]].append(data_dict)

            parsed_data['FormaCount'][arsenal_dict[item_Type]] = forma_count

    if 'Recipes' in overwolf_data:
        for item in overwolf_data['Recipes']:
            if '/Lotus/Types/Recipes/AbilityOverrides/' == item['ItemType'][:38]:
                continue

            item_name = parse_name(item['ItemType'])

            if 'Blueprint' not in item_name:
                item_name += ' Blueprint'

            if "Prime" in item_name and 'Extractor' not in item_name:
                parsed_data['Inventory']['PrimeParts'][item_name] = item['ItemCount']
            elif item['ItemType'] in item_type_dict:
                parsed_data['Inventory'][item_type_dict[item['ItemType']]][item_name] = item[
                    'ItemCount']
            else:
                parsed_data['Inventory']['Misc'][item_name] = item['ItemCount']

    if 'Missions' in overwolf_data:
        for mission in overwolf_data['Missions']:
            try:
                parsed_data['Missions'][parse_name(mission['Tag'])] = mission['Completes']
            except KeyError:
                continue

    total_sets = {}
    for prime_set in relic_engine.get_set_list():
        prime_set = prime_set[:-4]

        total_sets[prime_set] = {'sets': 0,
                                 'parts': {}}
        for prime_part in relic_engine.get_set_parts(prime_set):
            total_sets[prime_set]['parts'][prime_part] = 0

    for prime_part in parsed_data['Inventory']['PrimeParts']:
        try:
            total_sets[relic_engine.get_set_name(prime_part)]['parts'][prime_part] = \
                parsed_data['Inventory']['PrimeParts'][prime_part]
        except KeyError:
            print(f'Unknown Prime Part: {prime_part}')
            print(parsed_data['Inventory']['PrimeParts'][prime_part])

    for prime_set in total_sets:
        parts = []
        for prime_part in total_sets[prime_set]['parts']:
            try:
                parts.append(int(total_sets[prime_set]['parts'][prime_part] /
                                 relic_engine.get_required_amount(prime_part)))
            except (KeyError, TypeError):
                parts.append(0)

        try:
            sets = min(parts)
        except ValueError:
            print(f'Unknown Prime Set: {prime_set}')
            continue

        if sets > 0:
            parsed_data['Inventory']['PrimeSets'][prime_set] = min(parts)

    for key in parsed_data['Inventory']:
        if isinstance(parsed_data['Inventory'][key], dict):
            parsed_data['Inventory'][key] = {k: v for k, v in sorted(parsed_data['Inventory'][key].items())}
        else:
            parsed_data['Inventory'][key] = sorted(parsed_data['Inventory'][key])

    parsed_data['Missions'] = parsed_data['Missions'] = {k: v for k, v in sorted(parsed_data['Missions'].items())}

    parsed_data['changes'] = {}

    return parsed_data


class PageButtons(discord.ui.View):
    def __init__(self, embeds, user):
        self.embeds = embeds
        self.max_page = len(embeds) - 1
        self.current_page = 0
        self.user = user
        super().__init__()

    @discord.ui.button(
        label="Previous Page",
        style=ButtonStyle.green,
        custom_id=f"previous_page"
    )
    async def previous_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user == self.user:
            if self.current_page - 1 < 0:
                self.current_page = self.max_page
            else:
                self.current_page -= 1

            try:
                await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
            except NotFound:
                self.stop()

    @discord.ui.button(
        label="Next Page",
        style=ButtonStyle.green,
        custom_id=f"next_page"
    )
    async def next_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user == self.user:
            if self.current_page + 1 > self.max_page:
                self.current_page = 0
            else:
                self.current_page += 1

            try:
                await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
            except NotFound:
                self.stop()


class Overwolf(GroupCog, name="overwolf"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @command(name='overwolf')
    async def parse_overwolf(self, ctx):
        if len(ctx.message.attachments) == 0:
            alecaframe_location = r'%localappdata%\AlecaFrame'

            no_attachment_string = fr"""
            To use the overwolf commands, you have to upload ``lastData.dat`` to the bot.
            Below are the steps to do this.
            1. Download and install AlecaFrame located here - http://alecaframe.com/
            2. When AlecaFrame is open and ready, restart Warframe and ensure you have a green checkmark in the app.
            3. {f'Type overwolf again and attach the ``lastData.dat`` file located in ``{alecaframe_location}``' if ctx.guild is None else f'DM <@777949472507559976> and type overwolf, while attaching the ``lastData.dat`` file located in ``{alecaframe_location}``'}
            That's it! The commands should work now. Type /overwolf to see the list of commands. Below are screenshots demonstrating the process, if you require additional assistance, feel free to DM <@585035501929758721>.
            """

            image_list = ['https://i.imgur.com/YQk5XPf.png', 'https://i.imgur.com/GONvoLc.png',
                          'https://i.imgur.com/m3wxJhM.png']


            await ctx.send(no_attachment_string)
            for image in image_list:
                await ctx.send(content=image)

        elif ctx.message.attachments[0].filename != "lastData.dat" and ctx.author.id != 585035501929758721:

            try:
                await ctx.message.delete()
            except NotFound:
                pass
            except HTTPException:
                pass

            await ctx.send(r"Unsupported file, "
                           r"make sure you attach your ``lastData.dat`` file found in ``%localappdata%\AlecaFrame``.")
        else:
            await ctx.message.attachments[0].save(f"lib/data/overwolf/raw/{ctx.author.id}")

            try:
                await ctx.message.delete()
            except NotFound:
                pass
            except HTTPException:
                pass

            overwolf_data = parse_overwolf(ctx.author.id, ctx.message.created_at.timestamp(), False)

            if overwolf_data:
                await ctx.send("Successfully saved! You can now run the overwolf commands.")
            else:
                await ctx.send("Your AlecaFrame is out of date, commands will work, "
                               "but your data will be ineligible for leaderboards and other competition data.")
            # except Exception as e:
            #     print(e)
            #
            #     try:
            #         await ctx.message.delete()
            #     except NotFound:
            #         pass
            #     except HTTPException:
            #         pass
            #
            #     await ctx.send("Unspecified exception occured, please contact Guthix on discord.")

    async def embed_handler(self, ctx, embeds):
        allow = True
        ephemeral = True
        if ctx.guild is None or ctx.channel.name == 'bot-spam':
            ephemeral = False
        elif ctx.interaction is None:
            allow = False

        if len(embeds) > 1:
            view = PageButtons(embeds, ctx.author)
        else:
            view = None

        if allow:
            await ctx.send(embed=embeds[0], view=view, ephemeral=ephemeral)
        else:
            self.bot.mdh(ctx.message,
                         await ctx.send("This command is not allowed to be used outside of #botspam or DMs"),
                         ctx.channel, 5)

    @command(name='totalxp')
    async def total_xp(self, ctx):
        try:
            with open(f'lib/data/overwolf/xp/{ctx.author.id}', encoding='utf-8') as f:
                xp_data = json.load(f)
        except FileNotFoundError:
            await ctx.send(r"Could not find your overwolf data!"
                           "\nTo use this command, you first need to use the overwolf command in DMs "
                           r"while attaching your lastData.dat file found in ``%localappdata%\AlecaFrame`` "
                           r"after running AlecaFrame.")
            return

        embed_list = []
        total_count = 0
        for item in xp_data:
            embed_list.append([item, '{:,}'.format(xp_data[item])])
            total_count += xp_data[item]

        embed_list = embed_list[:10]

        embed_list.append(['**Total:**', '{:,}'.format(total_count)])

        embed = Embed(title=f"{ctx.author.name} Total Experience:")

        embed.add_field(name="Item", value="\n".join([item[0] for item in embed_list]))
        embed.add_field(name="XP", value="\n".join([str(item[1]) for item in embed_list]))

        await self.embed_handler(ctx, [embed])

    @command(name='reparsedata')
    async def reparse_data(self, ctx):
        for file in os.listdir("lib/data/overwolf/raw"):
            try:
                parse_overwolf(file, None, True)
            except KeyError as e:
                print(e)
                continue

        await ctx.send("Successfully rebuilt overwolf data.")

    def search_handler(self, item, search, data_type):
        if search is None or not search:
            return True

        if search.lower() in item.lower():
            return True

        if data_type == 'Relics':
            split_relic = item.split()
            fixed_relic = f"{split_relic[0]} {split_relic[1]}"

            if search in refinement_list:
                refinement = fix_refinement(search)
                if split_relic[2] == refinement:
                    return True

            if fixed_relic in relic_engine.get_relic_list():
                for drop in relic_engine.get_relic_drops(fixed_relic, 'i'):
                    if search.lower() in drop.lower():
                        return True
        elif data_type == "Missions":
            try:
                mission_data = parser[parser[item]]
                if 'type' in mission_data:
                    if search.lower() in mission_data['type'].lower():
                        return True

                if 'enemy' in mission_data:
                    if search.lower() in mission_data['enemy'].lower():
                        return True

                if 'tileset' in mission_data:
                    if search.lower() in mission_data['tileset'].lower():
                        return True

            except KeyError:
                pass
        elif data_type == "PrimeParts":
            if search.title() in relic_engine.get_relic_list():
                if any(item == drop for drop in relic_engine.get_relic_drops(search.title(), 'i')):
                    return True

        else:
            pass

        return False

    def check_item(self, amount, value, match_type):
        if match_type == 'N/A':
            return True
        elif match_type is None:
            if amount != value:
                return False
        elif match_type:
            if amount < value:
                return False
        elif not match_type:
            if amount > value:
                return False

        return True

    def get_match_type(self, value):
        match_type = 'N/A'
        value_string = None
        if value is not None:
            match_type = None
            if value[-1] == '+':
                match_type = True
                value = int(value[:-1])
                value_string = f"{value} or above"
            elif value[-1] == '-':
                match_type = False
                value = int(value[:-1])
                value_string = f"{value} or below"
            else:
                if value.isnumeric():
                    value = int(value)
                    value_string = f"{value}"

        return match_type, value, value_string

    def get_mission_info(self, node, amount):
        try:
            mission_data = parser[parser[node]]
        except KeyError:
            mission_data = {}

        mission_type = 'N/A'
        mission_enemy = 'N/A'
        if 'type' in mission_data:
            mission_type = mission_data['type']

        if 'enemy' in mission_data:
            mission_enemy = mission_data['enemy']

        return [node, amount, mission_type, mission_enemy]

    def get_data_embed(self, overwolf_data, data_type, name):
        if data_type == "Profile":
            embed_description = ""
            for data in overwolf_data['Profile']:
                if data == "CreationTime":
                    formatted_data = f"<t:{int(overwolf_data['Profile'][data])}:f>"
                else:
                    formatted_data = overwolf_data['Profile'][data]
                    if isinstance(formatted_data, int):
                        formatted_data = '{:,}'.format(formatted_data)

                embed_description += f"**{data}:** {formatted_data}\n"

            embed = discord.Embed(title=f"{name} {data_type}", description=embed_description)
            return embed
        elif data_type == "FormaCount":
            embed_list = []
            total_count = 0
            for item in overwolf_data['FormaCount']:
                embed_list.append([item, str(overwolf_data['FormaCount'][item])])
                total_count += overwolf_data['FormaCount'][item]

            embed_list = embed_list[:-1]

            embed_list.append(['**Total:**', str(total_count)])

            embed = Embed(title=f"{name} Total Formas Used:")

            embed.add_field(name="Category", value="\n".join([item[0] for item in embed_list]))
            embed.add_field(name="Amount", value="\n".join([str(item[1]) for item in embed_list]))

            return embed
        elif data_type == 'Slots':
            embed_list = []
            for item in overwolf_data['Slots']:
                available = '0'
                purchased = '0'
                if 'Available' in overwolf_data['Slots'][item]:
                    available = str(overwolf_data['Slots'][item]['Available'])

                if 'Purchased' in overwolf_data['Slots'][item]:
                    purchased = str(overwolf_data['Slots'][item]['Purchased'])
                if item == 'Riven':
                    available = 'N/A'

                embed_list.append([item, available, purchased])

            embed_list = embed_list

            embed = Embed(title=f"{name} Slots:")

            embed.add_field(name="Category", value="\n".join([item[0] for item in embed_list]))
            embed.add_field(name="Available", value="\n".join([str(item[1]) for item in embed_list]))
            embed.add_field(name="Purchased", value="\n".join([str(item[2]) for item in embed_list]))

            return embed
        elif data_type == 'Intrinsics':
            embed_list = []
            for item in overwolf_data['Intrinsics']:
                data = overwolf_data['Intrinsics'][item]
                if item == 'Points':
                    data = int(data / 1000)

                embed_list.append([item, data])

            embed_list = embed_list

            embed = Embed(title=f"{name} Intrinsics:")

            embed.add_field(name="Skill", value="\n".join([item[0] for item in embed_list]))
            embed.add_field(name="Level", value="\n".join([str(item[1]) for item in embed_list]))

            return embed
        elif data_type == 'Boosters':
            embed_list = []
            for item in overwolf_data['Boosters']:
                embed_list.append([item, f"<t:{int(overwolf_data['Boosters'][item])}:f>"])
            embed_list = embed_list

            embed = Embed(title=f"{name} Boosters:")

            embed.add_field(name="Booster", value="\n".join([item[0] for item in embed_list]))
            embed.add_field(name="Expires/Expired", value="\n".join([str(item[1]) for item in embed_list]))

            return embed
        elif data_type == 'changes':
            embed = discord.Embed()

            embed_description = ""
            changes = overwolf_data['changes']
            if len(changes['Profile']) != 0:
                embed_description += "**Profile:**\n"
                if 'Platinum' in changes['Profile']:
                    platinum = changes['Profile']['Platinum']
                    format_platinum = '{:,}'.format(abs(platinum))
                    embed_description += f"You have {'gained' if platinum > 0 else 'lost'} **{format_platinum}** platinum.\n"

                if 'Credits' in changes['Profile']:
                    credits = changes['Profile']['Credits']
                    format_credits = '{:,}'.format(abs(credits))
                    embed_description += f"You have {'gained' if credits > 0 else 'lost'} **{format_credits}** credits.\n"

                if 'MasteryRank' in changes['Profile']:
                    mastery_rank = changes['Profile']['Credits']
                    embed_description += f"You have gained {mastery_rank} mastery rank{'s' if mastery_rank > 1 else ''}\n"

                embed_description += '\n'

            if len(changes['Intrinsics']) != 0:
                embed_description += "**Intrinsics:**\n"
                for key in changes['Intrinsics']:
                    if key != 'Points':
                        level_gained = changes['Intrinsics'][key]
                        embed_description += f"You have gained {level_gained} level{'s' if level_gained > 1 else ''} in {key}\n"

                embed_description += '\n'

            if len(changes['Missions']) > 0:
                missions_completed = 0
                mission_list = []
                for mission in changes['Missions']:
                    mission_list.append(f"{changes['Missions'][mission]}x {mission}")
                    missions_completed += changes['Missions'][mission]

                field_name = f'**Misisons Completed:** {missions_completed}\n'

                embed.add_field(name=field_name, value='\n'.join(mission_list[:10]))

            for key in ['Relics', 'PrimeParts', 'PrimeSets', 'Mods']:
                if len(changes['Inventory'][key]) > 0:
                    total_change = 0
                    change_list = []
                    for item in changes['Inventory'][key]:
                        change_list.append(f"{changes['Inventory'][key][item]}x {item}")
                        total_change += changes['Inventory'][key][item]

                    if total_change != 0:
                        if key == 'Relics':
                            item_adjective = 'used/sold:**'
                        else:
                            item_adjective = 'sold:**'

                        field_name = f"**{key} Net Change:** {total_change}"

                    embed.add_field(name=field_name, value='\n'.join(change_list[:10]), inline=False)

            last_sync = changes['last_sync']
            if last_sync != 0 and last_sync is not None:
                last_sync = f"<t:{int(last_sync)}:f>"
            else:
                last_sync = 'last sync'

            if not embed_description and len(embed.fields) == 0:
                embed_description = "There were no changes detected in your most recent sync."
            elif len(embed.fields) > 0:
                embed_description += "Below shows at most 10 of each, if you want more detail, " \
                                     "use the relevant /overwolf command and set the changes option to True."

            embed.title = f"**Changes since {last_sync}:**"
            embed.description = embed_description
            return embed
        else:
            print('Unknown data type')

    def get_item_price(self, item, data_type, value_key):
        if data_type == "Relics":
            return get_relic_value(item)
        elif get_set_name(item) in relic_engine.get_set_list() and (
                data_type == 'PrimeParts' or data_type == 'PrimeSets'):
            try:
                if value_key == 'Ducats':
                    return relic_engine.get_ducats(item)
            except KeyError:
                pass

        return self.bot.market_db.get_item_price(item)

    def get_inventory_embed(self, overwolf_data, data_type, name, search, quantity, changes, min_value=None,
                            value_key='Platinum', sort_key=1):
        if data_type == "Missions":
            if not changes:
                dict_location = overwolf_data[data_type]
            else:
                dict_location = overwolf_data['changes'][data_type]
            value_toggle = False
        else:
            if not changes:
                dict_location = overwolf_data['Inventory'][data_type]
            else:
                dict_location = overwolf_data['changes']['Inventory'][data_type]
            value_toggle = True
        match_type, quantity, quantity_string = self.get_match_type(quantity)

        if value_toggle:
            value_type, min_value, min_value_string = self.get_match_type(min_value)

        cumulative_quantity = 0
        if value_toggle:
            cumulative_value = 0
        unique_amount = 0

        embed_list = []
        for item in dict_location:
            if not self.search_handler(item, search, data_type):
                continue

            try:
                item_amount = dict_location[item]
            except TypeError:
                item_amount = 1

            if not self.check_item(item_amount, quantity, match_type):
                continue

            if value_toggle:
                item_value = self.get_item_price(item, data_type, value_key)

                if not self.check_item(item_value, min_value, value_type):
                    continue

                total_value = item_value * item_amount
                cumulative_value += total_value

            unique_amount += 1
            cumulative_quantity += item_amount

            if data_type == "Missions":
                embed_list.append(self.get_mission_info(item, dict_location[item]))
            elif data_type == 'PrimeParts':
                embed_list.append([fix_name(item), item_amount, int(item_value), int(total_value)])
            else:
                embed_list.append([item, item_amount, int(item_value), int(total_value)])

        embeds = []
        embed_description = ""
        if search is not None:
            embed_description += f"**Search:** {search}\n"

        if quantity is not None:
            embed_description += f"**Quantity:** {quantity_string}\n"

        if min_value is not None:
            embed_description += f"**Minimum Value:** {min_value_string}\n"

        embed_description += f"**Unique Amount:** {unique_amount}\n" \
                             f"**Total Amount:** {'{:,}'.format(cumulative_quantity)}"

        if data_type == "PrimeSets" or data_type == "PrimeParts":
            embed_description += f"\n**Value Type:** {value_key}"

        if value_toggle:
            embed_description += f"\n**Total Value:** {'{:,}'.format(int(cumulative_value))}"

        if data_type == "Relics" and quantity == 0 and match_type is None:
            for relic in relic_engine.get_relic_list():
                for refinement in refinement_list_new:
                    relic = f"{relic} Relic {refinement}"
                    if relic not in dict_location:
                        embed_list.append([relic, 0, 0, 0])

        embed_list.sort(key=lambda x: x[sort_key], reverse=True)

        title = f"{name} {data_type}"
        if changes:
            last_sync = overwolf_data['changes']['last_sync']
            if last_sync != 0 and last_sync is not None:
                last_sync = f"<t:{int(last_sync)}:f>"
            else:
                last_sync = 'last sync'

            title += f": Changes since {last_sync}"

        for content in list(chunked(embed_list, 10)):
            embed = discord.Embed(title=title, description=embed_description)

            item_embed = '\n'.join([f"{'{:,}'.format(x[1])}x {x[0]}" for x in content])

            if value_toggle:
                value_embed = '\n'.join([f"{'{:,}'.format(x[2])}" for x in content])
                total_value_embed = '\n'.join(['{:,}'.format(x[3]) for x in content])
            else:
                mission_type_embed = '\n'.join([x[2] for x in content])
                mission_enemy_embed = '\n'.join([x[3] for x in content])

            embed.add_field(name='Item', value=item_embed)

            if value_toggle:
                embed.add_field(name=f'Value', value=value_embed)
                embed.add_field(name=f'Total Value', value=total_value_embed)
            else:
                embed.add_field(name='Type', value=mission_type_embed)
                embed.add_field(name='Enemy', value=mission_enemy_embed)

            embeds.append(embed)

        return embeds

    @commands.hybrid_command(name='profile', description="Get overwolf profile data.",
                             aliases=['formacount'])
    @app_commands.choices(data_type=[
        Choice(name='Profile - Mastery Rank, Plat, Credits, Creation Date', value='Profile'),
        Choice(name='Forma Count - Total Formas Used', value='FormaCount'),
        Choice(name='Slots - Total Slots Used/Available', value='Slots'),
        Choice(name='Intrinsics - Railjack Intrinsic Levels', value='Intrinsics'),
        Choice(name='Boosters - Booster Expiry Times', value='Boosters'),
        Choice(name='Changes - Show Overview of Changes Since Last Sync', value='changes'),
    ])
    @app_commands.describe(data_type="The data you wish to get.")
    async def get_overwolf_data(self, ctx: commands.Context, data_type: str):
        try:
            with open(f'lib/data/overwolf/data/{ctx.author.id}', encoding='utf-8') as f:
                overwolf_data = json.load(f)
        except FileNotFoundError:
            await ctx.send(r"Could not find your overwolf data!"
                           "\nTo use this command, you first need to use the overwolf command in DMs "
                           r"while attaching your lastData.dat file found in ``%localappdata%\AlecaFrame`` "
                           r"after running AlecaFrame.")
            return

        if ctx.message.content[2:] == 'formacount':
            data_type = 'FormaCount'

        embed = self.get_data_embed(overwolf_data, data_type, ctx.author.name)

        await self.embed_handler(ctx, [embed])

    @commands.hybrid_command(name='inventory', description="Get overwolf inventory data.")
    @app_commands.choices(data_type=[
        Choice(name='Resources', value='Resources'),
        Choice(name='Ayatan Sculptures', value='AyatanSculptures'),
        Choice(name='Ayatan Stars', value='AyatanStars'),
        Choice(name='Consumables', value='Consumables'),
        Choice(name='Focus Lens', value='FocusLens'),
        Choice(name='Decorations', value='Decorations'),
        Choice(name='Fish', value='Fish'),
        Choice(name='Plants', value='Plants'),
        Choice(name='Forma', value='Forma'),
        Choice(name='Cosmetic Items, Skins, and Glyphs', value='Skins'),
        Choice(name='Syndicate Medallions', value='SyndicateMedallions'),
        Choice(name='Focus Lens', value='FocusLens'),
        Choice(name='Components', value='Components'),
        Choice(name='Gems', value='Gems'),
        Choice(name='Miscellaneous', value='Misc'),
    ],
        sort_column=[
            Choice(name='Quantity', value=1),
            Choice(name='Value', value=2),
            Choice(name='Total Value', value=3)
        ]
    )
    @app_commands.describe(data_type="The data you wish to get.",
                           search="Something in the data to search for.",
                           quantity="Quantity of item you want, "
                                    "add + after to specify that number or higher, or - for that number or lower.",
                           min_value="Value of the item you want, "
                                     "add + after to specify that number or higher, or - for that number or lower.",
                           changes="Whether you only want to show changes since last sync, defaults to false.",
                           sort_column="The column you want to sort by, defaults to quantity.")
    async def get_inventory_data(self, ctx: commands.Context, data_type: str, search: Optional[str],
                                 quantity: Optional[str], min_value: Optional[str], changes: bool = False,
                                 sort_column: int = 1):
        try:
            with open(f'lib/data/overwolf/data/{ctx.author.id}', encoding='utf-8') as f:
                overwolf_data = json.load(f)
        except FileNotFoundError:
            await ctx.send(r"Could not find your overwolf data!"
                           "\nTo use this command, you first need to use the overwolf command in DMs "
                           r"while attaching your lastData.dat file found in ``%localappdata%\AlecaFrame`` "
                           r"after running AlecaFrame.")
            return

        if not min_value:
            min_value = None

        if not search:
            search = None

        if not quantity:
            quantity = None

        embeds = self.get_inventory_embed(overwolf_data, data_type, ctx.author.name, search, quantity, changes,
                                          min_value)

        if len(embeds) > 0:
            await self.embed_handler(ctx, embeds)
        else:
            await ctx.send("Could not find any items that matches the criteria you specified.")

    @commands.hybrid_command(name='prime', description="Get overwolf prime part data.",
                             aliases=['pv', 'partvalue', 'totalsets', 'totalducats'])
    @app_commands.choices(data_type=[
        Choice(name='Prime Sets', value='PrimeSets'),
        Choice(name='Prime Parts', value='PrimeParts')
    ],
        value_type=[
            Choice(name='Ducats', value='Ducats'),
            Choice(name='Platinum', value='Platinum'),
            Choice(name='Ducats / Platinum', value='Ducats/Platinum')
        ],
        sort_column=[
            Choice(name='Quantity', value=1),
            Choice(name='Value', value=2),
            Choice(name='Total Value', value=3)
        ]
    )
    @app_commands.describe(data_type="The data you wish to get.",
                           value_type="Whether to get platinum or ducat values.",
                           search="Something in the data to search for.",
                           quantity="Quantity of item you want, "
                                    "add + after to specify that number or higher, or - for that number or lower.",
                           min_value="Value of the item you want, "
                                     "add + after to specify that number or higher, or - for that number or lower.",
                           changes="Whether you only want to show changes since last sync, defaults to false.",
                           sort_column="The column you want to sort by, defaults to quantity.")
    async def get_prime_data(self, ctx: commands.Context, data_type: Optional[str], value_type: Optional[str],
                             search: Optional[str], quantity: Optional[str], min_value: Optional[str],
                             changes: bool = False, sort_column: int = 1):
        if ctx.message is not None:
            split_message = ctx.message.content.split()
            if len(split_message) == 2:
                if split_message[1] == "kill" and split_message[0] == "--pv":
                    await ctx.send("PV has been killed.")
                    return

            if ctx.message.content[2:] == 'totalsets':
                data_type = 'PrimeSets'

            if ctx.message.content[2:] == 'totalducats':
                value_type = "Ducats"

        try:
            with open(f'lib/data/overwolf/data/{ctx.author.id}', encoding='utf-8') as f:
                overwolf_data = json.load(f)
        except FileNotFoundError:
            await ctx.send(r"Could not find your overwolf data!"
                           "\nTo use this command, you first need to use the overwolf command in DMs "
                           r"while attaching your lastData.dat file found in ``%localappdata%\AlecaFrame`` "
                           r"after running AlecaFrame.")
            return

        if data_type is None:
            data_type = "PrimeParts"

        if value_type is None:
            value_type = 'Platinum'

        embeds = self.get_inventory_embed(overwolf_data, data_type, ctx.author.name,
                                          search, quantity, changes, min_value, value_type,
                                          sort_key=sort_column)

        if len(embeds) > 0:
            await self.embed_handler(ctx, embeds)
        else:
            await ctx.send("Could not find any items that matches the criteria you specified.")

    @commands.hybrid_command(name='relics', description="Get overwolf relic data.", aliases=['rv', 'relicvalue'])
    @app_commands.choices(sort_column=[
        Choice(name='Quantity', value=1),
        Choice(name='Value', value=2),
        Choice(name='Total Value', value=3)
    ])
    @app_commands.describe(search="Something in the data to search for.",
                           quantity="Quantity of item you want, "
                                    "add + after to specify that number or higher, or - for that number or lower.",
                           min_value="Value of the item you want, "
                                     "add + after to specify that number or higher, or - for that number or lower.",
                           changes="Whether you only want to show changes since last sync, defaults to false.",
                           sort_column="The column you want to sort by, defaults to quantity.")
    async def get_relic_data(self, ctx: commands.Context, search: Optional[str],
                             quantity: Optional[str], min_value: Optional[str], changes: bool = False,
                             sort_column: int = 1):
        split_message = ctx.message.content.split()
        if len(split_message) == 2:
            if split_message[1] == "kill" and split_message[0] == "--rv":
                await ctx.send("RV has been killed.")
                return

        try:
            with open(f'lib/data/overwolf/data/{ctx.author.id}', encoding='utf-8') as f:
                overwolf_data = json.load(f)
        except FileNotFoundError:
            await ctx.send(
                r"Could not find your overwolf data!\nTo use this command, you first "
                r"need to use the overwolf command in DMs while attaching your "
                r"lastData.dat file found in ``%localappdata%\AlecaFrame`` "
                r"after running AlecaFrame.")
            return

        if not min_value:
            min_value = None

        if not search:
            search = None

        if not quantity:
            quantity = None

        embeds = self.get_inventory_embed(overwolf_data, "Relics", ctx.author.name, search, quantity, changes,
                                          min_value, sort_key=sort_column)

        if len(embeds) > 0:
            await self.embed_handler(ctx, embeds)
        else:
            await ctx.send("Could not find any items that matches the criteria you specified.")

    @commands.hybrid_command(name='mods', description="Get overwolf mod data.")
    @app_commands.choices(sort_column=[
        Choice(name='Quantity', value=1),
        Choice(name='Value', value=2),
        Choice(name='Total Value', value=3)
    ])
    @app_commands.describe(search="Something in the data to search for.",
                           quantity="Quantity of item you want, "
                                    "add + after to specify that number or higher, or - for that number or lower.",
                           min_value="Value of the item you want, "
                                     "add + after to specify that number or higher, or - for that number or lower.",
                           changes="Whether you only want to show changes since last sync, defaults to false.",
                           sort_column="The column you want to sort by, defaults to quantity.")
    async def get_mod_data(self, ctx: commands.Context, search: Optional[str],
                           quantity: Optional[str], min_value: Optional[str], changes: bool = False,
                           sort_column: int = 1):
        try:
            with open(f'lib/data/overwolf/data/{ctx.author.id}', encoding='utf-8') as f:
                overwolf_data = json.load(f)
        except FileNotFoundError:
            await ctx.send(
                r"Could not find your overwolf data!\nTo use this command, you first "
                r"need to use the overwolf command in DMs while attaching your "
                r"lastData.dat file found in ``%localappdata%\AlecaFrame`` "
                r"after running AlecaFrame.")
            return

        if not min_value:
            min_value = None

        if not search:
            search = None

        if not quantity:
            quantity = None

        embeds = self.get_inventory_embed(overwolf_data, "Mods", ctx.author.name, search, quantity, changes,
                                          min_value, sort_key=sort_column)

        if len(embeds) > 0:
            await self.embed_handler(ctx, embeds)
        else:
            await ctx.send("Could not find any items that matches the criteria you specified.")

    @commands.hybrid_command(name='missions', description="Get overwolf mission data.",
                             aliases=['missioncount'])
    @app_commands.describe(search="Something in the data to search for.",
                           quantity="Quantity of item you want, "
                                    "add + after to specify that number or higher, or - for that number or lower.",
                           changes="Whether you only want to show changes since last sync, defaults to false.")
    async def get_mission_data(self, ctx: commands.Context, search: Optional[str], quantity: Optional[str],
                               changes: bool = False):
        try:
            with open(f'lib/data/overwolf/data/{ctx.author.id}', encoding='utf-8') as f:
                overwolf_data = json.load(f)
        except FileNotFoundError:
            await ctx.send(r"Could not find your overwolf data!"
                           "\nTo use this command, you first need to use the overwolf command in DMs "
                           r"while attaching your lastData.dat file found in ``%localappdata%\AlecaFrame`` "
                           r"after running AlecaFrame.")
            return

        if not search:
            search = None

        if not quantity:
            quantity = None

        embeds = self.get_inventory_embed(overwolf_data, 'Missions', ctx.author.name, search, quantity, changes)

        if len(embeds) > 0:
            await self.embed_handler(ctx, embeds)
        else:
            await ctx.send("Could not find any items that matches the criteria you specified.")

    @commands.command(name='missingrelics')
    async def missing_relics(self, ctx: commands.Context, refinement: str):
        try:
            with open(f'lib/data/overwolf/data/{ctx.author.id}', encoding='utf-8') as f:
                overwolf_data = json.load(f)
        except FileNotFoundError:
            await ctx.send(
                "Could not find your overwolf data!\nTo use this command, you first "
                r"need to use the overwolf command in DMs while attaching your "
                r"lastData.dat file found in ``%localappdata%\AlecaFrame`` "
                r"after running AlecaFrame.")
            return

        search = fix_refinement(refinement)

        embeds = self.get_inventory_embed(overwolf_data, "Relics", ctx.author.name, search, 0, False)

        if len(embeds) > 0:
            await self.embed_handler(ctx, embeds)
        else:
            await ctx.send("Could not find any items that matches the criteria you specified.")

    @get_mod_data.autocomplete('search')
    async def mod_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return [app_commands.Choice(name=item, value=item) for item in mod_list if current.lower() in item.lower()][:10]

    @get_relic_data.autocomplete('search')
    async def mod_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return [app_commands.Choice(name=item, value=item) for item in relic_autocomplete if
                current.lower() in item.lower()][:10]

    @get_prime_data.autocomplete('search')
    async def mod_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return [app_commands.Choice(name=item, value=item) for item in prime_autocomplete if
                current.lower() in item.lower()][:10]

    @get_mission_data.autocomplete('search')
    async def mod_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return [app_commands.Choice(name=item, value=item) for item in mission_autocomplete if
                current.lower() in item.lower()][:10]

    @command(name='export')
    async def export_data(self, ctx):
        if ctx.guild is not None:
            message = await ctx.send("This command only works in direct messages.", delete_after=5)
            return

        try:
            with open(f'lib/data/overwolf/data/{ctx.author.id}', mode='rb') as f:
                await ctx.send(file=discord.File(fp=f, filename='overwolf_data.json'))
        except FileNotFoundError:
            await ctx.send(r"Could not find your overwolf data!"
                           "\nTo use this command, you first need to use the overwolf command in DMs "
                           r"while attaching your lastData.dat file found in ``%localappdata%\AlecaFrame`` "
                           r"after running AlecaFrame.")
            return

    @command(name='rawexport')
    async def raw_export_data(self, ctx):
        if ctx.guild is not None:
            message = await ctx.send("This command only works in direct messages.", delete_after=5)
            return

        try:
            with open(f"lib/data/overwolf/raw/{ctx.author.id}", "rb") as f:
                encrypted_data = f.read()

                overwolf_data = decrypt_overwolf_data(encrypted_data)

                overwolf_file = BytesIO()

                json.dump(overwolf_data, overwolf_file)

                overwolf_file.seek(0)

                await ctx.send(file=discord.File(fp=overwolf_file, filename="raw_export.json"))
        except FileNotFoundError:
            await ctx.send(r"Could not find your overwolf data!"
                           "\nTo use this command, you first need to use the overwolf command in DMs "
                           r"while attaching your lastData.dat file found in ``%localappdata%\AlecaFrame`` "
                           r"after running AlecaFrame.")
            return
        except ValueError:
            await ctx.send("File is not encrpyted, so there is no need to decrypt, just open it as is.")
            return

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.bot.cogs_ready.ready_up("Overwolf")


async def setup(bot):
    await bot.add_cog(Overwolf(bot))
