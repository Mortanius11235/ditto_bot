import discord
from discord.ext import commands
import os

# ================= CONFIG =================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= STATE =================

bot_state = {
    "active": False,
    "letters": {}
}

# ================= HELPERS =================

def is_owner_or_moderator(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False

    # Dueño del servidor
    if interaction.user.id == interaction.guild.owner_id:
        return True

    # Rol Moderador
    for role in interaction.user.roles:
        if role.name.lower() == "guardians of sakura (moderators)":
            return True

    return False

# ================= EVENTS =================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot conectado como {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not bot_state["active"]:
        await bot.process_commands(message)
        return

    content = message.content.strip()
    if len(content) == 1 and content.isalpha():
        letter = content.upper()

        if letter in bot_state["letters"]:
            prev = bot_state["letters"][letter]
            await message.channel.send(
                f"🔁 **Letter repeated!** / **Lettera ripetuta!**\n"
                f"Letter / Lettera: **{letter}**\n"
                f"Said now by / Detta ora da: {message.author.mention}\n"
                f"Previously said by / Detta prima da: <@{prev['user_id']}> ({prev['username']})"
            )
        else:
            bot_state["letters"][letter] = {
                "user_id": message.author.id,
                "username": message.author.display_name
            }

    await bot.process_commands(message)

# ================= COMMANDS =================

@bot.tree.command(name="on", description="Activate the bot / Attiva il bot")
async def turn_on(interaction: discord.Interaction):
    if not is_owner_or_moderator(interaction):
        await interaction.response.send_message(
            "⛔ You don't have permission to use this command.\n"
            "Solo il proprietario del server o un moderatore può usarlo.",
            ephemeral=True
        )
        return

    if bot_state["active"]:
        bot_state["letters"] = {}
        await interaction.response.send_message(
            "🔄 **Letters reset!** / **Lettere resettate!**"
        )
    else:
        bot_state["active"] = True
        bot_state["letters"] = {}
        await interaction.response.send_message(
            "✅ **Bot activated!** / **Bot attivato!**"
        )

@bot.tree.command(name="off", description="Deactivate the bot / Disattiva il bot")
async def turn_off(interaction: discord.Interaction):
    if not is_owner_or_moderator(interaction):
        await interaction.response.send_message(
            "⛔ You don't have permission to use this command.\n"
            "Solo il proprietario del server o un moderatore può usarlo.",
            ephemeral=True
        )
        return

    bot_state["active"] = False
    await interaction.response.send_message(
        "⏸️ **Bot deactivated!** / **Bot disattivato!**"
    )

# ================= TOKEN =================

TOKEN = os.getenv("DISCORD_TOKEN")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ Error: DISCORD_TOKEN not found")
        exit(1)

    bot.run(TOKEN)