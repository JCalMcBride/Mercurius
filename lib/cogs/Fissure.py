import asyncio
import traceback
import uuid
from asyncio import sleep
from collections import defaultdict
from datetime import datetime, timedelta
from pprint import pprint
from typing import List, Union

import discord
from aiohttp import ClientOSError
from discord import app_commands, DiscordServerError
from discord.app_commands import Choice
from discord.ext import commands, tasks
from discord.ext.commands import Cog
from fissure_engine import fissure_engine
from fissure_engine.common import sol_nodes
from fissure_engine.fissure_engine import FissureEngine
from pymysql import IntegrityError
from pytz import UTC


class StatusNotificationView(discord.ui.View):
    def __init__(self, bot, user_id, status_settings):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.status_options = {
            'Online': 'online',
            'Idle': 'idle',
            'Do Not Disturb': 'dnd',
            'Offline': 'offline'
        }
        self.status_settings = status_settings
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        for status, status_key in self.status_options.items():
            enabled = self.status_settings.get(status_key, True)
            style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger
            button = discord.ui.Button(label=status, style=style)
            button.callback = self.create_button_callback(status_key)
            self.add_item(button)

    def create_button_callback(self, status_key):
        async def button_callback(interaction: discord.Interaction):
            self.status_settings[status_key] = not self.status_settings.get(status_key, True)
            self.bot.database.set_fissure_notification_status(self.user_id, status_key,
                                                              self.status_settings[status_key])
            self.update_buttons()
            await interaction.response.edit_message(view=self)

        return button_callback


class ThreadNotificationServerSelectView(discord.ui.View):
    def __init__(self, bot, ctx, user_servers, message):
        super().__init__()
        self.bot = bot
        self.ctx = ctx
        self.user_servers = user_servers
        self.message = message

        server_select = discord.ui.Select(
            placeholder="Select a server",
            options=[discord.SelectOption(label=server.name, value=str(server.id)) for server in user_servers]
        )
        server_select.callback = self.on_server_select
        self.add_item(server_select)

    async def on_server_select(self, interaction: discord.Interaction):
        selected_server_id = int(interaction.data['values'][0])
        selected_server = self.bot.get_guild(selected_server_id)
        self.bot.database.set_thread_notification_server(self.ctx.author.id, selected_server_id)
        await self.message.edit(content=f"Your thread notification server has been set to {selected_server.name}.",
                                view=None)
        self.stop()


class FissureSubscriptionView(discord.ui.View):
    def __init__(self, bot, user, subscriptions, embeds):
        super().__init__(timeout=None)
        self.bot = bot
        self.user = user
        self.subscriptions = subscriptions
        self.embeds = embeds
        self.current_page = 0
        self.message = None

        self.prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.blurple)
        self.prev_button.callback = self.previous_page
        self.add_item(self.prev_button)

        self.next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.blurple)
        self.next_button.callback = self.next_page
        self.add_item(self.next_button)

        self.delete_all_button = discord.ui.Button(label="Delete All Subscriptions", style=discord.ButtonStyle.danger)
        self.delete_all_button.callback = self.confirm_delete_all_subscriptions
        self.add_item(self.delete_all_button)

        self.cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.grey)
        self.cancel_button.callback = self.cancel_view
        self.add_item(self.cancel_button)

        self.update_button_states()
        self.update_delete_buttons()

    def update_button_states(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.embeds) - 1

    async def previous_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_button_states()
            await self.update_message(interaction)

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            self.update_button_states()
            await self.update_message(interaction)

    def update_delete_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label.startswith(
                    "Delete") and child.label != "Delete All Subscriptions":
                self.remove_item(child)

        start_index = self.current_page * 5
        end_index = start_index + 5

        for i, subscription in enumerate(self.subscriptions[start_index:end_index], start=start_index + 1):
            button = discord.ui.Button(label=f"Delete {i}", style=discord.ButtonStyle.danger, row=2)
            button.callback = self.create_delete_callback(subscription)
            self.add_item(button)

    async def update_message(self, interaction: discord.Interaction):
        self.update_delete_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def confirm_delete_all_subscriptions(self, interaction: discord.Interaction):
        confirm_view = ConfirmDeleteAllView(self.bot, self.user, self.subscriptions, self)
        await interaction.response.send_message("Are you sure you want to delete all fissure subscriptions?",
                                                view=confirm_view, ephemeral=True)

    async def delete_all_subscriptions(self):
        user_id = self.user.id
        self.bot.database.remove_all_fissure_subscriptions(user_id)
        self.subscriptions.clear()
        await self.message.delete()
        self.stop()

    async def cancel_view(self, interaction: discord.Interaction):
        await interaction.message.delete()
        self.stop()

    def create_delete_callback(self, subscription):
        async def delete_callback(interaction: discord.Interaction):
            user_id = self.user.id
            self.bot.database.remove_fissure_subscription(user_id, **subscription)
            self.subscriptions.remove(subscription)

            if not self.subscriptions:
                await interaction.response.edit_message(content="You have no active fissure subscriptions.", embed=None,
                                                        view=None)
                self.stop()
            else:
                self.embeds = []
                for i in range(0, len(self.subscriptions), 5):
                    embed = discord.Embed(title="Your Fissure Subscriptions", color=discord.Color.blue())
                    for j, sub in enumerate(self.subscriptions[i:i + 5], start=i + 1):
                        fields = [f"{field.replace('_', ' ').capitalize()}: {value}" for field, value in sub.items() if
                                  value]
                        embed.add_field(name=str(j), value="\n".join(fields), inline=True)
                    self.embeds.append(embed)

                self.current_page = min(self.current_page, len(self.embeds) - 1)

                await self.update_message(interaction)

        return delete_callback


class ConfirmDeleteAllView(discord.ui.View):
    def __init__(self, bot, user, subscriptions, parent_view):
        super().__init__(timeout=None)
        self.bot = bot
        self.user = user
        self.subscriptions = subscriptions
        self.parent_view = parent_view

        self.confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.danger)
        self.confirm_button.callback = self.confirm_delete_all
        self.add_item(self.confirm_button)

        self.cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.grey)
        self.cancel_button.callback = self.cancel_delete_all
        self.add_item(self.cancel_button)

    async def confirm_delete_all(self, interaction: discord.Interaction):
        await self.parent_view.delete_all_subscriptions()
        await interaction.response.edit_message(content="All subscriptions have been deleted.", view=None)

    async def cancel_delete_all(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Deletion of all subscriptions has been cancelled.", view=None)


class ButtonView(discord.ui.View):
    def __init__(self, bot, interaction, message_text=None, button_configs=None, fissure_view_message=None):
        super().__init__()
        self.bot = bot
        self.interaction = interaction
        self.button_configs = [] if button_configs is None else button_configs
        self.message_text = "Fissure view created:" if message_text is None else message_text

        self.add_button = discord.ui.Button(label='Add Button', style=discord.ButtonStyle.primary)
        self.add_button.callback = self.add_button_callback
        self.add_item(self.add_button)

        self.edit_buttons = discord.ui.Button(label='Edit Buttons', style=discord.ButtonStyle.secondary)
        self.edit_buttons.callback = self.edit_buttons_callback
        self.add_item(self.edit_buttons)

        self.set_message_text_button = discord.ui.Button(label='Set Message Text', style=discord.ButtonStyle.secondary)
        self.set_message_text_button.callback = self.set_message_text_callback
        self.add_item(self.set_message_text_button)

        self.done_button = discord.ui.Button(label='Done', style=discord.ButtonStyle.success)
        self.done_button.callback = self.done_button_callback
        self.add_item(self.done_button)

        self.content = None
        self.fissure_view_message = fissure_view_message

    async def send_initial_message(self):
        self.get_message_content()
        await self.interaction.response.send_message(content=self.content, view=self, ephemeral=True)

    async def add_button_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ButtonModal(self.bot, interaction, self))

    async def edit_buttons_callback(self, interaction: discord.Interaction):
        select = discord.ui.Select(
            placeholder="Select a button to edit",
            options=[discord.SelectOption(label=config['text'], value=str(i)) for i, config in
                     enumerate(self.button_configs)]
        )
        select.callback = self.edit_button_select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.edit_message(content="Select a button to edit:", view=view)

    async def edit_button_select_callback(self, interaction: discord.Interaction):
        index = int(interaction.data['values'][0])
        button_config = self.button_configs[index]
        await interaction.response.send_modal(ButtonModal(self.bot, interaction, self, button_config, index))

    async def set_message_text_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MessageTextModal(self.bot, interaction, self))

    async def done_button_callback(self, interaction: discord.Interaction):
        if not self.button_configs:
            await interaction.response.edit_message(content="Please add at least one button to the fissure view.",
                                                    view=self)
            return

        view = FissureView(self.bot, self.button_configs)

        if self.fissure_view_message is None:
            message = await interaction.channel.send(content=self.message_text, view=view)

            # Save the data associated with the view to the database
            self.bot.database.save_fissure_view(self.message_text, self.button_configs, interaction.channel.id,
                                                message.id)

            await interaction.response.edit_message(content="Fissure view created successfully.", view=None, embed=None)
        else:
            await self.fissure_view_message.edit(content=self.message_text, view=view)

            await interaction.response.edit_message(content="Fissure view updated successfully.", view=None, embed=None)

            self.bot.database.update_fissure_view(self.message_text, self.button_configs, self.fissure_view_message.id)

        self.stop()

    def get_message_content(self):
        button_list = '\n'.join([self.format_button_config(config) for config in self.button_configs])
        self.content = f"Click the 'Add Button' button to add buttons to the fissure view.\n\nMessage Text: {self.message_text}\n\nCurrent Buttons:\n{button_list}"

    async def update_message(self, interaction: discord.Interaction):
        self.get_message_content()
        await interaction.response.edit_message(content=self.content, view=self)

    def format_button_config(self, config):
        fissure_data = ', '.join([f"{k.capitalize()}: {v}" for k, v in config['fissure_data'].items() if v])
        return f"{config['emoji']} {config['text']} ({fissure_data})"


