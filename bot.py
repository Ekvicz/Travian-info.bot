import discord
import requests
import os
import time
import asyncio
import gc
from discord.ext import tasks
from flask import Flask
from threading import Thread

# --- KONFIGURACE ---
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1491485630566498344
URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'

# --- FLASK (Záchrana pro Render) ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- BOT LOGIKA ---
class TravianBot(discord.Client):
    async def on_ready(self):
        print(f"--- BOT ONLINE: {self.user} ---")
        if not self.stats_loop.is_running():
            self.stats_loop.start()

    @tasks.loop(minutes=30)
    async def stats_loop(self):
        print("--- Start smyčky: Stahuji data ---")
        try:
            channel = await self.fetch_channel(REPORT_CHANNEL_ID)
            players = {}

            # Stahování MAPY
            with requests.get(URL_MAP, stream=True, timeout=60) as r:
                for line in r.iter_lines(decode_unicode=True):
                    if line and "INSERT INTO" in line:
                        try:
                            parts = line.split("VALUES")[1].strip("(); ").split(",")
                            uid, name, pop = parts[6].strip("' "), parts[7].strip("' "), int(parts[10].strip("' "))
                            if uid in players: players[uid][1] += pop
                            else: players[uid] = [name, pop, 0, 0]
                        except: continue

            # Stahování STATISTIK
            with requests.get(URL_STATS, stream=True, timeout=60) as r:
                mode = 0
                for line in r.iter_lines(decode_unicode=True):
                    if "x_world_stats_attack" in line: mode = 1
                    elif "x_world_stats_defend" in line: mode = 2
                    if mode > 0 and "INSERT INTO" in line:
                        try:
                            parts = line.split("VALUES")[1].strip("(); ").split(",")
                            uid, pts = parts[0].strip("' "), int(parts[3].strip("' "))
                            if uid in players:
                                if mode == 1: players[uid][2] = pts
                                else: players[uid][3] = pts
                        except: continue

            # Formátování a odeslání
            top_pop = sorted(players.values(), key=lambda x: x[1], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x[2], reverse=True)[:10]
            top_def = sorted(players.values(), key=lambda x: x[3], reverse=True)[:10]

            def fmt(data, idx): return "\n".join(f"{i+1}. {p[0]} ({p[idx]})" for i, p in enumerate(data))

            embed = discord.Embed(title="📊 TOP 10 STATISTIKY SERVERU", color=0x2ecc71)
            embed.description = f"Aktualizováno: <t:{int(time.time())}:R>"
            embed.add_field(name="🏰 Populace", value=fmt(top_pop, 1), inline=False)
            embed.add_field(name="⚔️ Off Body", value=fmt(top_off, 2), inline=True)
            embed.add_field(name="🛡️ Deff Body", value=fmt(top_def, 3), inline=True)

            await channel.send(embed=embed)
            print("--- OK: Zpráva odeslána ---")
            
            # Úklid paměti
            players.clear()
            gc.collect()

        except Exception as e:
            print(f"--- CHYBA: {e} ---")

# --- SPUŠTĚNÍ ---
if __name__ == "__main__":
    # Start webu na pozadí
    Thread(target=run_flask, daemon=True).start()

    # Start Discord bota
    intents = discord.Intents.default()
    intents.message_content = True
    client = TravianBot(intents=intents)
    client.run(TOKEN)
