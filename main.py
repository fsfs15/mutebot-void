import asyncio
import os

import discord # pyright: ignore[reportMissingImports]
from discord.ext import commands # pyright: ignore[reportMissingImports]


VOICE_CHANNEL_IDS = (
    1373282885712351333,
    1373282902036713553,
    1534797504820809801,
    1535720878778876015,
)
if len(set(VOICE_CHANNEL_IDS)) != 4:
    raise RuntimeError("The four configured voice channel IDs must be unique.")

ALLOWED_ROLE_ID = 1550533183085486110
ROLE_REQUIRED_MESSAGE = "Lazm tkon Among Manager bach dir mute ou unmute."
VOICE_REQUIRED_MESSAGE = "Mute ma y5dmch f had salon. Khassk tkoun f wa7ed men salons vocaux li mkhtarin."

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
_mute_view_registered = False


def has_allowed_role(member: discord.Member) -> bool:
    return any(role.id == ALLOWED_ROLE_ID for role in member.roles)


def get_selected_voice_channels(
    guild: discord.Guild,
) -> tuple[discord.VoiceChannel | discord.StageChannel, ...] | None:
    channels = tuple(guild.get_channel(channel_id) for channel_id in VOICE_CHANNEL_IDS)
    if all(isinstance(channel, (discord.VoiceChannel, discord.StageChannel)) for channel in channels):
        return channels
    return None


def member_is_in_selected_voice_channel(
    member: discord.Member,
    channels: tuple[discord.VoiceChannel | discord.StageChannel, ...],
) -> discord.VoiceChannel | discord.StageChannel | None:
    if member.voice is None or member.voice.channel not in channels:
        return None
    return member.voice.channel


async def toggle_voice_mutes(
    channel: discord.VoiceChannel | discord.StageChannel,
    mute: bool,
) -> int:
    members = [member for member in channel.members if not member.bot]
    if not members:
        return 0

    await asyncio.gather(*(member.edit(mute=mute) for member in members))
    return len(members)


class VoiceMuteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def handle_action(self, interaction: discord.Interaction, mute: bool):
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This panel can only be used by a server member.",
                ephemeral=True,
            )
            return

        if not has_allowed_role(interaction.user):
            await interaction.response.send_message(
                ROLE_REQUIRED_MESSAGE,
                ephemeral=True,
            )
            return

        if not guild.me.guild_permissions.mute_members:
            await interaction.response.send_message(
                "The bot does not have Mute Members permission in this server.",
                ephemeral=True,
            )
            return

        channels = get_selected_voice_channels(guild)
        if channels is None:
            await interaction.response.send_message(
                "The configured voice channel was not found in this server.",
                ephemeral=True,
            )
            return

        channel = member_is_in_selected_voice_channel(interaction.user, channels)
        if channel is None:
            await interaction.response.send_message(
                VOICE_REQUIRED_MESSAGE,
                ephemeral=True,
            )
            return

        count = await toggle_voice_mutes(channel, mute)
        action = "Muted" if mute else "Unmuted"
        await interaction.response.send_message(
            f"{action} {count} member(s) in {channel.mention}.",
            ephemeral=True,
            delete_after=10,
        )

    @discord.ui.button(
        label="Mute Kaml",
        style=discord.ButtonStyle.red,
        emoji="🔇",
        custom_id="voice_mute_panel:mute_all",
    )
    async def mute_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, True)

    @discord.ui.button(
        label="Unmute Kaml",
        style=discord.ButtonStyle.green,
        emoji="🔊",
        custom_id="voice_mute_panel:unmute_all",
    )
    async def unmute_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, False)