class MessageTextModal(discord.ui.Modal):
    def __init__(self, bot, interaction, button_view):
        super().__init__(title='Set Message Text')
        self.bot = bot
        self.interaction = interaction
        self.button_view = button_view

        self.message_text_input = discord.ui.TextInput(label='Message Text', placeholder='Enter the message text',
                                                       style=discord.TextStyle.long)
        self.add_item(self.message_text_input)

    async def on_submit(self, interaction: discord.Interaction):
        message_text = self.message_text_input.value
        self.button_view.message_text = message_text
        await self.button_view.update_message(interaction)


class ButtonModal(discord.ui.Modal):
    def __init__(self, bot, interaction, button_view, button_config=None, index=None):
        super().__init__(title='Add/Edit Button')
        self.bot = bot
        self.interaction = interaction
        self.button_view = button_view
        self.fissure_data = button_config['fissure_data'] if button_config else {}
        self.index = index

        self.text_input = discord.ui.TextInput(label='Button Text', placeholder='Enter the text for the button',
                                               default=button_config['text'] if button_config else None)
        self.emoji_input = discord.ui.TextInput(label='Emoji', placeholder='Enter the custom emoji for the button',
                                                required=False,
                                                default=button_config['emoji'] if button_config else None)
        self.add_item(self.text_input)
        self.add_item(self.emoji_input)

    async def on_submit(self, interaction: discord.Interaction):
        emoji_input = self.emoji_input.value.strip() if self.emoji_input.value else ''
        text_input = self.text_input.value

        async def get_emoji(emoji_key):
            if emoji_key in self.bot.emoji_dict:
                return self.bot.emoji_dict[emoji_key]

            guild_emoji = discord.utils.get(interaction.guild.emojis, name=emoji_key)
            if guild_emoji:
                return guild_emoji

            if emoji_key.startswith('<:') and emoji_key.endswith('>'):
                id_part = emoji_key.split(':')[-1][:-1]
                try:
                    potential_id = int(id_part)
                    return self.bot.get_emoji(potential_id)
                except (ValueError, discord.NotFound):
                    return None

            try:
                return self.bot.get_emoji(int(emoji_key))
            except discord.NotFound:
                return None

        if emoji_input:
            emoji = await get_emoji(emoji_input)
            if not emoji:
                await interaction.response.send_message("Invalid emoji. Please enter a valid custom server emoji.",
                                                        ephemeral=True)
                return

            emoji = str(emoji)
        else:
            emoji = None

        try:
            fissure_data_message = self.get_fissure_data_message()
            view = DataView(self.bot, self.interaction, self, emoji, text_input, self.fissure_data, self.index)
            await interaction.response.edit_message(content=fissure_data_message, view=view)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred while updating the message: {str(e)}",
                                                    ephemeral=True)

    def get_fissure_data_message(self):
        content = "Current Fissure Data:\n"
        if self.fissure_data:
            content += '\n'.join([f'{k.capitalize()}: {v}' for k, v in self.fissure_data.items()])
        else:
            content += "No fissure data selected."

        return content


class DataView(discord.ui.View):
    def __init__(self, bot, interaction, button_modal, emoji, text, fissure_data, index=None):
        super().__init__()
        self.bot = bot
        self.interaction = interaction
        self.button_modal = button_modal
        self.emoji = emoji
        self.text = text
        self.fissure_data = fissure_data
        self.index = index

        self.data_select = discord.ui.Select(
            placeholder='Select Fissure Data',
            options=[
                discord.SelectOption(label='Fissure Type', value='fissure_type'),
                discord.SelectOption(label='Era', value='era'),
                discord.SelectOption(label='Node', value='node'),
                discord.SelectOption(label='Mission', value='mission'),
                discord.SelectOption(label='Planet', value='planet'),
                discord.SelectOption(label='Tileset', value='tileset'),
                discord.SelectOption(label='Enemy', value='enemy'),
                discord.SelectOption(label='Tier', value='tier')
            ]
        )
        self.data_select.callback = self.data_select_callback
        self.add_item(self.data_select)

        self.clear_data_button = discord.ui.Button(label='Clear Fissure Data', style=discord.ButtonStyle.danger)
        self.clear_data_button.callback = self.clear_data_callback
        self.add_item(self.clear_data_button)

        self.done_button = discord.ui.Button(label='Done', style=discord.ButtonStyle.success)
        self.done_button.callback = self.done_button_callback
        self.add_item(self.done_button)

    async def data_select_callback(self, interaction: discord.Interaction):
        selected_option = self.data_select.values[0]
        if selected_option in ['fissure_type', 'era', 'tier']:
            await self.show_data_dropdown(interaction, selected_option)
        else:
            filtered_nodes = self.bot.cogs['Fissure'].filter_nodes(interaction, self.fissure_data)
            key_mapping = {
                'mission': 'type'
            }
            node_key = key_mapping.get(selected_option, selected_option)
            valid_choices = {node[node_key] for node in filtered_nodes if node_key in node}
            if len(valid_choices) <= 25:
                await self.show_data_dropdown(interaction, selected_option, valid_choices)
            else:
                await interaction.response.send_modal(DataModal(self.bot, self.interaction, self, selected_option))

    async def show_data_dropdown(self, interaction: discord.Interaction, data_type, valid_choices=None):
        if valid_choices is None:
            if data_type == 'fissure_type':
                valid_choices = ['Normal', 'Steel Path', 'Void Storm']
            elif data_type == 'era':
                valid_choices = ['Lith', 'Meso', 'Neo', 'Axi', 'Requiem', 'Omnia']
            elif data_type == 'tier':
                valid_choices = [
                    discord.SelectOption(label='Tier 1 - Capture/Exterminate', value='1'),
                    discord.SelectOption(label='Tier 2 - + Fast Sabotage/Rescue', value='2'),
                    discord.SelectOption(label='Tier 3 - + Excavation/Disruption', value='3'),
                    discord.SelectOption(label='Tier 4 - + Slow Sabotage/Spy/Hive', value='4'),
                    discord.SelectOption(label='Tier 5 - + Survival/Defense/Mobile Defense/Other', value='5')
                ]

        self.data_dropdown = discord.ui.Select(
            placeholder=f'Select {data_type.capitalize()}',
            options=valid_choices if data_type == 'tier' else [discord.SelectOption(label=choice) for choice in
                                                               valid_choices]
        )
        self.data_dropdown.callback = self.data_dropdown_callback
        self.add_item(self.data_dropdown)

        fissure_data_message = self.button_modal.get_fissure_data_message()
        await interaction.response.edit_message(content=fissure_data_message, view=self)

    async def data_dropdown_callback(self, interaction: discord.Interaction):
        value = self.data_dropdown.values[0]

        if self.data_dropdown.placeholder.startswith('Select Tier'):
            value = int(value)

        data_type = self.data_dropdown.placeholder.split(' ')[1].lower()
        self.fissure_data[data_type] = value

        fissure_data_message = self.button_modal.get_fissure_data_message()
        self.remove_item(self.data_dropdown)
        await interaction.response.edit_message(content=fissure_data_message, view=self)

    async def clear_data_callback(self, interaction: discord.Interaction):
        self.fissure_data.clear()
        fissure_data_message = self.button_modal.get_fissure_data_message()
        await interaction.response.edit_message(content=fissure_data_message, view=self)

    async def done_button_callback(self, interaction: discord.Interaction):
        valid_fissure_data = {k: v for k, v in self.fissure_data.items() if v is not None}
        if self.index is not None:
            self.button_modal.button_view.button_configs[self.index] = {
                'emoji': self.emoji,
                'text': self.text,
                'fissure_data': valid_fissure_data
            }
        else:
            self.button_modal.button_view.button_configs.append(
                {'emoji': self.emoji, 'text': self.text, 'fissure_data': valid_fissure_data})
        await self.button_modal.button_view.update_message(interaction)
        self.stop()


