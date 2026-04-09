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

# --- 1. PROVOZ SERVERU ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. KONFIGURACE ---
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1191485630566498344
CHANNEL_NAME = "zpravodaj"
URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'

# --- 3. BOT ---
class TravianBot(discord.Client):
    async def on_ready(self):
        print(f'✅ Bot online: {self.user}')
        if not self.stats_loop.is_running():
            self.stats_loop.start()

    @tasks.loop(minutes=20)
    async def stats_loop(self):
        print("🚀 Startuji sběr dat...")
        players = {}
        try:
            await self.wait_until_ready()
            channel = self.get_channel(REPORT_CHANNEL_ID) or discord.utils.get(self.get_all_channels(), name=CHANNEL_NAME)
            
            if not channel:
                print("❌ Kanál nenalezen.")
                return

            # 1. Mapa
            print("📥 Stahuji mapu...")
            r = requests.get(URL_MAP, stream=True, timeout=60)
            for line in r.iter_lines():
                if line:
                    line = line.decode('utf-8', errors='ignore') # OPRAVA: Převod na text
                    if "INSERT INTO" in line:
                        try:
                            d = [x.strip("'\" ") for x in line.split("VALUES")[1].strip("(); ").split(",")]
                            uid, name, pop = d[6], d[7], int(d[10])
                            if uid in players: players[uid][1] += pop
                            else: players[uid] = [name, pop, 0, 0]
                        except: continue

            # 2. Statistiky
            print("📥 Stahuji statistiky...")
            r = requests.get(URL_STATS, stream=True, timeout=60)
            mode = 0
            for line in r.iter_lines():
                if line:
                    line = line.decode('utf-8', errors='ignore') # OPRAVA: Převod na text
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

            if not players: return

            # 3. Embed
            top_pop = sorted(players.values(), key=lambda x: x[1], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x[2], reverse=True)[:10]
            top_def = sorted(players.values(), key=lambda x: x[3], reverse=True)[:10]

            embed = discord.Embed(title="🏰 TOP STATISTIKY SERVERU", color=0x2ecc71)
            embed.description = f"Aktualizováno: <t:{int(time.time())}:R>"
            
            def fmt(data, idx):
                return "\n".join(f"{i+1}. {p[0]} ({p[idx]})" for i, p in enumerate(data))
            
            embed.add_field(name="🏙️ Populace", value=fmt(top_pop, 1), inline=False)
            embed.add_field(name="⚔️ Off", value=fmt(top_off, 2), inline=True)
            embed.add_field(name="🛡️ Deff", value=fmt(top_def, 3), inline=True)

            await channel.send(embed=embed)
            print("✨ Odesláno!")

        except Exception as e:
            print(f"🔥 Chyba: {e}")
            traceback.print_exc()
        finally:
            players.clear()
            gc.collect()

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    intents = discord.Intents.default()
    intents.guilds = True
    TravianBot(intents=intents).run(TOKEN)
