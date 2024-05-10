import json
import relic_engine
import requests
from bs4 import BeautifulSoup

try:
    with open('lib/data/default_data.json', 'r') as rel_style:
        relic_style_defaults = json.load(rel_style)
except FileNotFoundError:
    relic_style_defaults = {}
    with open('lib/data/default_data.json', 'w') as fp:
        json.dump(relic_style_defaults, fp, indent=4)

style_list_new = ['Solo', '1b1', '2b2', '3b3', '4b4']
refinement_list_new = ['Intact', 'Exceptional', 'Flawless', 'Radiant']

style_list = ['sol', '1b1', '2b2', '3b3', '4b4']
refinement_list = ["i", "int", "intact",
                   "e", "excep", "exc", "exceptional",
                   "f", "flaw", "flawless",
                   "r", "rad", "radiant"]
era_list = ['Lith', 'Meso', 'Neo', 'Axi', 'Requiem']


# Changes refinement to required format.
def fix_refinement(refinement):
    refinement_map = {
        "i": "Intact",
        "e": "Exceptional",
        "f": "Flawless",
        "r": "Radiant"
    }
    return refinement_map[refinement[0].lower()]

# Uses default if no style selected
def use_default(relic):
    # Format the relic string
    relic = relic.title()

    ref = relic_style_defaults.get(relic, {'styles': {'default': '4b4r'}})['styles']['default']
    return [fix_refinement(ref[-1:])], ref[:-1]


def get_average(relic, style, refinement):
    return relic_engine.get_average_return(relic, style, refinement)


run_average_dict = {
    '1b1': 4,
    '2b2': 2,
    '3b3': 4 / 3,
    '4b4': 1
}


def get_run_average(average, style):
    return int(average / run_average_dict[style])


