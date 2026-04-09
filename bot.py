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

# --- 1. WEBSERVER PRO RENDER (Keep-alive) ---
app = Flask(__name__)

@app.route('/')
def ping():
    return "Bot is alive!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. KONFIGURACE ---
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1191485630566498344 # ID tvého kanálu
URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'

# --- 3. BOT LOGIKA ---
class TravianBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_ready(self):
        print(f'--- BOT PŘIHLÁŠEN: {self.user} ---')
        if not self.stats_loop.is_running():
            self.stats_loop.start()

    @tasks.loop(minutes=20)
    async def stats_loop(self):
        print("--- DEBUG: Začínám zpracování dat ---")
        channel = self.get_channel(REPORT_CHANNEL_ID)
        if not channel:
            print("CHYBA: Kanál nebyl nalezen!")
            return

        players = {}

        try:
            # Stahování Mapy (Populace)
            r = requests.get(URL_MAP, stream=True, timeout=60)
            for line in r.iter_lines(decode_unicode=True):
                if line and "INSERT INTO" in line and "VALUES" in line:
                    try:
                        data_part = line.split("VALUES")[1].strip("();").split(",")
                        uid = data_part[6].strip("'\" ")
                        name = data_part[7].strip("'\" ")
                        pop = int(data_part[10].strip("'\" "))

                        if uid in players:
                            players[uid][1] += pop
                        else:
                            players[uid] = [name, pop, 0, 0]
                    except (IndexError, ValueError):
                        continue

            # Stahování Statistik (Útok / Obrana)
            r = requests.get(URL_STATS, stream=True, timeout=60)
            mode = 0
            for line in r.iter_lines(decode_unicode=True):
                if "x_world_stats_attack" in line: mode = 1
                elif "x_world_stats_defend" in line: mode = 2
                
                if mode > 0 and "INSERT INTO" in line and "VALUES" in line:
                    try:
                        parts = line.split("VALUES")[1].strip("();").split(",")
                        uid = parts[0].strip("'\" ")
                        pts = int(parts[3].strip("'\" "))

                        if uid in players:
                            if mode == 1: players[uid][2] = pts
                            if mode == 2: players[uid][3] = pts
                    except (IndexError, ValueError):
                        continue

            # Výběr TOP 10
            top_pop = sorted(players.values(), key=lambda x: x[1], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x[2], reverse=True)[:10]
            top_def = sorted(players.values(), key=lambda x: x[3], reverse=True)[:10]

            def fmt(data, idx):
                return "\n".join(f"{i+1}. {p[0]} ({p[idx]})" for i, p in enumerate(data))

            embed = discord.Embed(title="📊 TOP 10 STATISTIKY SERVERU", color=0x2ecc71)
            embed.description = f"Aktualizováno: <t:{int(time.time())}:R>"
            embed.add_field(name="🏰 Populace", value=fmt(top_pop, 1), inline=False)
            embed.add_field(name="⚔️ Off Body", value=fmt(top_off, 2), inline=True)
            embed.add_field(name="🛡️ Deff Body", value=fmt(top_def, 3), inline=True)

            await channel.send(embed=embed)
            print("--- OK: Zpráva odeslána ---")

        except Exception as e:
            err = traceback.format_exc()
            print(f"--- KRITICKÁ CHYBA VE SMYČCE ---\n{err}")
            await channel.send(f"⚠️ *Chyba při zpracování dat:* {str(e)}")

        finally:
            players.clear()
            gc.collect()

# --- 4. SPUŠTĚNÍ ---
if __name__ == "__main__":
    # Spuštění Flasku v jiném vlákně
    Thread(target=run_flask, daemon=True).start()

    # Nastavení Discord bota
    intents = discord.Intents.default()
    intents.message_content = True
    
    client = TravianBot(intents=intents)
    client.run(TOKEN)
