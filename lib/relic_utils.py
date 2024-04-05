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
era_list = ['Lith', 'Meso', 'Neo', 'Axi']


# Changes refinement to required format.
def fix_refinement(refinement):
    if refinement == "int" or refinement == "i" or refinement == "intact":
        return "Intact"
    elif refinement == "excep" or refinement == "exc" or refinement == "e" or refinement == "exceptional":
        return "Exceptional"
    elif refinement == "flaw" or refinement == "f" or refinement == "flawless":
        return "Flawless"
    elif refinement == "rad" or refinement == "r" or refinement == "radiant":
        return "Radiant"


# Uses default if no style selected
def use_default(relic):
    def find_style(current_relic):
        if current_relic not in relic_style_defaults:
            return '4b4r'
        else:
            return relic_style_defaults[current_relic]['styles']['default']

    ref = find_style(relic)

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


def get_price_data(pd_file):
    if pd_file is None:
        soup = BeautifulSoup(requests.get('http://relics.run/history/').text, 'html.parser')
        return requests.get(sorted(['http://relics.run/history/' + node.get('href')
                                    for node in soup.find_all('a') if node.get('href').endswith('json')])[-1]).json()
    else:
        return requests.get(f"http://relics.run/history/{pd_file}").json()


price_data = get_price_data(None)


def update_part_prices(debug=False):
    global price_data
    pd = get_price_data(None)
    price_data.update(pd)
