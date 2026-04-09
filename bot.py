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
REPORT_CHANNEL_ID = 1191485630566498344
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
        print("--- DEBUG: START SMYČKY ---")
        try:
            # Získání kanálu přes API (fetch je jistota při startu)
            channel = await self.fetch_channel(REPORT_CHANNEL_ID)
            print(f"--- DEBUG: Kanál nalezen: {channel.name} ---")

            players = {}

            # 1. Stahování Mapy (Populace)
            print("--- DEBUG: Stahuji mapu ---")
            with requests.get(URL_MAP, stream=True, timeout=60) as r:
                for line in r.iter_lines(decode_unicode=True):
                    if line and "INSERT INTO" in line and "VALUES" in line:
                        try:
                            content = line.split("VALUES")[1].strip("(); ")
                            parts = [p.strip("'\" ") for p in content.split(",")]
                            uid = parts[6]
                            name = parts[7]
                            pop = int(parts[10])

                            if uid in players:
                                players[uid][1] += pop
                            else:
                                players[uid] = [name, pop, 0, 0]
                        except:
                            continue
            
            await asyncio.sleep(1) # Pauza pro stabilitu

            # 2. Stahování Statistik (Útok / Obrana)
            print("--- DEBUG: Stahuji statistiky ---")
            with requests.get(URL_STATS, stream=True, timeout=60) as r:
                mode = 0
                for line in r.iter_lines(decode_unicode=True):
                    if "x_world_stats_attack" in line: mode = 1
                    elif "x_world_stats_defend" in line: mode = 2
                    
                    if mode > 0 and "INSERT INTO" in line and "VALUES" in line:
                        try:
                            content = line.split("VALUES")[1].strip("(); ")
                            parts = [p.strip("'\" ") for p in content.split(",")]
                            uid = parts[0]
                            pts = int(parts[3])

                            if uid in players:
                                if mode == 1: players[uid][2] = pts
                                if mode == 2: players[uid][3] = pts
                        except:
                            continue

            if not players:
                print("--- VAROVÁNÍ: Žádná data nebyla načtena ---")
                return

            # 3. Výběr TOP 10
            print("--- DEBUG: Generuji embed ---")
            top_pop = sorted(players.values(), key=lambda x: x[1], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x[2], reverse=True)[:10]
            top_def = sorted(players.values(), key=lambda x: x[3], reverse=True)[:10]

            def fmt(data, idx):
                res = "\n".join(f"{i+1}. {p[0]} ({p[idx]})" for i, p in enumerate(data))
                return res if res else "Žádná data"

            embed = discord.Embed(title="📊 TOP 10 STATISTIKY SERVERU", color=0x2ecc71)
            embed.description = f"Aktualizováno: <t:{int(time.time())}:R>"
            embed.add_field(name="🏰 Populace", value=fmt(top_pop, 1), inline=False)
            embed.add_field(name="⚔️ Off Body", value=fmt(top_off, 2), inline=True)
            embed.add_field(name="🛡️ Deff Body", value=fmt(top_def, 3), inline=True)

            await channel.send(embed=embed)
            print("--- HOTOVO: Zpráva odeslána ---")

        except Exception as e:
            print(f"--- KRITICKÁ CHYBA: {e} ---")
            traceback.print_exc()

        finally:
            players.clear()
            gc.collect()

# --- 4. SPUŠTĚNÍ ---
if __name__ == "__main__":
    # Spuštění Flasku
    Thread(target=run_flask, daemon=True).start()

    # Nastavení bota
    intents = discord.Intents.default()
    # Následující řádek je nutný, pokud by bot měl číst zprávy, 
    # pro odesílání statistik technicky stačí default, ale necháme ho tam.
    intents.message_content = True 
    
    client = TravianBot(intents=intents)
    client.run(TOKEN)
