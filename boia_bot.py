import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime
import unicodedata

# ================= CONFIG =================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.name = "Impiccato"

DATA_FILE = "hangman_data.json"

# ================= GAME STATE =================

game_state = {
    "active": False,
    "secret": "",
    "hint": "",
    "secret_normalized": "",
    "letters_needed": set(),
    "letters_found": set(),
    "wrong_letters": set(),
    "players": {},
    "last_player": None,
    "initial_lives": 5,
    "round_number": 0,
    "lose_points_mode": False
}

persistent_data = {
    "daily_ranking": {},
    "historical_ranking": {},
    "last_reset": datetime.now().date().isoformat()
}

# ================= UTILITIES =================

def load_data():
    global persistent_data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            persistent_data = json.load(f)

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(persistent_data, f, indent=2, ensure_ascii=False)

def normalize_text(text):
    nfd = unicodedata.normalize("NFD", text.upper())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")

def get_letters_in_phrase(phrase):
    normalized = normalize_text(phrase)
    return set(c for c in normalized if c.isalpha())

def check_last_letter_win():
    return len(game_state["letters_needed"]) == 0

def add_points_to_player(user_id, username, points):
    uid = str(user_id)

    for ranking in ("daily_ranking", "historical_ranking"):
        if uid not in persistent_data[ranking]:
            persistent_data[ranking][uid] = {"name": username, "points": 0}
        persistent_data[ranking][uid]["points"] += points
        persistent_data[ranking][uid]["name"] = username

    save_data()

def get_initial_pattern(secret):
    return " ".join("_" if c != " " else " " for c in secret.upper())

def get_word_lengths(secret):
    return "+".join(str(len(w)) for w in secret.split())

def get_current_pattern():
    """Genera el patrón actual con letras adivinadas"""
    pattern = []
    for char in game_state["secret"]:
        if char == " ":
            pattern.append(" ")
        elif normalize_text(char) in game_state["letters_found"]:
            pattern.append(char)
        else:
            pattern.append("_")
    return " ".join(pattern)

# ================= EVENTS =================

@bot.event
async def on_ready():
    load_data()
    check_daily_reset.start()
    await bot.tree.sync()
    print(f"Impiccato Bot conectado como {bot.user}")

@tasks.loop(hours=1)
async def check_daily_reset():
    today = datetime.now().date().isoformat()
    if persistent_data["last_reset"] != today:
        persistent_data["daily_ranking"] = {}
        persistent_data["last_reset"] = today
        save_data()

def is_owner():
    async def predicate(interaction: discord.Interaction):
        return interaction.guild and interaction.user.id == interaction.guild.owner_id
    return app_commands.check(predicate)

# ================= COMMANDS =================

@bot.tree.command(name="start_game", description="Start a new game / Inizia una nuova partita")
@app_commands.describe(
    secret="The secret word or phrase / La parola o frase segreta",
    hint="Hint for players / Indizio per i giocatori",
    lives="Initial lives for each player / Vite iniziali per ogni giocatore"
)
@is_owner()
async def start_game(interaction: discord.Interaction, secret: str, hint: str, lives: int = 5):
    if game_state["active"]:
        await interaction.response.send_message("❌ There's already an active game!", ephemeral=True)
        return

    game_state.update({
        "active": True,
        "round_number": game_state["round_number"] + 1,
        "lose_points_mode": False,
        "secret": secret.upper(),
        "hint": hint,
        "secret_normalized": normalize_text(secret),
        "letters_needed": get_letters_in_phrase(secret),
        "letters_found": set(),
        "wrong_letters": set(),
        "players": {},
        "last_player": None,
        "initial_lives": lives
    })

    pattern = get_initial_pattern(secret)
    lengths = get_word_lengths(secret)

    await interaction.response.send_message(
        f"**🎮 ROUND {game_state['round_number']}**\n\n"
        f"**Parola/frase:** `{pattern}` ({lengths})\n\n"
        f"**Tips:**\n*{hint}*\n\n"
        f"Use `/l <letter>` to guess a letter or `/w <phrase>` to guess the word!\n"
        f"Usa `/l <lettera>` per indovinare una lettera o `/w <frase>` per indovinare la parola!\n\n"
        f"❤️ Lives / Vite: **{lives}**"
    )