@bot.event
async def on_ready():
    global _mute_view_registered
    if not _mute_view_registered:
        bot.add_view(VoiceMuteView())
        _mute_view_registered = True
    print(f"Logged in as {bot.user}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send(ROLE_REQUIRED_MESSAGE)
        return

    await commands.Bot.on_command_error(bot, ctx, error)


@bot.command(name="debug")
async def debug(ctx):
    perms = ctx.guild.me.guild_permissions
    await ctx.send(
        "```\n"
        f"guild: {ctx.guild.name}\n"
        f"bot_admin: {perms.administrator}\n"
        f"bot_mute: {perms.mute_members}\n"
        f"bot_manage_messages: {perms.manage_messages}\n"
        f"user_mute: {ctx.author.guild_permissions.mute_members}\n"
        "```"
    )


@bot.command(name="mutepanel")
@commands.has_role(ALLOWED_ROLE_ID)
async def mutepanel(ctx):
    if not ctx.guild.me.guild_permissions.manage_messages:
        await ctx.send("The bot does not have Manage Messages permission to pin the panel.")
        return

    embed = discord.Embed(
        title="🎙️ Contrôle Mute",
        description="**Kifesh tekhdem:**",
        color=0x2F3136,
    )
    embed.add_field(
        name="",
        value=(
            "• 🔴 `Mute Kaml`: L'bot ydir Mute l'ga3 nas li m3ak f l'salon.\n"
            "• 🟢 `Unmute Kaml`: L'bot yna7i l'Mute 3la ga3 nas li m3ak f l'salon."
        ),
        inline=False,
    )

    message = await ctx.send(embed=embed, view=VoiceMuteView())
    await message.pin()


@bot.command()
@commands.has_role(ALLOWED_ROLE_ID)
async def muteall(ctx):
    channels = get_selected_voice_channels(ctx.guild)
    if channels is None:
        await ctx.send("The configured voice channel was not found in this server.")
        return
    channel = member_is_in_selected_voice_channel(ctx.author, channels)
    if channel is None:
        await ctx.send(VOICE_REQUIRED_MESSAGE)
        return
    if not ctx.guild.me.guild_permissions.mute_members:
        await ctx.send("The bot does not have Mute Members permission in this server.")
        return

    muted = await toggle_voice_mutes(channel, True)
    await ctx.send(f"Muted {muted} member(s) in {channel.mention}.")


@bot.command()
@commands.has_role(ALLOWED_ROLE_ID)
async def unmuteall(ctx):
    channels = get_selected_voice_channels(ctx.guild)
    if channels is None:
        await ctx.send("The configured voice channel was not found in this server.")
        return
    channel = member_is_in_selected_voice_channel(ctx.author, channels)
    if channel is None:
        await ctx.send(VOICE_REQUIRED_MESSAGE)
        return
    if not ctx.guild.me.guild_permissions.mute_members:
        await ctx.send("The bot does not have Mute Members permission in this server.")
        return

    unmuted = await toggle_voice_mutes(channel, False)
    await ctx.send(f"Unmuted {unmuted} member(s) in {channel.mention}.")


@bot.command()
@commands.has_role(ALLOWED_ROLE_ID)
async def muteone(ctx, member: discord.Member):
    channels = get_selected_voice_channels(ctx.guild)
    if channels is None:
        await ctx.send("The configured voice channel was not found in this server.")
        return
    channel = member_is_in_selected_voice_channel(ctx.author, channels)
    if channel is None:
        await ctx.send(VOICE_REQUIRED_MESSAGE)
        return
    if member.voice is None or member.voice.channel != channel:
        await ctx.send(f"{member.mention} must be in your voice channel, {channel.mention}.")
        return
    if not ctx.guild.me.guild_permissions.mute_members:
        await ctx.send("The bot does not have Mute Members permission in this server.")
        return

    await member.edit(mute=True)
    await ctx.send(f"Muted {member.mention}")


@bot.command()
@commands.has_role(ALLOWED_ROLE_ID)
async def unmuteone(ctx, member: discord.Member):
    channels = get_selected_voice_channels(ctx.guild)
    if channels is None:
        await ctx.send("The configured voice channel was not found in this server.")
        return
    channel = member_is_in_selected_voice_channel(ctx.author, channels)
    if channel is None:
        await ctx.send(VOICE_REQUIRED_MESSAGE)
        return
    if member.voice is None or member.voice.channel != channel:
        await ctx.send(f"{member.mention} must be in your voice channel, {channel.mention}.")
        return
    if not ctx.guild.me.guild_permissions.mute_members:
        await ctx.send("The bot does not have Mute Members permission in this server.")
        return

    await member.edit(mute=False)
    await ctx.send(f"Unmuted {member.mention}")


bot.run(os.environ["DISCORD_TOKEN"])
