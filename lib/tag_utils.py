import json
from random import choice

from discord import Embed

with open('lib/data/tag_data.json') as f:
    tag_data = json.load(f)


def update_tag_data():
    with open('lib/data/tag_data.json', 'w') as fp:
        json.dump(tag_data, fp, indent=4)


def get_tag_embed():
    tag_names = []
    for tag in tag_data:
        tag_names.append(tag)

    tag_names.sort()

    embed = Embed(title="Tags (" + str(len(tag_data)) + ")", description=", ".join(tag_names))
    embed.set_footer(text="Use \"--tag name\" or just \"--name\" to show a tag")

    return embed


def new_tag(tag_name, tag_contents):
    if tag_name == 'random':
        return "That is a reserved word and cannot be used."

    if not (tag_name[:2] == '<:' and tag_name[-1] == '>'):
        tag_name = tag_name.lower()

    if tag_name in tag_data:
        tag_data[tag_name]['content'] = tag_contents
        update_tag_data()
        return f"Successfully updated {tag_name} with new contents."
    else:
        tag_data[tag_name] = {
            'content': tag_contents,
            'autodelete': True,
            'dm': False
        }
        update_tag_data()
        return f"Successfully created {tag_name}."


def delete_tag(tag_name):
    if tag_name in tag_data:
        del tag_data[tag_name]
        update_tag_data()
        return f"Successfully removed the tag {tag_name}."
    else:
        return f"Could not find the tag {tag_name} in the tag list."


def change_attribute(tag_name, attribute):
    if tag_name in tag_data:
        tag_data[tag_name][attribute] = not tag_data[tag_name][attribute]
        update_tag_data()
        if attribute == "autodelete":
            text = "auto delete the tag command message"
        elif attribute == "dm":
            text = "DM the tag's contents"
        return f"Successfully changed the tag {tag_name} to{'' if tag_data[tag_name][attribute] else ' not'} {text}."
    else:
        return f"Could not find the tag {tag_name}."


def get_tag(tag_name):
    if tag_name.lower() in tag_data:
        return tag_data[tag_name.lower()]
    elif tag_name in tag_data:
        return tag_data[tag_name]
    elif tag_name.lower() == 'random':
        return tag_data[choice(list(tag_data))]
    else:
        return False


def check_tag_exists(tag_name):
    if tag_name in tag_data:
        return tag_name
    else:
        return False