@bot.tree.command(name="l", description="Guess a letter / Indovina una lettera")
@app_commands.describe(letter="The letter to guess / La lettera da indovinare")
async def guess_letter(interaction: discord.Interaction, letter: str):
    if not game_state["active"]:
        await interaction.response.send_message("❌ No active game! / Nessuna partita attiva!", ephemeral=True)
        return

    if len(letter) != 1 or not letter.isalpha():
        await interaction.response.send_message("❌ Please provide only one letter! / Fornisci solo una lettera!", ephemeral=True)
        return

    uid = str(interaction.user.id)

    if uid not in game_state["players"]:
        game_state["players"][uid] = {
            "lives": game_state["initial_lives"],
            "eliminated": False
        }

    player = game_state["players"][uid]

    if player["eliminated"]:
        await interaction.response.send_message(
            f"❌ {interaction.user.mention} you are eliminated! Your message doesn't count. / "
            f"sei eliminato! Il tuo messaggio non conta.",
            ephemeral=True
        )
        return

    if game_state["last_player"] == uid:
        await interaction.response.send_message(
            f"⏳ {interaction.user.mention} wait for another player's turn! / aspetta il turno di un altro giocatore!",
            ephemeral=True
        )
        return

    normalized = normalize_text(letter)
    game_state["last_player"] = uid

    # 🔁 REPEATED LETTER
    if normalized in game_state["letters_found"] or normalized in game_state["wrong_letters"]:
        if game_state["lose_points_mode"]:
            add_points_to_player(uid, interaction.user.display_name, -1)
            await interaction.response.send_message(
                f"🔁 {interaction.user.mention} that letter was already said! -1 point 🔴 / "
                f"quella lettera è già stata detta! -1 punto 🔴"
            )
        else:
            player["lives"] -= 1
            
            if player["lives"] <= 0:
                player["eliminated"] = True
                await interaction.response.send_message(
                    f"🔁 {interaction.user.mention} that letter was already said! -1 life ❤️ / "
                    f"quella lettera è già stata detta! -1 vita ❤️\n"
                    f"💀 {interaction.user.mention} has been eliminated! / è stato eliminato!"
                )
            else:
                await interaction.response.send_message(
                    f"🔁 {interaction.user.mention} that letter was already said! -1 life ❤️ / "
                    f"quella lettera è già stata detta! -1 vita ❤️\n"
                    f"Lives remaining / Vite rimanenti: **{player['lives']}**"
                )
        return

    # ✅ CORRECT LETTER
    if normalized in game_state["letters_needed"]:
        game_state["letters_needed"].remove(normalized)
        game_state["letters_found"].add(normalized)
        add_points_to_player(uid, interaction.user.display_name, 1)

        if check_last_letter_win():
            game_state["active"] = False
            add_points_to_player(uid, interaction.user.display_name, 4)

            embed = discord.Embed(
                title="🎉 VICTORY! / VITTORIA! 🎉",
                description=f"**{interaction.user.mention}** found the last letter! / ha trovato l'ultima lettera!",
                color=discord.Color.gold()
            )
            embed.add_field(name="Answer / Risposta", value=f"**{game_state['secret']}**", inline=False)
            embed.add_field(name="Points / Punti", value="+5 🌟", inline=False)

            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("✓", ephemeral=True,)

    # ❌ WRONG LETTER
    else:
        game_state["wrong_letters"].add(normalized)

        if game_state["lose_points_mode"]:
            add_points_to_player(uid, interaction.user.display_name, -1)
            await interaction.response.send_message("✓", ephemeral=True,)
        else:
            player["lives"] -= 1

            if player["lives"] <= 0:
                player["eliminated"] = True
                await interaction.response.send_message(
                    f"💀 {interaction.user.mention} has been eliminated! / è stato eliminato!"
                )
            else:
                await interaction.response.send_message("✓", ephemeral=True,)

@bot.tree.command(name="w", description="Guess the word or phrase / Indovina la parola o frase")
@app_commands.describe(word="The word or phrase / La parola o frase")
async def guess_word(interaction: discord.Interaction, word: str):
    if not game_state["active"]:
        await interaction.response.send_message("❌ No active game! / Nessuna partita attiva!", ephemeral=True)
        return

    uid = str(interaction.user.id)

    if uid not in game_state["players"]:
        game_state["players"][uid] = {
            "lives": game_state["initial_lives"],
            "eliminated": False
        }

    player = game_state["players"][uid]

    if player["eliminated"]:
        await interaction.response.send_message(
            f"❌ {interaction.user.mention} you are eliminated! Your message doesn't count. / "
            f"sei eliminato! Il tuo messaggio non conta.",
            ephemeral=True
        )
        return

    if game_state["last_player"] == uid:
        await interaction.response.send_message(
            f"⏳ {interaction.user.mention} wait for another player's turn! / aspetta il turno di un altro giocatore!",
            ephemeral=True
        )
        return

    game_state["last_player"] = uid

    # ✅ CORRECT WORD
    if normalize_text(word) == game_state["secret_normalized"]:
        game_state["active"] = False
        add_points_to_player(uid, interaction.user.display_name, 5)

        embed = discord.Embed(
            title="🎉 VICTORY! / VITTORIA! 🎉",
            description=f"**{interaction.user.mention}** guessed the phrase! / ha indovinato la frase!",
            color=discord.Color.gold()
        )
        embed.add_field(name="Answer / Risposta", value=f"**{game_state['secret']}**", inline=False)
        embed.add_field(name="Points / Punti", value="+5 🌟", inline=False)

        await interaction.response.send_message(embed=embed)

    # ❌ WRONG WORD
    else:
        if game_state["lose_points_mode"]:
            add_points_to_player(uid, interaction.user.display_name, -1)
            await interaction.response.send_message("✓", ephemeral=True,)
        else:
            player["lives"] -= 1

            if player["lives"] <= 0:
                player["eliminated"] = True
                await interaction.response.send_message(
                    f"💀 {interaction.user.mention} has been eliminated! / è stato eliminato!"
                )
            else:
                await interaction.response.send_message("✓", ephemeral=True,)