class DataModal(discord.ui.Modal):
    def __init__(self, bot, interaction, data_view, data_type):
        super().__init__(title=f'Select {data_type.capitalize()}')
        self.bot = bot
        self.interaction = interaction
        self.data_view = data_view
        self.data_type = data_type

        self.data_input = discord.ui.TextInput(label=data_type.capitalize(), placeholder=f'Enter the {data_type}')
        self.add_item(self.data_input)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.data_input.value

        if self.data_type in ['node', 'type', 'planet', 'tileset', 'enemy']:
            filtered_nodes = self.bot.cogs['Fissure'].filter_nodes(interaction,
                                                                   self.data_view.button_modal.fissure_data)
            key_mapping = {
                'mission': 'type'
            }
            node_key = key_mapping.get(self.data_type, self.data_type)
            valid_choices = {node[node_key] for node in filtered_nodes if node_key in node}
            if value not in valid_choices:
                await interaction.response.send_message(f"Invalid {self.data_type} entered. Please try again.",
                                                        ephemeral=True)
                self.data_view.button_modal.fissure_data[self.data_type] = None
                await self.data_view.interaction.edit_original_response(view=self.data_view)
                return
        elif self.data_type == 'tier':
            try:
                value = int(value)
                if value < 1 or value > 5:
                    await interaction.response.send_message("Tier must be between 1 and 5. Please try again.",
                                                            ephemeral=True)
                    self.data_view.button_modal.fissure_data[self.data_type] = None
                    await self.data_view.interaction.edit_original_response(view=self.data_view)
                    return
            except ValueError:
                await interaction.response.send_message("Invalid tier entered. Please enter a number between 1 and 5.",
                                                        ephemeral=True)
                self.data_view.button_modal.fissure_data[self.data_type] = None
                await self.data_view.interaction.edit_original_response(view=self.data_view)
                return

        self.data_view.button_modal.fissure_data[self.data_type] = value

        content = '\n'.join(
            [f'{k.capitalize()}: {v}' for k, v in self.data_view.button_modal.fissure_data.items() if v is not None])
        await interaction.response.edit_message(content=content, view=self.data_view)


class FissureView(discord.ui.View):
    def __init__(self, bot, button_configs):
        super().__init__(timeout=None)
        self.bot = bot

        used_custom_ids = []

        for config in button_configs[:15]:
            emoji = config['emoji']
            text = config['text']
            fissure_data = config['fissure_data']

            custom_id = f"fissure_button_{text.lower()}"
            if custom_id in used_custom_ids:
                custom_id += custom_id + str(uuid.uuid4())

            used_custom_ids.append(custom_id)
            button = discord.ui.Button(
                label=text,
                emoji=emoji if emoji else None,
                style=discord.ButtonStyle.primary,
                custom_id=custom_id
            )
            button.callback = self.create_button_callback(text, fissure_data)
            self.add_item(button)

    def create_button_callback(self, text, fissure_data):
        async def button_callback(interaction: discord.Interaction):
            user_id = interaction.user.id

            # Check if the user exists in the users table
            user_exists = self.bot.database.user_exists(user_id)

            if not user_exists:
                # Create a new entry for the user in the users table
                self.bot.database.create_user(user_id)

            # Check if any subscription fields are provided
            if not any(fissure_data.values()):
                await interaction.response.send_message("Cannot add a blank subscription.", ephemeral=True)
                return

            try:
                self.bot.database.add_fissure_subscription(user_id, **fissure_data)
                await interaction.response.send_message(f"You have subscribed to {text} fissures.", ephemeral=True)
            except ValueError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
            except IntegrityError:
                await interaction.response.send_message("You're already subscribed.", ephemeral=True)

        return button_callback


