﻿from AAA3A_utils import Cog, CogsUtils, Menu  # isort:skip
from redbot.core import commands, Config  # isort:skip
from redbot.core.bot import Red  # isort:skip
from redbot.core.i18n import Translator, cog_i18n  # isort:skip
import discord  # isort:skip
import typing  # isort:skip

import asyncio
from functools import partial

from redbot.core.utils.chat_formatting import inline

from .converters import Emoji, EmojiCommandConverter

# Credits:
# General repo credits.
# Thanks to TrustyJAID for the two converter for the bulk command arguments! (https://github.com/TrustyJAID/Trusty-cogs/blob/main/roletools/converter.py)
# Thanks to Yami for the technique in the init file of some cogs to load the interaction client only if it is not already loaded! Before this fix, when a user clicked a button, the actions would be run about 10 times, causing a huge spam and loop in the channel.
# Thanks to Kuro for the emoji converter (https://canary.discord.com/channels/133049272517001216/133251234164375552/1014520590239019048)!

_ = Translator("CommandsButtons", __file__)


@cog_i18n(_)
class CommandsButtons(Cog):
    """A cog to allow a user to execute a command by clicking on a button!"""

    def __init__(self, bot: Red) -> None:
        super().__init__(bot=bot)

        self.config: Config = Config.get_conf(
            self,
            identifier=205192943327321000143939875896557571750,  # 370638632963
            force_registration=True,
        )
        self.CONFIG_SCHEMA = 2
        self.commands_buttons_global: typing.Dict[str, typing.Optional[int]] = {
            "CONFIG_SCHEMA": None,
        }
        self.commands_buttons_guild: typing.Dict[
            str, typing.Dict[str, typing.Dict[str, typing.Dict[str, str]]]
        ] = {
            "commands_buttons": {},
        }
        self.config.register_global(**self.commands_buttons_global)
        self.config.register_guild(**self.commands_buttons_guild)

        self.cache: typing.List[commands.Context] = []

    async def cog_load(self) -> None:
        await super().cog_load()
        await self.edit_config_schema()
        await self.load_buttons()

    async def red_delete_data_for_user(self, *args, **kwargs) -> None:
        """Nothing to delete."""
        return

    async def red_get_data_for_user(self, *args, **kwargs) -> typing.Dict[str, typing.Any]:
        """Nothing to get."""
        return {}

    async def edit_config_schema(self) -> None:
        CONFIG_SCHEMA = await self.config.CONFIG_SCHEMA()
        if CONFIG_SCHEMA is None:
            CONFIG_SCHEMA = 1
            await self.config.CONFIG_SCHEMA(CONFIG_SCHEMA)
        if CONFIG_SCHEMA == self.CONFIG_SCHEMA:
            return
        if CONFIG_SCHEMA == 1:
            for guild_id in await self.config.all_guilds():
                commands_buttons = await self.config.guild_from_id(guild_id).commands_buttons()
                for message in commands_buttons:
                    message_data = commands_buttons[message].copy()
                    for emoji in message_data:
                        data = commands_buttons[message].pop(emoji)
                        data["emoji"] = emoji
                        config_identifier = CogsUtils.generate_key(
                            length=5, existing_keys=commands_buttons[message]
                        )
                        commands_buttons[message][config_identifier] = data
                await self.config.guild_from_id(guild_id).commands_buttons.set(commands_buttons)
            CONFIG_SCHEMA = 2
            await self.config.CONFIG_SCHEMA.set(CONFIG_SCHEMA)
        if CONFIG_SCHEMA < self.CONFIG_SCHEMA:
            CONFIG_SCHEMA = self.CONFIG_SCHEMA
            await self.config.CONFIG_SCHEMA.set(CONFIG_SCHEMA)
        self.log.info(
            f"The Config schema has been successfully modified to {self.CONFIG_SCHEMA} for the {self.qualified_name} cog."
        )

    async def load_buttons(self) -> None:
        all_guilds = await self.config.all_guilds()
        for guild in all_guilds:
            config = all_guilds[guild]["commands_buttons"]
            for message in config:
                channel = self.bot.get_channel(int((str(message).split("-"))[0]))
                if channel is None:
                    continue
                message_id = int((str(message).split("-"))[1])
                try:
                    view = self.get_buttons(config=config, message=message)
                    self.bot.add_view(view, message_id=message_id)
                    self.views[discord.PartialMessage(channel=channel, id=message_id)] = view
                except Exception as e:
                    self.log.error(
                        f"The Button View could not be added correctly for the `{guild}-{message}` message.",
                        exc_info=e,
                    )

    async def on_button_interaction(
        self, interaction: discord.Interaction, config_identifier: str
    ) -> None:
        if await self.bot.cog_disabled_in_guild(self, interaction.guild):
            return
        if not interaction.data["custom_id"].startswith("commands_buttons"):
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        config = await self.config.guild(interaction.guild).commands_buttons.all()
        if f"{interaction.channel.id}-{interaction.message.id}" not in config:
            await interaction.followup.send(_("This message is not in Config."), ephemeral=True)
            return
        if config_identifier not in config[f"{interaction.channel.id}-{interaction.message.id}"]:
            await interaction.followup.send(_("This button is not in Config."), ephemeral=True)
            return
        command = config[f"{interaction.channel.id}-{interaction.message.id}"][config_identifier][
            "command"
        ]
        context = await CogsUtils.invoke_command(
            bot=interaction.client,
            author=interaction.user,
            channel=interaction.channel,
            command=command,
            message=interaction.message,
            __is_mocked__=True,
        )
        if not isinstance(context, commands.Context) or not context.valid:
            await interaction.followup.send(_("The command don't exist."), ephemeral=True)
            return
        if not await context.command.can_run(context):
            await interaction.followup.send(
                _("You are not allowed to execute this command."), ephemeral=True
            )
            return
        self.cache.append(context)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context) -> None:
        if ctx in self.cache:
            self.cache.remove(ctx)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if ctx not in self.cache:
            return
        self.cache.remove(ctx)
        if isinstance(error, commands.CommandInvokeError):
            await asyncio.sleep(0.7)
            self.log.error(
                f"This exception in the '{ctx.command.qualified_name}' command may have been triggered by the use of CommandsButtons. Check that the same error occurs with the text command, before reporting it.",
                exc_info=None,
            )
            message = f"This error in the '{ctx.command.qualified_name}' command may have been triggered by the use of CommandsButtons.\nCheck that the same error occurs with the text command, before reporting it."
            await ctx.send(inline(message))

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        config = await self.config.guild(message.guild).commands_buttons.all()
        if f"{message.channel.id}-{message.id}" not in config:
            return
        del config[f"{message.channel.id}-{message.id}"]
        await self.config.guild(message.guild).commands_buttons.set(config)

    @commands.guild_only()
    @commands.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    @commands.hybrid_group()
    async def commandsbuttons(self, ctx: commands.Context) -> None:
        """Group of commands to use CommandsButtons."""
        pass

    @commandsbuttons.command(aliases=["+"])
    async def add(
        self,
        ctx: commands.Context,
        message: discord.Message,
        command: str,
        emoji: typing.Optional[Emoji],
        style_button: typing.Optional[typing.Literal["1", "2", "3", "4"]] = "2",
        *,
        text_button: typing.Optional[commands.Range[str, 1, 100]] = None,
    ) -> None:
        """Add a command-button for a message.

        (Use the number for the color.)
        • `primary`: 1
        • `secondary`: 2
        • `success`: 3
        • `danger`: 4
        # Aliases
        • `blurple`: 1
        • `grey`: 2
        • `gray`: 2
        • `green`: 3
        • `red`: 4
        """
        if message.author != ctx.me:
            raise commands.UserFeedbackCheckFailure(
                _("I have to be the author of the message for the command-button to work.")
            )
        channel_permissions = message.channel.permissions_for(ctx.me)
        if (
            not channel_permissions.view_channel
            or not channel_permissions.read_messages
            or not channel_permissions.read_message_history
        ):
            raise commands.UserFeedbackCheckFailure(
                _(
                    "I don't have sufficient permissions on the channel where the message you specified is located.\nI need the permissions to see the messages in that channel."
                )
            )
        if ctx.prefix != "/":
            msg = ctx.message
            msg.content = f"{ctx.prefix}{command}"
            new_ctx = await ctx.bot.get_context(msg)
            if not new_ctx.valid:
                raise commands.UserFeedbackCheckFailure(
                    _("You have not specified a correct command.")
                )
        if emoji is None and text_button is None:
            raise commands.UserFeedbackCheckFailure(_("You have to specify at least an emoji or a label."))
        if emoji is not None and ctx.interaction is None and ctx.bot_permissions.add_reactions:
            try:
                await ctx.message.add_reaction(emoji)
            except discord.HTTPException:
                raise commands.UserFeedbackCheckFailure(
                    _(
                        "The emoji you selected seems invalid. Check that it is an emoji. If you have Nitro, you may have used a custom emoji from another server."
                    )
                )
        config = await self.config.guild(ctx.guild).commands_buttons.all()
        if f"{message.channel.id}-{message.id}" not in config:
            if message.components:
                raise commands.UserFeedbackCheckFailure(_("This message already has components."))
            config[f"{message.channel.id}-{message.id}"] = {}
        if len(config[f"{message.channel.id}-{message.id}"]) > 25:
            raise commands.UserFeedbackCheckFailure(
                _("I can't do more than 25 commands-buttons for one message.")
            )
        config_identifier = CogsUtils.generate_key(
            length=5, existing_keys=config[f"{message.channel.id}-{message.id}"]
        )
        config[f"{message.channel.id}-{message.id}"][config_identifier] = {
            "command": command,
            "emoji": f"{getattr(emoji, 'id', emoji)}" if emoji is not None else None,
            "style_button": int(style_button),
            "text_button": text_button,
        }
        view = self.get_buttons(config, message)
        message = await message.edit(view=view)
        self.views[message] = view
        await self.config.guild(ctx.guild).commands_buttons.set(config)
        await self.list.callback(self, ctx, message=message)

    @commandsbuttons.command()
    async def bulk(
        self,
        ctx: commands.Context,
        message: discord.Message,
        commands_buttons: commands.Greedy[EmojiCommandConverter],
    ) -> None:
        """Add commands-buttons for a message.

        ```[p]commandsbuttons bulk <message> ":reaction1:|ping" ":reaction2:|ping" :reaction3:|ping"```
        """
        if message.author != ctx.me:
            raise commands.UserFeedbackCheckFailure(
                _("I have to be the author of the message for the command-button to work.")
            )
        if len(commands_buttons) == 0:
            raise commands.UserFeedbackCheckFailure(
                _("You have not specified any valid command-button.")
            )
        channel_permissions = message.channel.permissions_for(ctx.me)
        if (
            not channel_permissions.view_channel
            or not channel_permissions.read_messages
            or not channel_permissions.read_message_history
        ):
            raise commands.UserFeedbackCheckFailure(
                _(
                    "I don't have sufficient permissions on the channel where the message you specified is located.\nI need the permissions to see the messages in that channel."
                )
            )
        if ctx.interaction is None and ctx.bot_permissions.add_reactions:
            try:
                for emoji, command in commands_buttons[:19]:
                    if ctx.prefix != "/":
                        msg = ctx.message
                        msg.content = f"{ctx.prefix}{command}"
                        new_ctx = await ctx.bot.get_context(msg)
                        if not new_ctx.valid:
                            raise commands.UserFeedbackCheckFailure(
                                _("At least one of these commands is invalid.")
                            )
                    if emoji is None:
                        continue
                    await ctx.message.add_reaction(emoji)
            except discord.HTTPException:
                raise commands.UserFeedbackCheckFailure(
                    _(
                        "An emoji you selected seems invalid. Check that it is an emoji. If you have Nitro, you may have used a custom emoji from another server."
                    )
                )
        config = await self.config.guild(ctx.guild).commands_buttons.all()
        if f"{message.channel.id}-{message.id}" not in config:
            if message.components:
                raise commands.UserFeedbackCheckFailure(_("This message already has components."))
            config[f"{message.channel.id}-{message.id}"] = {}
        if len(config[f"{message.channel.id}-{message.id}"]) + len(commands_buttons) > 25:
            raise commands.UserFeedbackCheckFailure(
                _("I can't do more than 25 roles-buttons for one message.")
            )
        for emoji, command in commands_buttons:
            config_identifier = CogsUtils.generate_key(
                length=5, existing_keys=config[f"{message.channel.id}-{message.id}"]
            )
            config[f"{message.channel.id}-{message.id}"][config_identifier] = {
                "command": command,
                "emoji": f"{getattr(emoji, 'id', emoji)}" if emoji is not None else None,
                "style_button": 2,
                "text_button": None,
            }
        view = self.get_buttons(config, message)
        message = await message.edit(view=view)
        self.views[message] = view
        await self.config.guild(ctx.guild).commands_buttons.set(config)
        await self.list.callback(self, ctx, message=message)

    @commandsbuttons.command(aliases=["-"])
    async def remove(self, ctx: commands.Context, message: discord.Message, config_identifier: str) -> None:
        """Remove a command-button for a message.

        Use `[p]commandsbuttons list <message>` to find the config identifier.
        """
        if message.author != ctx.me:
            raise commands.UserFeedbackCheckFailure(
                _("I have to be the author of the message for the command-button to work.")
            )
        config = await self.config.guild(ctx.guild).commands_buttons.all()
        if f"{message.channel.id}-{message.id}" not in config:
            raise commands.UserFeedbackCheckFailure(
                _("No command-button is configured for this message.")
            )
        if config_identifier not in config[f"{message.channel.id}-{message.id}"]:
            raise commands.UserFeedbackCheckFailure(
                _("I wasn't watching for this button on this message.")
            )
        del config[f"{message.channel.id}-{message.id}"][config_identifier]
        if config[f"{message.channel.id}-{message.id}"] == {}:
            del config[f"{message.channel.id}-{message.id}"]
            await message.edit(view=None)
        else:
            view = self.get_buttons(config, message)
            message = await message.edit(view=view)
            self.views[message] = view
        await self.config.guild(ctx.guild).commands_buttons.set(config)
        await self.list.callback(self, ctx, message=message)

    @commandsbuttons.command()
    async def clear(self, ctx: commands.Context, message: discord.Message) -> None:
        """Clear all commands-buttons for a message."""
        if message.author != ctx.me:
            raise commands.UserFeedbackCheckFailure(
                _("I have to be the author of the message for the role-button to work.")
            )
        config = await self.config.guild(ctx.guild).commands_buttons.all()
        if f"{message.channel.id}-{message.id}" not in config:
            raise commands.UserFeedbackCheckFailure(
                _("No command-button is configured for this message.")
            )
        try:
            await message.edit(view=None)
        except discord.HTTPException:
            pass
        del config[f"{message.channel.id}-{message.id}"]
        await self.config.guild(ctx.guild).commands_buttons.set(config)
        await ctx.send(_("Commands-buttons cleared for this message."))

    @commands.bot_has_permissions(embed_links=True)
    @commandsbuttons.command()
    async def list(self, ctx: commands.Context, message: discord.Message = None) -> None:
        commands_buttons = await self.config.guild(ctx.guild).commands_buttons()
        for command_button in commands_buttons:
            commands_buttons[command_button]["message"] = command_button
        if message is None:
            _commands_buttons = list(commands_buttons.values()).copy()
        elif f"{message.channel.id}-{message.id}" not in commands_buttons:
            raise commands.UserFeedbackCheckFailure(
                _("No command-button is configured for this message.")
            )
        else:
            _commands_buttons = commands_buttons.copy()
            _commands_buttons = [commands_buttons[f"{message.channel.id}-{message.id}"]]
        if not _commands_buttons:
            raise commands.UserFeedbackCheckFailure(_("No commands-buttons in this server."))
        lists = []
        while _commands_buttons != []:
            li = _commands_buttons[:5]
            _commands_buttons = _commands_buttons[5:]
            lists.append(li)
        embeds = []
        for li in lists:
            embed: discord.Embed = discord.Embed(
                title=_("Commands Buttons"),
                description=_("There is {len_commands_buttons} commands buttons in this server.").format(
                    len_commands_buttons=len(commands_buttons)
                ),
                color=await ctx.embed_color(),
            )
            embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
            for command_button in li:
                value = _("Message Jump Link: {message_jump_link}\n").format(message_jump_link=f"https://discord.com/channels/{ctx.guild.id}/{command_button['message'].replace('-', '/')}")
                value += "\n".join([f"• `{config_identifier}` - Emoji {ctx.bot.get_emoji(int(data['emoji'])) if data['emoji'].isdigit() else data['emoji']} - Label `{data['text_button']}` - Command `[p]{data['command']}`" for config_identifier, data in command_button.items() if config_identifier != "message"])
                embed.add_field(
                    name="\u200B", value=value, inline=False
                )
            embeds.append(embed)
        await Menu(pages=embeds).start(ctx)

    @commandsbuttons.command(hidden=True)
    async def purge(self, ctx: commands.Context) -> None:
        """Clear all commands-buttons for a guild."""
        await self.config.guild(ctx.guild).commands_buttons.clear()
        await ctx.send(_("All commands-buttons purged."))

    def get_buttons(
        self, config: typing.Dict[str, dict], message: typing.Union[discord.Message, str]
    ) -> discord.ui.View:
        message = (
            f"{message.channel.id}-{message.id}"
            if isinstance(message, discord.Message)
            else message
        )
        view = discord.ui.View(timeout=None)
        for config_identifier in config[message]:
            if config[message][config_identifier]["emoji"] is not None:
                try:
                    int(config[message][config_identifier]["emoji"])
                except ValueError:
                    b = config[message][config_identifier]["emoji"]
                else:
                    b = str(self.bot.get_emoji(int(config[message][config_identifier]["emoji"])))
            else:
                b = None
            button = discord.ui.Button(
                label=config[message][config_identifier]["text_button"],
                emoji=b,
                style=discord.ButtonStyle(
                    config[message][config_identifier].get("style_button", 2)
                ),
                custom_id=f"commands_buttons {config_identifier}",
                disabled=False,
            )
            button.callback = partial(
                self.on_button_interaction, config_identifier=config_identifier
            )
            view.add_item(button)
        return view