@bot.tree.command(name="status", description="View game status (owner only) / Visualizza stato partita (solo proprietario)")
@is_owner()
async def status(interaction: discord.Interaction):
    if not game_state["active"]:
        await interaction.response.send_message("❌ No active game! / Nessuna partita attiva!", ephemeral=True)
        return

    # Patrón con letras adivinadas
    current_pattern = get_current_pattern()
    
    # Estadísticas
    total_letters_said = len(game_state["letters_found"]) + len(game_state["wrong_letters"])
    letters_guessed = len(game_state["letters_found"])
    letters_remaining = len(game_state["letters_needed"])
    
    # Información de jugadores
    players_info = []
    for uid, data in game_state["players"].items():
        try:
            member = await interaction.guild.fetch_member(int(uid))
            name = member.display_name
        except:
            # Buscar en rankings como fallback
            uid_str = str(uid)
            if uid_str in persistent_data["daily_ranking"]:
                name = persistent_data["daily_ranking"][uid_str]["name"]
            elif uid_str in persistent_data["historical_ranking"]:
                name = persistent_data["historical_ranking"][uid_str]["name"]
            else:
                name = "Unknown"
        
        # Obtener puntos del ranking
        points = persistent_data["daily_ranking"].get(str(uid), {}).get("points", 0)
        
        status_emoji = "💀" if data["eliminated"] else "✅"
        players_info.append(
            f"{status_emoji} **{name}**: {data['lives']}❤️ | {points}⭐"
        )
    
    embed = discord.Embed(
        title=f"📊 Game Status - Round {game_state['round_number']}",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🔤 Current Progress / Progresso Attuale",
        value=f"`{current_pattern}`",
        inline=False
    )
    
    embed.add_field(
        name="📈 Statistics / Statistiche",
        value=(
            f"**Letters said / Lettere dette:** {total_letters_said}\n"
            f"**Letters guessed / Lettere indovinate:** {letters_guessed}\n"
            f"**Letters remaining / Lettere mancanti:** {letters_remaining}"
        ),
        inline=False
    )
    
    if players_info:
        embed.add_field(
            name="👥 Players / Giocatori",
            value="\n".join(players_info),
            inline=False
        )
    else:
        embed.add_field(
            name="👥 Players / Giocatori",
            value="No players yet / Ancora nessun giocatore",
            inline=False
        )
    
    mode = "🔴 Points Mode" if game_state["lose_points_mode"] else "❤️ Lives Mode"
    embed.set_footer(text=f"Mode / Modalità: {mode}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="add_lives", description="Add lives to a player / Aggiungi vite a un giocatore")
@app_commands.describe(
    user="The player / Il giocatore",
    lives="Number of lives to add / Numero di vite da aggiungere"
)
@is_owner()
async def add_lives(interaction: discord.Interaction, user: discord.Member, lives: int = 1):
    if not game_state["active"]:
        await interaction.response.send_message("❌ No active game! / Nessuna partita attiva!", ephemeral=True)
        return

    uid = str(user.id)

    if uid not in game_state["players"]:
        game_state["players"][uid] = {
            "lives": game_state["initial_lives"],
            "eliminated": False
        }

    if game_state["players"][uid]["eliminated"]:
        await interaction.response.send_message(
            f"❌ {user.mention} is eliminated and cannot receive lives! / "
            f"{user.mention} è eliminato e non può ricevere vite!",
            ephemeral=True
        )
        return

    game_state["players"][uid]["lives"] += lives

    await interaction.response.send_message(
        f"✅ Added {lives} life/lives to {user.mention}! New total: {game_state['players'][uid]['lives']} ❤️ / "
        f"Aggiunte {lives} vita/vite a {user.mention}! Nuovo totale: {game_state['players'][uid]['lives']} ❤️"
    )

@bot.tree.command(name="add_points", description="Add points to a player / Aggiungi punti a un giocatore")
@app_commands.describe(
    user="The player / Il giocatore",
    points="Number of points to add / Numero di punti da aggiungere"
)
@is_owner()
async def add_points_cmd(interaction: discord.Interaction, user: discord.Member, points: int = 1):
    add_points_to_player(str(user.id), user.display_name, points)
    
    await interaction.response.send_message(
        f"✅ Added {points} point(s) to {user.mention}! / Aggiunti {points} punto/i a {user.mention}!"
    )

@bot.tree.command(name="end_game", description="End current game / Termina partita corrente")
@is_owner()
async def end_game(interaction: discord.Interaction):
    if not game_state["active"]:
        await interaction.response.send_message("❌ No active game! / Nessuna partita attiva!", ephemeral=True)
        return

    secret = game_state["secret"]
    game_state["active"] = False

    await interaction.response.send_message(
        f"🏁 Game ended! The answer was: **{secret}** / Partita terminata! La risposta era: **{secret}**"
    )

@bot.tree.command(name="ranking", description="Show rankings / Mostra classifiche")
@app_commands.describe(type="Ranking type / Tipo di classifica")
@app_commands.choices(type=[
    app_commands.Choice(name="Daily / Giornaliera", value="daily"),
    app_commands.Choice(name="Historical / Storica", value="historical")
])
@is_owner()
async def ranking(interaction: discord.Interaction, type: str = "daily"):
    if type == "daily":
        data = persistent_data["daily_ranking"]
        title = "🏆 Daily Ranking / Classifica Giornaliera 🏆"
    else:
        data = persistent_data["historical_ranking"]
        title = "🏆 Historical Ranking / Classifica Storica 🏆"

    if not data:
        await interaction.response.send_message("📊 No data yet! / Ancora nessun dato!", ephemeral=True)
        return

    sorted_players = sorted(data.items(), key=lambda x: x[1]["points"], reverse=True)[:10]

    embed = discord.Embed(title=title, color=discord.Color.gold())

    ranking_text = ""
    for i, (user_id, player_data) in enumerate(sorted_players, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        ranking_text += f"{medal} **{player_data['name']}** - {player_data['points']} pts\n"

    embed.description = ranking_text if ranking_text else "No players yet / Ancora nessun giocatore"

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="reset_daily", description="Reset daily ranking / Resetta classifica giornaliera")
@is_owner()
async def reset_daily(interaction: discord.Interaction):
    persistent_data["daily_ranking"] = {}
    persistent_data["last_reset"] = datetime.now().date().isoformat()
    save_data()

    await interaction.response.send_message("✅ Daily ranking reset! / Classifica giornaliera resettata!")

@bot.tree.command(name="reset_historical", description="Reset historical ranking / Resetta classifica storica")
@is_owner()
async def reset_historical(interaction: discord.Interaction):
    persistent_data["historical_ranking"] = {}
    save_data()

    await interaction.response.send_message("✅ Historical ranking reset! / Classifica storica resettata!")

@bot.tree.command(name="reset_rounds", description="Reset round counter / Resetta contatore delle ronde")
@is_owner()
async def reset_rounds(interaction: discord.Interaction):
    game_state["round_number"] = 0

    await interaction.response.send_message("✅ Round counter reset to 0! / Contatore delle ronde resettato a 0!")

@bot.tree.command(name="toggle_mode", description="Toggle between lives mode and points mode / Alterna tra modalità vite e punti")
@is_owner()
async def toggle_mode(interaction: discord.Interaction):
    game_state["lose_points_mode"] = not game_state["lose_points_mode"]

    if game_state["lose_points_mode"]:
        mode_text = (
            "🔴 **Points Mode Active** / **Modalità Punti Attiva**\n"
            "Players will lose points for wrong answers instead of lives. / "
            "I giocatori perderanno punti per risposte sbagliate invece di vite."
        )
    else:
        mode_text = (
            "❤️ **Lives Mode Active** / **Modalità Vite Attiva**\n"
            "Players will lose lives for wrong answers. / "
            "I giocatori perderanno vite per risposte sbagliate."
        )

    await interaction.response.send_message(mode_text)

# ================= ERROR HANDLERS =================

@start_game.error
@add_lives.error
@add_points_cmd.error
@end_game.error
@ranking.error
@reset_daily.error
@reset_historical.error
@reset_rounds.error
@toggle_mode.error
@status.error
async def permission_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "❌ Only the server owner can use this command! / Solo il proprietario del server può usare questo comando!",
            ephemeral=True
        )

# ================= TOKEN =================

TOKEN = os.getenv("DISCORD_TOKEN")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ Error: DISCORD_TOKEN not found in environment variables")
        print("Please set the environment variable before running the bot")
        exit(1)
    
    bot.run(TOKEN)