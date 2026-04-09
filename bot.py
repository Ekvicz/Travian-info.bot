import discord
import requests
import os
import time
import asyncio
import gc
import traceback
from discord.ext import tasks
from flask import Flask
from threading import Thread

# --- 1. ŽIVOTNÍ FUNKCE (Webserver pro Render) ---
app = Flask(__name__)
@app.route('/')
def home(): return "<h1>Travian Inteligence System Online</h1>", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. KONFIGURACE ---
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1191485630566498344
CHANNEL_NAME = "zpravodaj"
URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'

# --- 3. BOT S MAXIMÁLNÍ ODOLNOSTÍ ---
class TravianBot(discord.Client):
    async def on_ready(self):
        print(f'✅ Systém aktivován: {self.user}')
        if not self.stats_loop.is_running():
            self.stats_loop.start()

    @tasks.loop(minutes=20)
    async def stats_loop(self):
        print("🚀 Spouštím sběr dat z fronty...")
        players = {} # Inicializace hned na startu (prevence UnboundLocalError)
        
        try:
            # POJISTKA: Počkáme, až se bot plně synchronizuje s Discordem
            await self.wait_until_ready()
            
            # HLEDÁNÍ KANÁLU: Pokud selže ID, bot prohledá jména
            channel = self.get_channel(REPORT_CHANNEL_ID)
            if not channel:
                for guild in self.guilds:
                    for ch in guild.text_channels:
                        if ch.name == CHANNEL_NAME:
                            channel = ch
                            break
            
            if not channel:
                print("❌ KRITICKÁ CHYBA: Kanál nebyl nalezen. Prověřte oprávnění bota.")
                return

            # STAHOVÁNÍ MAPY (Populace)
            print("📥 Stahuji mapu...")
            with requests.get(URL_MAP, stream=True, timeout=60) as r:
                for line in r.iter_lines(decode_unicode=True):
                    if line and "INSERT INTO" in line:
                        try:
                            # Čisté parsování SQL dat
                            d = [x.strip("'\" ") for x in line.split("VALUES")[1].strip("(); ").split(",")]
                            uid, name, pop = d[6], d[7], int(d[10])
                            if uid in players: players[uid][1] += pop
                            else: players[uid] = [name, pop, 0, 0]
                        except: continue

            await asyncio.sleep(1) # Krátká pauza pro stabilitu paměti

            # STAHOVÁNÍ STATISTIK (Útok/Obrana)
            print("📥 Stahuji statistiky...")
            with requests.get(URL_STATS, stream=True, timeout=60) as r:
                mode = 0
                for line in r.iter_lines(decode_unicode=True):
                    if "x_world_stats_attack" in line: mode = 1
                    elif "x_world_stats_defend" in line: mode = 2
                    if mode > 0 and "INSERT INTO" in line:
                        try:
                            d = [x.strip("'\" ") for x in line.split("VALUES")[1].strip("(); ").split(",")]
                            uid, pts = d[0], int(d[3])
                            if uid in players:
                                if mode == 1: players[uid][2] = pts
                                if mode == 2: players[uid][3] = pts
                        except: continue

            if not players:
                print("⚠️ Žádná data k parsování.")
                return

            # GENERAVÁNÍ TOP 10
            top_pop = sorted(players.values(), key=lambda x: x[1], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x[2], reverse=True)[:10]
            top_def = sorted(players.values(), key=lambda x: x[3], reverse=True)[:10]

            embed = discord.Embed(
                title="🏰 ELITNÍ STATISTIKY SERVERU",
                description=f"Aktualizace bitevního pole.\nZasloužená sláva pro nejlepší.\n\nUpdate: <t:{int(time.time())}:R>",
                color=0x2ecc71
            )
            
            def format_row(data, idx):
                rows = []
                for i, p in enumerate(data):
                    medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"*{i+1}.*"
                    rows.append(f"{medal} {p[0]} — {p[idx]}")
                return "\n".join(rows) if rows else "Žádná data"

            embed.add_field(name="🏙️ Populace", value=format_row(top_pop, 1), inline=False)
            embed.add_field(name="⚔️ Útok (Off)", value=format_row(top_off, 2), inline=True)
            embed.add_field(name="🛡️ Obrana (Deff)", value=format_row(top_def, 3), inline=True)
            
            # Pokud má bot avatar, přidáme ho do patičky
            icon = self.user.avatar.url if self.user.avatar else None
            embed.set_footer(text="Travian Automated Intelligence", icon_url=icon)

            await channel.send(embed=embed)
            print("✨ Statistiky doručeny na Discord.")

        except Exception as e:
            print(f"🔥 SYSTÉMOVÁ CHYBA: {e}")
            traceback.print_exc()
        finally:
            players.clear()
            gc.collect() # Násilné uvolnění paměti (pro Render nutnost)

# --- 4. SPUŠTĚNÍ ---
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    
    bot = TravianBot(intents=intents)
    bot.run(TOKEN)
