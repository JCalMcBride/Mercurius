import json

with open('lib/data/starboard_data.json') as f:
    x = json.load(f)
    starboards = {int(k): v for k, v in x.items()}

for server in starboards:
    starboards[server] = {int(k): v for k, v in starboards[server].items() if k.isnumeric()}

with open('lib/data/sb_message_data.json') as f:
    x = json.load(f)
    sb_messages = {int(k): v for k, v in x.items()}

for emoji in sb_messages:
    sb_messages[emoji] = {int(k): v for k, v in sb_messages[emoji].items() if k.isnumeric()}


def update_starboard_data():
    with open('lib/data/starboard_data.json', 'w') as fp:
        json.dump(starboards, fp, indent=4)


def update_sb_message_data():
    with open('lib/data/sb_message_data.json', 'w') as fp:
        json.dump(sb_messages, fp, indent=4)


def new_sb_message(message_id, emoji_id, guild_id, channel_id, starcount):
    message_id, emoji_id, guild_id, channel_id, starcount


def add_new_starboard(guild_id, emoji_id, channel_id, needed):
    if guild_id not in starboards:
        starboards[guild_id] = {}

    if emoji_id in starboards[guild_id]:
        return_msg = "Successfully replaced old starboard with new one."
    else:
        return_msg = "Successfully added new starboard."

    starboards[guild_id][emoji_id] = {
        'channel': channel_id,
        'needed': needed
    }

    if emoji_id not in sb_messages:
        sb_messages[emoji_id] = {}
        update_sb_message_data()

    update_starboard_data()
    return return_msg


def update_star_count(guild_id, emoji_id, needed):
    try:
        starboards[guild_id][emoji_id]['needed'] = needed
        update_starboard_data()
        return f"Set the number of required emojis to {needed}."
    except KeyError:
        return "Could not find that starboard!"


def get_guild_starboard_emojis(guild_id):
    if guild_id in starboards:
        return list(starboards[guild_id])
    else:
        return None


def get_guild_starboard_channels(guild_id):
    starboard_channels = []
    for sb in starboards[guild_id]:
        starboard_channels.append(starboards[guild_id][sb]['channel'])
    return starboard_channels


def get_sb_data(guild_id, emoji_id):
    return starboards[guild_id][emoji_id]


def add_new_sb_message(root_message_id, emoji_id, star_message_id):
    sb_messages[emoji_id][root_message_id] = star_message_id


def get_sb_message(root_message_id, emoji_id):
    if root_message_id in sb_messages[emoji_id]:
        return sb_messages[emoji_id][root_message_id]
    else:
        return None
