import discord
from discord import app_commands
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
    "letters": {}  # {letter: {"user_id": id, "username": name}}
}

# ================= EVENTS =================

@bot.event
async def on_ready():
    # Sincronización GLOBAL de slash commands (producción)
    await bot.tree.sync()
    print(f"Bot conectado como {bot.user}")

@bot.event
async def on_message(message):
    # Ignorar mensajes del bot
    if message.author.bot:
        return

    # Si el bot no está activo, igual permitir comandos
    if not bot_state["active"]:
        await bot.process_commands(message)
        return

    # Procesar letras
    content = message.content.strip()
    if len(content) == 1 and content.isalpha():
        letter = content.upper()

        if letter in bot_state["letters"]:
            previous_user_id = bot_state["letters"][letter]["user_id"]
            previous_username = bot_state["letters"][letter]["username"]

            await message.channel.send(
                f"🔁 **Letter repeated!** / **Lettera ripetuta!**\n"
                f"Letter / Lettera: **{letter}**\n"
                f"Said now by / Detta ora da: {message.author.mention}\n"
                f"Previously said by / Detta prima da: <@{previous_user_id}> ({previous_username})"
            )
        else:
            bot_state["letters"][letter] = {
                "user_id": message.author.id,
                "username": message.author.display_name
            }

    # 🔴 CRÍTICO: permitir que Discord procese comandos
    await bot.process_commands(message)

# ================= COMMANDS =================

@bot.tree.command(name="on", description="Activate the bot / Attiva il bot")
async def turn_on(interaction: discord.Interaction):
    if bot_state["active"]:
        bot_state["letters"] = {}
        await interaction.response.send_message(
            "🔄 **Letters reset!** / **Lettere resettate!**\n"
            "Starting fresh / Si ricomincia da capo"
        )
    else:
        bot_state["active"] = True
        bot_state["letters"] = {}
        await interaction.response.send_message(
            "✅ **Bot activated!** / **Bot attivato!**\n"
            "Tracking letters / Traccia lettere"
        )

@bot.tree.command(name="off", description="Deactivate the bot / Disattiva il bot")
async def turn_off(interaction: discord.Interaction):
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