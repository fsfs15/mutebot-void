import asyncio
import os
from datetime import timedelta

import discord # pyright: ignore[reportMissingImports]
from discord.ext import commands # pyright: ignore[reportMissingImports]

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def toggle_voice_mutes(guild: discord.Guild, mute: bool):
    members = []
    for channel in guild.voice_channels:
        for member in channel.members:
            if not member.bot:
                members.append(member)

    if not members:
        return 0

    await asyncio.gather(*(member.edit(mute=mute) for member in members))
    return len(members)


class VoiceMuteView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild = guild

    async def handle_action(self, interaction: discord.Interaction, mute: bool):
        if not interaction.user.guild_permissions.mute_members:
            await interaction.response.send_message(
                "You need the Mute Members permission to use this.",
                ephemeral=True,
            )
            return

        if not self.guild.me.guild_permissions.mute_members:
            await interaction.response.send_message(
                "The bot does not have Mute Members permission in this server.",
                ephemeral=True,
            )
            return

        count = await toggle_voice_mutes(self.guild, mute)
        action = "Muted" if mute else "Unmuted"
        await interaction.response.send_message(
            f"{action} {count} member(s) in voice channels.",
            ephemeral=True,
            delete_after=10,
        )

    @discord.ui.button(label="Mute Kaml", style=discord.ButtonStyle.red, emoji="🔇")
    async def mute_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, True)

    @discord.ui.button(label="Unmute Kaml", style=discord.ButtonStyle.green, emoji="🔊")
    async def unmute_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, False)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


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
@commands.has_permissions(mute_members=True, manage_messages=True)
async def mutepanel(ctx):
    embed = discord.Embed(
        title="Void Among Mute Panel",
        description="Kifesh tekdem:",
        color=0x2F3136,
    )
    embed.add_field(
        name="",
        value="• Mute Kaml: L'bot ydir mute l'ga3 nas li m3ak f salon.\n• Unmute Kaml: L'bot yna7i l'Mute 3la ga3 nas li m3ak f' salon.",
        inline=False,
    )
    embed.set_footer(text="(edited)")

    message = await ctx.send(embed=embed, view=VoiceMuteView(ctx.guild))
    await message.pin()


@bot.command()
@commands.has_permissions(mute_members=True)
async def muteall(ctx):
    muted = await toggle_voice_mutes(ctx.guild, True)
    await ctx.send(f"Muted {muted} member(s) in voice channels.")


@bot.command()
@commands.has_permissions(mute_members=True)
async def unmuteall(ctx):
    unmuted = await toggle_voice_mutes(ctx.guild, False)
    await ctx.send(f"Unmuted {unmuted} member(s) in voice channels.")


@bot.command()
@commands.has_permissions(mute_members=True)
async def muteone(ctx, member: discord.Member):
    await member.edit(mute=True)
    await ctx.send(f"Muted {member.mention}")


@bot.command()
@commands.has_permissions(mute_members=True)
async def unmuteone(ctx, member: discord.Member):
    await member.edit(mute=False)
    await ctx.send(f"Unmuted {member.mention}")


@bot.command()
@commands.has_permissions(deafen_members=True)
async def deafenone(ctx, member: discord.Member):
    await member.edit(deafen=True)
    await ctx.send(f"Deafened {member.mention}")


@bot.command()
@commands.has_permissions(deafen_members=True)
async def undeafenone(ctx, member: discord.Member):
    await member.edit(deafen=False)
    await ctx.send(f"Undeafened {member.mention}")


@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeoutmember(ctx, member: discord.Member, minutes: int, *, reason: str = "No reason"):
    duration = discord.utils.utcnow() + timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await ctx.send(f"Timed out {member.mention} for {minutes} minute(s). Reason: {reason}")


bot.run(os.environ["DISCORD_TOKEN"])