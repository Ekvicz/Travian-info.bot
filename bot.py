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

# --- 1. PROVOZ PRO RENDER ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is online!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. KONFIGURACE ---
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1191485630566498344
CHANNEL_NAME = "zpravodaj"
URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'

# --- 3. BOT LOGIKA ---
class TravianBot(discord.Client):
    async def on_ready(self):
        print(f'✅ Bot prihlasen jako: {self.user}')
        if not self.stats_loop.is_running():
            self.stats_loop.start()

    @tasks.loop(minutes=20)
    async def stats_loop(self):
        print("🚀 Startuji aktualizaci dat...")
        players = {}
        try:
            await self.wait_until_ready()
            # Pokus o ziskani kanalu
            channel = self.get_channel(REPORT_CHANNEL_ID)
            if not channel:
                channel = discord.utils.get(self.get_all_channels(), name=CHANNEL_NAME)
            
            if not channel:
                print("❌ Kanal nenalezen!")
                return

            # 📥 1. STAHUJI MAPU (Populace)
            print("📥 Stahuji mapu...")
            r_map = requests.get(URL_MAP, stream=True, timeout=60)
            for line in r_map.iter_lines():
                if line:
                    # TADY JE TA OPRAVA: Prevod bytes na str
                    line_str = line.decode('utf-8', errors='ignore')
                    if "INSERT INTO" in line_str and "VALUES" in line_str:
                        try:
                            content = line_str.split("VALUES")[1].strip("(); ")
                            p = [x.strip("'\" ") for x in content.split(",")]
                            uid, name, pop = p[6], p[7], int(p[10])
                            if uid in players: players[uid][1] += pop
                            else: players[uid] = [name, pop, 0, 0]
                        except: continue

            await asyncio.sleep(1)

            # 📥 2. STAHUJI STATISTIKY (Utok/Obrana)
            print("📥 Stahuji statistiky...")
            r_stats = requests.get(URL_STATS, stream=True, timeout=60)
            mode = 0
            for line in r_stats.iter_lines():
                if line:
                    line_str = line.decode('utf-8', errors='ignore')
                    if "x_world_stats_attack" in line_str: mode = 1
                    elif "x_world_stats_defend" in line_str: mode = 2
                    
                    if mode > 0 and "INSERT INTO" in line_str:
                        try:
                            content = line_str.split("VALUES")[1].strip("(); ")
                            p = [x.strip("'\" ") for x in content.split(",")]
                            uid, pts = p[0], int(p[3])
                            if uid in players:
                                if mode == 1: players[uid][2] = pts
                                if mode == 2: players[uid][3] = pts
                        except: continue

            if not players:
                print("⚠️ Zadna data.")
                return

            # 📊 3. POSILANI NA DISCORD
            print("📊 Generuji TOP 10...")
            top_pop = sorted(players.values(), key=lambda x: x[1], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x[2], reverse=True)[:10]
            top_def = sorted(players.values(), key=lambda x: x[3], reverse=True)[:10]

            embed = discord.Embed(title="📊 TOP 10 STATISTIKY SERVERU", color=0x2ecc71)
            embed.description = f"Aktualizováno: <t:{int(time.time())}:R>"
            
            def fmt(data, idx):
                res = "\n".join(f"{i+1}. {p[0]} ({p[idx]})" for i, p in enumerate(data))
                return res if res else "Zadna data"

            embed.add_field(name="🏰 Populace", value=fmt(top_pop, 1), inline=False)
            embed.add_field(name="⚔️ Off Body", value=fmt(top_off, 2), inline=True)
            embed.add_field(name="🛡️ Deff Body", value=fmt(top_def, 3), inline=True)

            await channel.send(embed=embed)
            print("✨ OK: Zprava odeslana!")

        except Exception as e:
            print(f"🔥 CHYBA: {e}")
            traceback.print_exc()
        finally:
            players.clear()
            gc.collect()

# --- 4. SPUSTENI ---
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    intents = discord.Intents.default()
    intents.guilds = True
    client = TravianBot(intents=intents)
    client.run(TOKEN)