class Fissure(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.image_dict = {
            'Lith': 'https://cdn.discordapp.com/emojis/780453137588551720.webp',
            'Meso': 'https://cdn.discordapp.com/emojis/780453137739022357.webp',
            'Neo': 'https://cdn.discordapp.com/emojis/780453137675714630.webp',
            'Axi': 'https://cdn.discordapp.com/emojis/780453137291018271.webp',
            'Requiem': 'https://cdn.discordapp.com/emojis/1043330972642447500.webp',
            'Omnia': 'https://static.wikia.nocookie.net/warframe/images/5/57/VoidTearIcon_b.png',
            FissureEngine.FISSURE_TYPE_VOID_STORMS: "https://static.wikia.nocookie.net/warframe/images/1/1c/CorruptedHolokey.png",
            FissureEngine.FISSURE_TYPE_STEEL_PATH: "https://static.wikia.nocookie.net/warframe/images/1/10/SteelEssence.png"
        }
        self.color_dict = {
            'Lith': discord.Color.green(),
            'Meso': discord.Color.blue(),
            'Neo': discord.Color.red(),
            'Axi': discord.Color.gold(),
            'Requiem': discord.Color.purple(),
            'Omnia': discord.Color.dark_gold()
        }

    @tasks.loop(seconds=10)
    async def update_fissure_list(self):
        new_fissures, changed_fissure_types = await self.bot.fissure_engine.build_fissure_list()

        if new_fissures:
            self.bot.loop.create_task(self.send_new_fissures(new_fissures))

    async def send_new_fissures(self, new_fissures):
        new_fissures = self.sort_new_fissures(new_fissures)

        fissure_log_dict = self.bot.database.get_fissure_log_channels()

        for fissure_type, server_dict in fissure_log_dict.items():
            fissures_of_type = [fissure for fissure in new_fissures if fissure.fissure_type == fissure_type]
            embeds_of_type = [self.get_fissure_info_embed(fissure) for fissure in fissures_of_type]

            for server_id, channel_ids in server_dict.items():
                server = self.bot.get_guild(server_id)
                if server is None:
                    continue

                channels = list(filter(None, map(server.get_channel, channel_ids)))
                for channel in channels:
                    for fissure, embed in zip(fissures_of_type, embeds_of_type):
                        log_message = await channel.send(embed=embed)
                        await self.send_thread_notifications(fissure, log_message)

        await self.send_fissure_subscription_dms(new_fissures)

    async def get_user_status(self, user_id):
        user = self.bot.get_user(user_id)
        if user is None:
            return 'Offline'

        member = None
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if member:
                break

        if member is None:
            return 'Offline'

        return str(member.status)

    async def send_thread_notifications(self, fissure, log_message: discord.Message):
        subscriptions = self.bot.database.get_all_fissure_subscriptions('Thread')
        thread_users = [sub['user_id'] for sub in subscriptions if self.match_subscription(sub, fissure)]

        # Remove duplicates
        thread_users = list(set(thread_users))

        if not thread_users:
            return

        thread_user_ids = []
        for user_id in thread_users:
            thread_server_id = self.bot.database.get_thread_notification_server(user_id)

            member_status = await self.get_user_status(user_id)

            if ((thread_server_id is None or thread_server_id == log_message.guild.id) and
                    self.bot.database.get_fissure_notification_status(user_id).get(member_status, True)):
                thread_user_ids.append(user_id)

        if not thread_user_ids:
            return

        thread = await log_message.create_thread(name=f"{log_message.embeds[0].description.split('\n')[0]}")

        thread_mentions = [f"<@{user_id}>" for user_id in thread_user_ids]
        mention_chunks = self.split_mentions(" ".join(thread_mentions))

        for chunk in mention_chunks:
            await thread.send(chunk)

        # Schedule a job to lock and archive the thread when the fissure expires
        self.bot.scheduler.add_job(
            self.lock_and_archive_thread,
            'date',
            run_date=fissure.expiry,
            args=[thread]
        )

    async def send_fissure_subscription_dms(self, new_fissures):
        subscriptions = self.bot.database.get_all_fissure_subscriptions('DM')
        user_embeds = await self.get_user_embeds(new_fissures, subscriptions)

        user_send_tasks = []
        for user_id, embeds in user_embeds.items():
            user = self.bot.get_user(user_id)
            if user:
                member_status = await self.get_user_status(user_id)

                if self.bot.database.get_fissure_notification_status(user_id).get(member_status, True):
                    for embed in embeds:
                        user_send_tasks.append(self.send_embeds_to_user(user, [embed]))

        await asyncio.gather(*user_send_tasks)

    async def send_embeds_to_user(self, user, embeds):
        try:
            await user.send(embeds=embeds)
        except discord.Forbidden:
            pass

    async def get_user_embeds(self, new_fissures, subscriptions):
        user_embeds = defaultdict(list)
        user_fissure_sent = defaultdict(set)

        for fissure in new_fissures:
            matching_subscriptions = [sub for sub in subscriptions if self.match_subscription(sub, fissure)]

            for subscription in matching_subscriptions:
                user_id = subscription["user_id"]

                if fissure in user_fissure_sent[user_id]:
                    continue

                embed = self.get_fissure_info_embed(fissure)
                user_embeds[user_id].append(embed)
                user_fissure_sent[user_id].add(fissure)

        return user_embeds

    async def lock_and_archive_thread(self, thread: discord.Thread):
        # Lock and archive the thread
        await thread.edit(locked=True, archived=True)

    def split_mentions(self, mentions: str, max_length: int = 2000) -> List[str]:
        mentions_list = mentions.split()
        chunks = []
        current_chunk = []

        for mention in mentions_list:
            if len(' '.join(current_chunk)) + len(mention) + 1 > max_length:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
            current_chunk.append(mention)

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def get_fissure_type_identifier(self, fissure_type):
        if fissure_type != FissureEngine.FISSURE_TYPE_NORMAL:
            short_identifier = ''.join(word[0].upper() for word in fissure_type.split())
            return f"{short_identifier} "
        return ""

    def sort_new_fissures(self, new_fissures):
        fissure_type_order = [FissureEngine.FISSURE_TYPE_NORMAL, FissureEngine.FISSURE_TYPE_STEEL_PATH,
                              FissureEngine.FISSURE_TYPE_VOID_STORMS]
        era_order = [FissureEngine.ERA_LITH, FissureEngine.ERA_MESO, FissureEngine.ERA_NEO, FissureEngine.ERA_AXI,
                     FissureEngine.ERA_REQUIEM, FissureEngine.ERA_OMNIA]

        def sort_key(fissure):
            fissure_type_index = fissure_type_order.index(fissure.fissure_type)
            era_index = era_order.index(fissure.era)
            return fissure_type_index, era_index

        return sorted(new_fissures, key=sort_key)

    def match_subscription(self, subscription: dict, fissure: fissure_engine.Fissure) -> bool:
        for key, value in subscription.items():
            if key == "user_id":
                continue
            if value is None:
                continue
            if key == "mission" and value.lower() in fissure.mission.lower():
                return True
            if key == "max_tier":
                if fissure.tier > value:
                    return False
            elif getattr(fissure, key) != value:
                return False
        return True

    def get_fissure_info_embed(self, fissure: fissure_engine.Fissure):
        embed = discord.Embed(colour=self.color_dict[fissure.era], timestamp=fissure.activation)

        embed.set_author(name=f'New {fissure.era} Fissure ({fissure.fissure_type})',
                         icon_url=self.image_dict[fissure.era])

        hours, remainder = divmod(fissure.duration.total_seconds(), 3600)
        minutes = remainder // 60
        duration_str = f"{int(hours)} hour{'s' if hours != 1 else ''} {int(minutes)} minute{'s' if minutes != 1 else ''}"

        embed.description = f"{fissure.era} {fissure.mission}: {fissure.node} ({duration_str})\n" \
                            f"{self.bot.fissure_engine.format_time_remaining(fissure.expiry, FissureEngine.DISPLAY_TYPE_DISCORD)}"

        embed.add_field(name='Enemy', value=fissure.enemy, inline=True)
        embed.add_field(name='Tileset', value=fissure.tileset, inline=True)
        embed.add_field(name='Planet', value=fissure.planet, inline=True)

        if fissure.fissure_type in self.image_dict:
            embed.set_thumbnail(url=self.image_dict[fissure.fissure_type])

        return embed

    def list_to_field_string(self, field_list: List[str], max_length: int = 40):
        """
        Converts list of strings to a string that can be used as a field value in an embed.
        Any string that is longer than max_length will be cut off and appended with '..'.
        """
        field_string = ""
        for field in field_list:
            if len(field) > max_length:
                field_string += field[:max_length - 2] + "..\n"
            else:
                field_string += field + "\n"
        return field_string

    async def get_fissure_list_embed(self, fissure_types: Union[List, str] = 'Normal',
                                     display_type: str = FissureEngine.DISPLAY_TYPE_DISCORD,
                                     era_list: list = None,
                                     max_tier: int = 5):
        if isinstance(fissure_types, str):
            fissure_types = [fissure_types]

        if era_list is None:
            era_list = self.bot.fissure_engine.get_era_list(fissure_types)

        embeds = []

        fissures = self.bot.fissure_engine.get_fissures(fissure_type=fissure_types,
                                                        era=era_list,
                                                        tier=list(range(1, max_tier + 1)))

        era_resets = self.bot.fissure_engine.get_resets(fissure_type=fissure_types,
                                                        display_type=display_type,
                                                        emoji_dict=self.bot.emoji_dict,
                                                        era_list=era_list)

        embed = discord.Embed(colour=discord.Colour.dark_gold())

        fields = [('Era', '{era}'),
                  ('Mission', '{mission} - {node} ({planet})'),
                  ('Ends', '{expiry}')]

        field_values = self.bot.fissure_engine.get_fields(fissures, fields, display_type, self.bot.emoji_dict)

        if not fissures:
            embed.description = "There are no valid fissures available right now."
        else:
            # Determine the number of sublists (one per fissure type) in field_values
            num_fissure_types = max(len(values) for values in field_values.values())

            # Create an embed for each fissure type
            for fissure_type_index in range(num_fissure_types):
                for field_name, _ in fields:
                    max_length = 40 if field_name == 'Mission' else 1024

                    # Access the appropriate sublist for the current fissure type
                    # and handle cases where some fields might have fewer entries
                    value_list = field_values.get(field_name, [])
                    value = value_list[fissure_type_index] if fissure_type_index < len(value_list) else "N/A"

                    # Only add field names for the first fissure type
                    field_name = field_name if fissure_type_index == 0 else ""

                    embed.add_field(name=field_name, value=self.list_to_field_string(value, max_length), inline=True)

        for i, (fissure_type, resets) in enumerate(era_resets.items()):
            fissure_type_identifier = fissure_engine.get_fissure_type_identifier(fissure_type, self.bot.emoji_dict)
            resets = [f"{fissure_type_identifier} {item}" for item in resets]

            embed.add_field(name='', value='\n'.join(resets), inline=True if i < 2 else False)

        embeds.append(embed)

        return embeds

    @commands.hybrid_command(name='set_thread_notification_server', aliases=['stns'])
    async def set_thread_notification_server(self, ctx, server: discord.Guild = None):
        """Set the server where you want to receive thread notifications."""
        user_id = ctx.author.id

        if server is None:
            user_servers = [guild for guild in self.bot.guilds if guild.get_member(user_id)]
            message = await ctx.send("Please select the server where you want to receive thread notifications:",
                                     ephemeral=True)
            view = ThreadNotificationServerSelectView(self.bot, ctx, user_servers, message)
            await message.edit(view=view)
        else:
            self.bot.database.set_thread_notification_server(user_id, server.id)
            await ctx.send(f"Your thread notification server has been set to {server.name}.", ephemeral=True)

    @commands.command(name='sync_rolesubscriptions', aliases=['syncrs'])
    @commands.has_permissions(administrator=True)
    async def sync_rolesubscriptions(self, ctx):
        for role in ctx.guild.roles:
            if role.name.startswith(("Lith", "Meso", "Neo", "Axi")) and len(role.members) > 2:
                era = role.name.split()[0]
                mission_or_node = ' '.join(role.name.split()[1:])

                if mission_or_node in ["Capture", "Rescue", "Exterminate", "Sabotage", "Disruption"]:
                    mission = mission_or_node
                    node = None
                else:
                    mission = None
                    node = mission_or_node

                for member in role.members:
                    user_id = member.id

                    # Check if the user exists in the users table
                    user_exists = self.bot.database.user_exists(user_id)

                    if not user_exists:
                        # Create a new entry for the user in the users table
                        self.bot.database.create_user(user_id)

                    # Set the user's notification type to "Thread"
                    self.bot.database.set_fissure_notification_type(user_id, "Thread")

                    # Check if the user already has the subscription
                    existing_subscriptions = self.bot.database.get_fissure_subscriptions(user_id)
                    new_subscription = {
                        "fissure_type": "Normal",
                        "era": era,
                        "node": node,
                        "mission": mission,
                        "planet": None,
                        "tileset": None,
                        "enemy": None,
                        "max_tier": None
                    }

                    if new_subscription not in existing_subscriptions:
                        # Add the equivalent subscription
                        self.bot.database.add_fissure_subscription(user_id, fissure_type="Normal", era=era, node=node,
                                                                   mission=mission)
                        self.bot.logger.info(
                            f"Added subscription for user {member.id}: Era={era}, Mission={mission}, Node={node}")
                    else:
                        self.bot.logger.info(
                            f"User {member.id} already subscribed: Era={era}, Mission={mission}, Node={node}")

        await ctx.send("Role subscriptions synced successfully.")

    @commands.hybrid_command(name='mute_fissure_notifications', aliases=['mute', 'unmute'])
    @app_commands.describe(
        enabled='Whether to enable or disable fissure notifications. If not provided, the current setting will be toggled.')
    async def fissure_notifications(self, ctx, enabled: bool = None):
        """Enable, disable, or toggle fissure notifications."""
        user_id = ctx.author.id

        # Check if the user exists in the users table
        user_exists = self.bot.database.user_exists(user_id)

        if not user_exists:
            # Create a new entry for the user in the users table
            self.bot.database.create_user(user_id)

        if enabled is None:
            # If no argument is provided, toggle the current setting
            current_setting = self.bot.database.get_fissure_notifications_enabled(user_id)
            enabled = not current_setting

        self.bot.database.set_fissure_notifications_enabled(user_id, enabled)

        status = "enabled" if enabled else "disabled"
        await self.bot.send_message(ctx, f"Fissure notifications have been {status}.", ephemeral=True)

    @commands.hybrid_command(name='set_fissure_defaults', aliases=['sfd', 'setfissuredefaults'])
    @app_commands.describe(show_normal='Whether to show normal fissures by default.',
                           show_steel_path='Whether to show Steel Path fissures by default.',
                           show_void_storms='Whether to show Void Storm fissures by default.',
                           max_tier='The maximum tier of fissures to show by default.',
                           show_lith='Whether to show Lith fissures by default.',
                           show_meso='Whether to show Meso fissures by default.',
                           show_neo='Whether to show Neo fissures by default.',
                           show_axi='Whether to show Axi fissures by default.',
                           show_requiem='Whether to show Requiem fissures by default.',
                           show_omnia='Whether to show Omnia fissures by default.')
    @app_commands.choices(max_tier=[
        Choice(name='Tier 1 - Capture/Exterminate', value=1),
        Choice(name='Tier 2 - + Fast Sabotage/Rescue', value=2),
        Choice(name='Tier 3 - + Excavation/Disruption', value=3),
        Choice(name='Tier 4 - + Slow Sabotage/Spy/Hive', value=4),
        Choice(name='Tier 5 - + Survival/Defense/Mobile Defense/Other', value=5),
    ])
    async def set_fissure_defaults(self, ctx,
                                   show_normal: bool = None,
                                   show_steel_path: bool = None,
                                   show_void_storms: bool = None,
                                   max_tier: int = None,
                                   show_lith: bool = None,
                                   show_meso: bool = None,
                                   show_neo: bool = None,
                                   show_axi: bool = None,
                                   show_requiem: bool = None,
                                   show_omnia: bool = None):
        """Set your default preferences for the fissure list command."""
        user_id = ctx.author.id

        # Check if the user exists in the users table
        user_exists = self.bot.database.user_exists(user_id)

        if not user_exists:
            # Create a new entry for the user in the users table
            self.bot.database.create_user(user_id)

        # Create a dictionary of the provided parameters
        update_params = {
            'show_normal': show_normal,
            'show_steel_path': show_steel_path,
            'show_void_storms': show_void_storms,
            'max_tier': max_tier,
            'show_lith': show_lith,
            'show_meso': show_meso,
            'show_neo': show_neo,
            'show_axi': show_axi,
            'show_requiem': show_requiem,
            'show_omnia': show_omnia
        }

        # Filter out the parameters that were not provided by the user
        update_params = {k: v for k, v in update_params.items() if v is not None}

        self.bot.database.set_fissure_list_defaults(user_id, **update_params)

        await self.bot.send_message(ctx, "Your fissure list defaults have been updated.",
                                    ephemeral=True)

    @commands.hybrid_command(name='add_fissure_subscription', aliases=['afs', 'addfissuresubscription'])
    @app_commands.describe(
        fissure_type='The type of fissure to subscribe to.',
        era='The era of the fissure to subscribe to.',
        node='The node of the fissure to subscribe to.',
        mission='The mission type of the fissure to subscribe to.',
        planet='The planet of the fissure to subscribe to.',
        tileset='The tileset of the fissure to subscribe to.',
        enemy='The enemy faction of the fissure to subscribe to.',
        max_tier='The maximum tier of the fissure you want to receive notifications for.'
    )
    @app_commands.choices(max_tier=[
        Choice(name='Tier 1 - Capture/Exterminate', value=1),
        Choice(name='Tier 2 - + Fast Sabotage/Rescue', value=2),
        Choice(name='Tier 3 - + Excavation/Disruption', value=3),
        Choice(name='Tier 4 - + Slow Sabotage/Spy/Hive', value=4),
        Choice(name='Tier 5 - + Survival/Defense/Mobile Defense/Other', value=5),
    ],
        fissure_type=[Choice(name='Normal', value=FissureEngine.FISSURE_TYPE_NORMAL),
                      Choice(name='Steel Path', value=FissureEngine.FISSURE_TYPE_STEEL_PATH),
                      Choice(name='Void Storm', value=FissureEngine.FISSURE_TYPE_VOID_STORMS)],
        era=[Choice(name='Lith', value=FissureEngine.ERA_LITH),
             Choice(name='Meso', value=FissureEngine.ERA_MESO),
             Choice(name='Neo', value=FissureEngine.ERA_NEO),
             Choice(name='Axi', value=FissureEngine.ERA_AXI),
             Choice(name='Requiem', value=FissureEngine.ERA_REQUIEM),
             Choice(name='Omnia', value=FissureEngine.ERA_OMNIA)]
    )
    async def add_fissure_subscription(self, ctx,
                                       fissure_type: str = commands.parameter(default=None,
                                                                              description="The type of fissure to subscribe to."),
                                       era: str = commands.parameter(default=None,
                                                                     description="The era of the fissure to subscribe to."),
                                       node: str = commands.parameter(default=None,
                                                                      description="The node of the fissure to subscribe to."),
                                       mission: str = commands.parameter(default=None,
                                                                         description="The mission type of the fissure to subscribe to."),
                                       planet: str = commands.parameter(default=None,
                                                                        description="The planet of the fissure to subscribe to."),
                                       tileset: str = commands.parameter(default=None,
                                                                         description="The tileset of the fissure to subscribe to."),
                                       enemy: str = commands.parameter(default=None,
                                                                       description="The enemy faction of the fissure to subscribe to."),
                                       max_tier: int = commands.parameter(default=None,
                                                                          description="The tier of the fissure to subscribe to.")):
        """Add a new fissure subscription."""
        user_id = ctx.author.id

        # Check if the user exists in the users table
        user_exists = self.bot.database.user_exists(user_id)

        if not user_exists:
            # Create a new entry for the user in the users table
            user_id = self.bot.database.create_user(user_id)

        # Check if any subscription fields are provided
        if not any([fissure_type, era, node, mission, planet, tileset, enemy, max_tier]):
            await self.bot.send_message(ctx, "Please provide at least one subscription field.", ephemeral=True)
            return

        try:
            self.bot.database.add_fissure_subscription(user_id, fissure_type, era, node, mission, planet, tileset,
                                                       enemy,
                                                       max_tier)
            await self.bot.send_message(ctx, "Your fissure subscription has been added.", ephemeral=True)
        except ValueError as e:
            await self.bot.send_message(ctx, str(e), ephemeral=True)
        except IntegrityError:
            await self.bot.send_message(ctx, "This subscription already exists.", ephemeral=True)

    def filter_nodes(self, interaction: discord.Interaction, selected_values: dict = None) -> List[dict]:
        filter_rules = {
            'era': [
                {
                    'field': 'planet',
                    'type': 'whitelist',
                    'values': ['Venus', 'Earth', 'Mars'],
                    'condition': FissureEngine.ERA_LITH,
                    'exclusive': True
                },
                {
                    'field': 'planet',
                    'type': 'whitelist',
                    'values': ['Ceres', 'Jupiter', 'Phobos', 'Saturn'],
                    'condition': FissureEngine.ERA_MESO,
                    'exclusive': True
                },
                {
                    'field': 'planet',
                    'type': 'whitelist',
                    'values': ['Neptune', 'Europa', 'Uranus', 'Void'],
                    'condition': FissureEngine.ERA_NEO,
                    'exclusive': False
                },
                {
                    'field': 'planet',
                    'type': 'whitelist',
                    'values': ['Pluto', 'Sedna', 'Eris', 'Void'],
                    'condition': FissureEngine.ERA_AXI,
                    'exclusive': False
                },
                {
                    'field': 'planet',
                    'type': 'whitelist',
                    'values': ['Kuva Fortress'],
                    'condition': FissureEngine.ERA_REQUIEM,
                    'exclusive': True
                },
                {
                    'field': 'planet',
                    'type': 'whitelist',
                    'values': ['Lua', 'Zariman Ten Zero', "Albrecht's Laboratories"],
                    'condition': FissureEngine.ERA_OMNIA,
                    'exclusive': True
                }
            ],
            'fissure_type': [
                {
                    'field': 'planet',
                    'type': 'whitelist',
                    'values': ['Saturn Proxima', 'Earth Proxima', 'Venus Proxima', 'Neptune Proxima', 'Pluto Proxima',
                               'Veil Proxima'],
                    'condition': FissureEngine.FISSURE_TYPE_VOID_STORMS,
                    'exclusive': True
                }
            ]
        }

        if selected_values is None:
            selected_values = {
                attr: getattr(interaction.namespace, attr)
                for attr in interaction.namespace.__dict__
                if getattr(interaction.namespace, attr)
            }
        else:
            # Map the keys from selected_values to match the keys in sol_nodes
            key_mapping = {
                'mission': 'type'
            }
            selected_values = {
                key_mapping.get(key, key): value
                for key, value in selected_values.items()
            }

        blacklisted_nodes = {'type': ['Relay', 'Ancient Retribution', 'Salvage', 'Arena', 'Conclave', 'Hijack',
                                      'Assassination', 'Pursuit (Archwing)', 'Mobile Defense (Archwing)',
                                      'Sabotage (Archwing)', 'Orphix', 'Rush (Archwing)', 'Exterminate (Archwing)',
                                      'Interception (Archwing)', 'Assassinate', 'Void Armageddon', 'Defection',
                                      'Free Roam'],
                             'enemy': ['Tenno'],
                             'planet': ['Mercury']}

        filtered_nodes = sol_nodes.values()

        # Apply blacklist filter
        for attr, values in blacklisted_nodes.items():
            filtered_nodes = [node for node in filtered_nodes if attr not in node or node[attr] not in values]

        for filter_key, filter_rules_list in filter_rules.items():
            filter_value = selected_values.get(filter_key)
            for filter_rule in filter_rules_list:
                if filter_rule['exclusive']:
                    if filter_value == filter_rule['condition']:
                        filtered_nodes = [node for node in filtered_nodes if
                                          node.get(filter_rule['field']) in filter_rule['values']]
                    elif filter_value is not None:
                        filtered_nodes = [node for node in filtered_nodes if
                                          node.get(filter_rule['field']) not in filter_rule['values']]
                else:
                    if filter_value == filter_rule['condition']:
                        field = filter_rule['field']
                        filter_type = filter_rule['type']
                        values = filter_rule['values']

                        if filter_type == 'whitelist':
                            filtered_nodes = [node for node in filtered_nodes if
                                              field in node and node[field] in values]
                        elif filter_type == 'blacklist':
                            filtered_nodes = [node for node in filtered_nodes if
                                              field not in node or node[field] not in values]

        filtered_nodes = [
            node for node in filtered_nodes
            if all(
                attr in node and node[attr].lower().startswith(value.lower()) for attr, value in selected_values.items()
                if attr in node)
        ]

        return filtered_nodes

    def get_choices(self, nodes: List[dict], current: str, key: str) -> List[Choice[str]]:
        choices = {node[key] for node in nodes if key in node} - {''}

        return [Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()][:10]

    @add_fissure_subscription.autocomplete('node')
    async def node_autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice[str]]:
        filtered_nodes = self.filter_nodes(interaction)
        return self.get_choices(filtered_nodes, current, 'node')

    @add_fissure_subscription.autocomplete('mission')
    async def mission_autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice[str]]:
        filtered_nodes = self.filter_nodes(interaction)
        return self.get_choices(filtered_nodes, current, 'type')

    @add_fissure_subscription.autocomplete('planet')
    async def planet_autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice[str]]:
        filtered_nodes = self.filter_nodes(interaction)
        return self.get_choices(filtered_nodes, current, 'planet')

    @add_fissure_subscription.autocomplete('tileset')
    async def tileset_autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice[str]]:
        filtered_nodes = self.filter_nodes(interaction)
        return self.get_choices(filtered_nodes, current, 'tileset')

    @add_fissure_subscription.autocomplete('enemy')
    async def enemy_autocomplete(self, interaction: discord.Interaction, current: str) -> List[Choice[str]]:
        filtered_nodes = self.filter_nodes(interaction)
        return self.get_choices(filtered_nodes, current, 'enemy')

    @commands.hybrid_command(name='remove_fissure_subscription', aliases=['rfs', 'removefissuresubscription'])
    @app_commands.describe(
        fissure_type='The type of fissure to unsubscribe from.',
        era='The era of the fissure to unsubscribe from.',
        node='The node of the fissure to unsubscribe from.',
        mission='The mission type of the fissure to unsubscribe from.',
        planet='The planet of the fissure to unsubscribe from.',
        tileset='The tileset of the fissure to unsubscribe from.',
        enemy='The enemy faction of the fissure to unsubscribe from.',
        max_tier='The tier of the fissure to unsubscribe from.'
    )
    async def remove_fissure_subscription(self, ctx,
                                          fissure_type: str = None,
                                          era: str = None,
                                          node: str = None,
                                          mission: str = None,
                                          planet: str = None,
                                          tileset: str = None,
                                          enemy: str = None,
                                          max_tier: int = None):
        """Remove a fissure subscription."""
        user_id = ctx.author.id

        # Check if the user exists in the users table
        user_exists = self.bot.database.user_exists(user_id)

        if not user_exists:
            await self.bot.send_message(ctx, "You have no subscriptions to remove.", ephemeral=True)
            return

        self.bot.database.remove_fissure_subscription(user_id, fissure_type, era, node, mission, planet, tileset, enemy,
                                                      max_tier)

        await self.bot.send_message(ctx, "Your fissure subscription has been removed.", ephemeral=True)

    @commands.hybrid_command(name='list_fissure_subscriptions', aliases=['lfs', 'listfissuresubscriptions'])
    async def list_fissure_subscriptions(self, ctx):
        """List your current fissure subscriptions."""
        user_id = ctx.author.id

        subscriptions = self.bot.database.get_fissure_subscriptions(user_id)

        if not subscriptions:
            await self.bot.send_message(ctx, "You have no active fissure subscriptions.", ephemeral=True)
            return

        embeds = []
        for i in range(0, len(subscriptions), 5):
            embed = discord.Embed(title="Your Fissure Subscriptions", color=discord.Color.blue())
            for j, subscription in enumerate(subscriptions[i:i + 5], start=i + 1):
                fields = []
                for field, value in subscription.items():
                    if value:
                        field = field.replace("_", " ").capitalize()
                        fields.append(f"{field}: {value}")
                subscription_str = "\n".join(fields)
                embed.add_field(name=f"{j}", value=subscription_str, inline=True)
            embeds.append(embed)

        view = FissureSubscriptionView(self.bot, ctx.author, subscriptions, embeds)
        message = await ctx.send(embed=embeds[0], view=view, ephemeral=True)
        view.message = message

    @app_commands.command(name='fissure_notifications_status',
                          description='Set fissure notification options based on your current Discord status.')
    async def fissure_notifications_status(self, interaction: discord.Interaction):
        """Set fissure notification options based on your current Discord status."""
        user_id = interaction.user.id

        # Check if the user exists in the users table
        user_exists = self.bot.database.user_exists(user_id)

        if not user_exists:
            # Create a new entry for the user in the users table
            self.bot.database.create_user(user_id)

        status_settings = self.bot.database.get_fissure_notification_status(user_id)
        view = StatusNotificationView(self.bot, user_id, status_settings)
        await interaction.response.send_message("Select the Discord statuses for which you want to receive fissure notifications:",
                                                view=view, ephemeral=True)

    @commands.hybrid_command(name='fissure_log_channel', aliases=['flc', 'flogc', 'flogchannel', 'fissurelogchannel'],
                             brief='Set the channel for the fissure log.')
    @commands.has_permissions(manage_channels=True)
    @app_commands.describe(fissure_type='The type of fissure to log.',
                           channel='The channel to log the fissures in.')
    @app_commands.choices(fissure_type=[Choice(name='Normal', value='normal'),
                                        Choice(name='Steel Path', value='sp'),
                                        Choice(name='Void Storm', value='vs')])
    async def fissure_log_channel(self, ctx,
                                  fissure_type: str = commands.parameter(
                                      default='normal',
                                      description="The type of fissure to log."),
                                  channel: discord.TextChannel = commands.parameter(
                                      default=lambda ctx: ctx.channel,
                                      displayed_default='current channel',
                                      description="The channel to log the fissures in.")):
        """
        If no channel is provided, the current channel is used.

        If you wish to set a log channel and are not using the slash command,
        ensure that you also provide a fissure type before the channel.

        You must have the `manage_channels` permission to use this command.

        By default, only normal fissures are logged. To log other fissure types, provide the fissure type as the
        first argument. Valid types are `normal`, `sp`, and `vs`.

        You can log multiple fissure types in the same channel by repeating the command with different types.
        """
        if channel is None:
            channel = ctx.channel

        if fissure_type.lower() not in self.bot.fissure_engine.ALIASES:
            await self.bot.send_message(ctx, f'Invalid fissure type: {fissure_type}', ephemeral=True)
            return

        fissure_type = self.bot.fissure_engine.ALIASES[fissure_type.lower()]

        try:
            self.bot.database.set_fissure_log_channel(channel.guild.id, channel.id, fissure_type)
        except IntegrityError:
            self.bot.database.unset_fissure_log_channel(channel.guild.id, channel.id, fissure_type)
            await self.bot.send_message(ctx,
                                        f'You will no longer receive {fissure_type} fissure logs in {channel.mention}',
                                        ephemeral=True)
            return

        await self.bot.send_message(ctx, f'New {fissure_type} fissures will now be logged in {channel.mention}',
                                    ephemeral=True)

    def get_era_list_from_config(self, channel_config: dict) -> List[str]:
        era_mapping = {
            "show_lith": FissureEngine.ERA_LITH,
            "show_meso": FissureEngine.ERA_MESO,
            "show_neo": FissureEngine.ERA_NEO,
            "show_axi": FissureEngine.ERA_AXI,
            "show_requiem": FissureEngine.ERA_REQUIEM,
            "show_omnia": FissureEngine.ERA_OMNIA
        }
        return [era for era_name, era in era_mapping.items() if channel_config.get(era_name, False)]

    @commands.hybrid_command(name='fissures', aliases=['fissure', 'fiss', 'f'])
    @app_commands.describe(show_normal='Whether to show normal fissures.',
                           show_steel_path='Whether to show Steel Path fissures.',
                           show_void_storms='Whether to show Void Storm fissures.',
                           max_tier='The maximum tier of fissures to show.',
                           show_lith='Whether to show Lith fissures.',
                           show_meso='Whether to show Meso fissures.',
                           show_neo='Whether to show Neo fissures.',
                           show_axi='Whether to show Axi fissures.',
                           show_requiem='Whether to show Requiem fissures.',
                           show_omnia='Whether to show Omnia fissures.')
    @app_commands.choices(max_tier=[
        Choice(name='Tier 1 - Capture/Exterminate', value=1),
        Choice(name='Tier 2 - + Fast Sabotage/Rescue', value=2),
        Choice(name='Tier 3 - + Excavation/Disruption', value=3),
        Choice(name='Tier 4 - + Slow Sabotage/Spy/Hive', value=4),
        Choice(name='Tier 5 - + Survival/Defense/Mobile Defense/Other', value=5),
    ],
        display_type=[Choice(name='Discord Timestamps', value=FissureEngine.DISPLAY_TYPE_DISCORD),
                      Choice(name='Static Time Left', value=FissureEngine.DISPLAY_TYPE_TIME_LEFT)]
    )
    async def fissures(self, ctx,
                       show_normal: bool = None,
                       show_steel_path: bool = None,
                       show_void_storms: bool = None,
                       max_tier: int = None,
                       show_lith: bool = None,
                       show_meso: bool = None,
                       show_neo: bool = None,
                       show_axi: bool = None,
                       show_requiem: bool = None,
                       show_omnia: bool = None,
                       display_type: str = FissureEngine.DISPLAY_TYPE_DISCORD):
        """Get the current list of fissures."""
        user_id = ctx.author.id
        defaults = self.bot.database.get_fissure_list_defaults(user_id) or {}

        default_values = {
            "show_normal": True,
            "show_steel_path": False,
            "show_void_storms": False,
            "max_tier": 5,
            "show_lith": True,
            "show_meso": True,
            "show_neo": True,
            "show_axi": True,
            "show_requiem": True,
            "show_omnia": True,
            "display_type": FissureEngine.DISPLAY_TYPE_DISCORD
        }

        options = {key: value if value is not None else defaults.get(key, default_values[key])
                   for key, value in locals().items() if key != 'self' and key != 'ctx'}

        channel_config = {key: options[key] for key in options if key.startswith("show_")}
        era_list = self.get_era_list_from_config(channel_config)

        fissure_types = [fissure_type for fissure_type in [FissureEngine.FISSURE_TYPE_NORMAL,
                                                           FissureEngine.FISSURE_TYPE_STEEL_PATH,
                                                           FissureEngine.FISSURE_TYPE_VOID_STORMS]
                         if options.get(f"show_{fissure_type.lower().replace(' ', '_')}", False)]

        embeds = await self.get_fissure_list_embed(fissure_types, era_list=era_list, max_tier=options["max_tier"],
                                                   display_type=options["display_type"])
        await self.bot.send_message(ctx, embed=embeds)

    @commands.hybrid_command(name='set_fissure_notification_type', aliases=['sfnt', 'setfissurenotificationtype'])
    @app_commands.describe(notification_type='The type of notification to receive for fissure subscriptions.')
    @app_commands.choices(notification_type=[
        Choice(name='DM', value='DM'),
        Choice(name='Thread', value='Thread')
    ])
    async def set_fissure_notification_type(self, ctx, notification_type: str):
        """Set your preferred notification type for fissure subscriptions."""
        user_id = ctx.author.id

        # Check if the user exists in the users table
        user_exists = self.bot.database.user_exists(user_id)

        if not user_exists:
            # Create a new entry for the user in the users table
            self.bot.database.create_user(user_id)

        self.bot.database.set_fissure_notification_type(user_id, notification_type)

        await self.bot.send_message(ctx, f"Your fissure notification type has been set to {notification_type}.",
                                    ephemeral=True)

    @commands.hybrid_command(name='fissure_list_channel', aliases=['fissure_list', 'flist', 'flistchannel'],
                             brief='Show a constantly updating fissure list in the given channel.')
    @commands.has_permissions(manage_channels=True)
    @app_commands.describe(show_normal='Whether to show normal fissures.',
                           show_steel_path='Whether to show Steel Path fissures.',
                           show_void_storms='Whether to show Void Storm fissures.',
                           max_tier='The maximum tier of fissures to show.',
                           show_lith='Whether to show Lith fissures.',
                           show_meso='Whether to show Meso fissures.',
                           show_neo='Whether to show Neo fissures.',
                           show_axi='Whether to show Axi fissures.',
                           show_requiem='Whether to show Requiem fissures.',
                           show_omnia='Whether to show Omnia fissures.',
                           display_type='The type of display to use for the fissure list.',
                           channel='The channel to post the fissure list in.')
    @app_commands.choices(max_tier=[
        Choice(name='Tier 1 - Capture/Exterminate', value=1),
        Choice(name='Tier 2 - + Fast Sabotage/Rescue', value=2),
        Choice(name='Tier 3 - + Excavation/Disruption', value=3),
        Choice(name='Tier 4 - + Slow Sabotage/Spy/Hive', value=4),
        Choice(name='Tier 5 - + Survival/Defense/Mobile Defense/Other', value=5),
    ],
        display_type=[Choice(name='Discord Timestamps', value=FissureEngine.DISPLAY_TYPE_DISCORD),
                      Choice(name='Static Time Left', value=FissureEngine.DISPLAY_TYPE_TIME_LEFT)]
    )
    async def fissure_list_channel(self, ctx,
                                   show_normal: bool = commands.parameter(
                                       default=True,
                                       description="Whether to show normal fissures."),
                                   show_steel_path: bool = commands.parameter(
                                       default=False,
                                       description="Whether to show Steel Path fissures."),
                                   show_void_storms: bool = commands.parameter(
                                       default=False,
                                       description="Whether to show Void Storm fissures."),
                                   max_tier: int = commands.parameter(
                                       default=5,
                                       description="The maximum tier of fissures to list."),
                                   show_lith: bool = commands.parameter(
                                       default=True,
                                       description="Whether to show Lith fissures."),
                                   show_meso: bool = commands.parameter(
                                       default=True,
                                       description="Whether to show Meso fissures."),
                                   show_neo: bool = commands.parameter(
                                       default=True,
                                       description="Whether to show Neo fissures."),
                                   show_axi: bool = commands.parameter(
                                       default=True,
                                       description="Whether to show Axi fissures."),
                                   show_requiem: bool = commands.parameter(
                                       default=True,
                                       description="Whether to show Requiem fissures."),
                                   show_omnia: bool = commands.parameter(
                                       default=True,
                                       description="Whether to show Omnia fissures."),
                                   display_type: str = commands.parameter(
                                       default=FissureEngine.DISPLAY_TYPE_DISCORD,
                                       description="The type of display to use for the fissure list."),
                                   channel: discord.TextChannel = commands.parameter(
                                       default=lambda ctx: ctx.channel,
                                       displayed_default='current channel',
                                       description="The channel to list the fissures in.")
                                   ):
        """
        Show a constantly updating fissure list in the given channel.

        You must have the `manage_channels` permission to use this command.

        By default, it will show all fissure types. You can specify which fissure types to show using the
        `show_normal`, `show_steel_path`, and `show_void_storms` parameters.
        """
        if channel is None:
            channel = ctx.channel

        try:
            self.bot.database.set_fissure_list_channel(channel.guild.id, channel.id, None, max_tier,
                                                       show_lith, show_meso, show_neo, show_axi, show_requiem,
                                                       show_omnia, display_type, show_normal, show_steel_path,
                                                       show_void_storms)
        except IntegrityError:
            self.bot.database.unset_fissure_list_channel(channel.guild.id, channel.id, None)
            await self.bot.send_message(ctx, f'The fissure list will no longer be posted/updated in {channel.mention}',
                                        ephemeral=True)
            return

        await self.bot.send_message(ctx, f'A fissure list will now be posted and then updated in {channel.mention}',
                                    ephemeral=True)

    @commands.hybrid_command(name='update_fissure_lists', aliases=['ufl', 'updatefissurelists'],
                             brief='Update all fissure lists.')
    @commands.has_permissions(administrator=True)
    async def update_fissure_lists(self, ctx):
        """Update all fissure lists across all configured channels."""
        await ctx.defer()  # Defer the response to indicate that the bot is working on the command

        try:
            await self.update_all_fissure_lists()
            await self.bot.send_message(ctx, 'All fissure lists have been updated.',
                                        ephemeral=True)
        except Exception as e:
            await self.bot.send_message(ctx, f'An error occurred while updating the fissure lists: {str(e)}',
                                        ephemeral=True)

    @commands.hybrid_command(name='sendview',
                             brief='Sends the view.')
    @commands.has_permissions(administrator=True)
    async def send_view(self, ctx):
        """Update all fissure lists across all configured channels."""
        button_configs = [
            {'emoji': self.bot.emoji_dict['Lith'], 'text': 'Lith Capture',
             'fissure_data': {'era': FissureEngine.ERA_LITH}},
            {'emoji': self.bot.emoji_dict['Meso'], 'text': 'Meso Capture',
             'fissure_data': {'era': FissureEngine.ERA_MESO}},
            {'emoji': self.bot.emoji_dict['Neo'], 'text': 'Neo Capture',
             'fissure_data': {'era': FissureEngine.ERA_NEO}},
            {'emoji': self.bot.emoji_dict['Axi'], 'text': 'Axi Capture', 'fissure_data': {'era': FissureEngine.ERA_AXI}}
        ]

        await ctx.send("Subscribe to the following fissures:", view=FissureView(self.bot, button_configs))

    @app_commands.command(name='create_fissure_view', description='Create a fissure view')
    @app_commands.checks.has_permissions(manage_channels=True)
    async def create_fissure_view(self, interaction: discord.Interaction):
        view = ButtonView(self.bot, interaction)
        await view.send_initial_message()

    @app_commands.command(name='resend_fissure_views', description='Resend all saved fissure views')
    @app_commands.checks.has_permissions(manage_channels=True)
    async def resend_fissure_views(self, interaction: discord.Interaction):
        # Recreate all saved fissure views
        await interaction.response.defer()

        fissure_views = self.bot.database.get_all_fissure_views()

        new_fissure_views = []
        for view_data in fissure_views:
            message_text = view_data['message_text']
            button_configs = view_data['button_configs']
            channel_id = view_data['channel_id']
            message_id = view_data['message_id']

            view = FissureView(self.bot, button_configs)
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                except discord.NotFound:
                    pass

            message = await interaction.channel.send(content=message_text, view=view)
            new_fissure_views.append([message_text, button_configs, message.channel.id, message.id])

        self.bot.database.delete_all_fissure_views()

        for fissure_view in new_fissure_views:
            self.bot.database.save_fissure_view(*fissure_view)

        await interaction.followup.send("All saved fissure views have been resent.", ephemeral=True)

    @app_commands.command(name='edit_fissure_view', description='Edit a fissure view')
    @app_commands.describe(message_id='The ID of the message containing the fissure view to edit')
    @app_commands.checks.has_permissions(manage_channels=True)
    async def edit_fissure_view(self, interaction: discord.Interaction, message_id: str):
        try:
            message_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("Invalid message ID. Please provide a valid message ID.",
                                                    ephemeral=True)
            return

        # Fetch the fissure view data from the database based on the message ID
        fissure_view_data = self.bot.database.get_fissure_view_by_message_id(message_id)

        if fissure_view_data:
            message_text = fissure_view_data['message_text']
            button_configs = fissure_view_data['button_configs']
            channel_id = fissure_view_data['channel_id']

            try:
                channel = self.bot.get_channel(channel_id)
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                await interaction.response.send_message("No fissure view found with the provided message ID.",
                                                        ephemeral=True)
                return

            # Create a new ButtonView instance with the fetched data
            view = ButtonView(self.bot, interaction, message_text, button_configs, message)

            await view.send_initial_message()

        else:
            await interaction.response.send_message("No fissure view found with the provided message ID.",
                                                    ephemeral=True)

    @tasks.loop(seconds=30)
    async def update_all_fissure_lists(self):
        fissure_list_dict = self.bot.database.get_fissure_list_channels()

        async def update_server_fissure_lists(server_id, channel_configs):
            async def update_channel_fissure_list(channel_config):
                try:
                    channel_id = channel_config["channel_id"]
                    await self.post_or_update_fissure_list(server_id, channel_id, channel_config)
                    await asyncio.sleep(1)
                except Exception as e:
                    self.bot.logger.error(f"Error updating fissure list for server {server_id}, "
                                          f"channel {channel_config['channel_id']}", exc_info=e)

            for channel_config in channel_configs:
                await update_channel_fissure_list(channel_config)
                await asyncio.sleep(1)

        server_update_tasks = [update_server_fissure_lists(server_id, channel_configs) for server_id, channel_configs in
                               fissure_list_dict.items()]

        try:
            await asyncio.gather(*server_update_tasks, return_exceptions=True)
        except Exception as e:
            print(f"Error updating fissure lists: {str(e)}")
            traceback.print_exc()  # Print the traceback for debugging purposes

    async def post_or_update_fissure_list(self, server_id: int, channel_id: int, channel_config: dict):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return

        era_list = self.get_era_list_from_config(channel_config)
        max_tier = channel_config["max_tier"]
        display_type = channel_config["display_type"]
        message_id = channel_config["message_id"]

        fissure_types = [fissure_type for fissure_type in [FissureEngine.FISSURE_TYPE_NORMAL,
                                                           FissureEngine.FISSURE_TYPE_STEEL_PATH,
                                                           FissureEngine.FISSURE_TYPE_VOID_STORMS]
                         if channel_config[f"show_{fissure_type.lower().replace(' ', '_')}"]]

        embeds = await self.get_fissure_list_embed(fissure_types,
                                                   display_type=display_type,
                                                   era_list=era_list,
                                                   max_tier=max_tier)

        try:
            await self.update_fissure_list_message(channel, message_id, embeds)
        except (DiscordServerError, ClientOSError, asyncio.TimeoutError):
            pass
        except (discord.NotFound, Exception) as e:
            self.bot.logger.error(f"Error updating fissure list for server {server_id}, \
                                    channel {channel_config['channel_id']}", exc_info=e)
            message = await channel.send(embeds=embeds)
            self.bot.database.set_fissure_list_message_id(channel_config["id"], message.id)

    async def update_fissure_list_message(self, channel, message_id: int, embeds):
        if message_id:
            message = await channel.fetch_message(message_id)
            await message.edit(embeds=embeds)
        else:
            raise Exception("Message ID not found.")

    async def cog_unload(self) -> None:
        self.update_fissure_list.cancel()
        self.update_all_fissure_lists.cancel()

    async def cog_load(self) -> None:
        self.update_fissure_list.start()
        self.update_all_fissure_lists.start()

    @Cog.listener()
    async def on_ready(self):
        if not self.bot.ready:
            self.update_fissure_list.start()

            self.bot.cogs_ready.ready_up("Fissure")
            await sleep(5)
            self.update_all_fissure_lists.start()

            # Recreate all saved fissure views on startup
            fissure_views = self.bot.database.get_all_fissure_views()
            for view_data in fissure_views:
                message_text = view_data['message_text']
                button_configs = view_data['button_configs']
                channel_id = view_data['channel_id']
                message_id = view_data['message_id']

                view = FissureView(self.bot, button_configs)
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.edit(content=message_text, view=view)
                        await sleep(1)
                    except discord.NotFound:
                        pass


async def setup(bot):
    await bot.add_cog(Fissure(bot))
