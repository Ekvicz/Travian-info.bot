import discord
import requests
import os
import time
import io
import asyncio
from flask import Flask
from threading import Thread
from discord.ext import tasks

# ======================== KONFIGURACE ========================
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1491485630566498344
URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'
# =============================================================

app = Flask(__name__) # TADY byla ta chyba - musí tu být __name__

@app.route('/')
def ping():
    return "", 200

class TravianBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.first_run = True

    async def setup_hook(self):
        self.stats_report.start()

    @tasks.loop(minutes=5)
    async def stats_report(self):
        await self.wait_until_ready()
        
        if self.first_run:
            print("Prvni start - cekam na stabilitu...")
            await asyncio.sleep(5)
            self.first_run = False

        channel = self.get_channel(REPORT_CHANNEL_ID)
        if not channel:
            print(f"Chyba: Kanal {REPORT_CHANNEL_ID} nenalezen!")
            return

        try:
            print("Zpracovavam data z Travianu...")
            players = {}

            # 1. ČTENÍ MAPY
            with requests.get(URL_MAP, stream=True, timeout=30) as r:
                for line in r.iter_lines(decode_unicode=True):
                    if line and "INSERT INTO" in line:
                        try:
                            content = line.split("VALUES")[1].strip("(); ")
                            parts = content.split(",")
                            uid = parts[6].strip("' ")
                            name = parts[7].strip("' ")
                            pop = int(parts[10].strip("' "))
                            if uid in players: players[uid]['pop'] += pop
                            else: players[uid] = {'name': name, 'pop': pop, 'off': 0, 'deff': 0}
                        except: continue

            # 2. ČTENÍ STATISTIK
            with requests.get(URL_STATS, stream=True, timeout=30) as r:
                mode = 0 
                for line in r.iter_lines(decode_unicode=True):
                    if "x_world_stats_attack" in line: mode = 1
                    elif "x_world_stats_defend" in line: mode = 2
                    if mode > 0 and "INSERT INTO" in line:
                        try:
                            content = line.split("VALUES")[1].strip("(); ")
                            parts = content.split(",")
                            uid, points = parts[0].strip("' "), int(parts[3].strip("' "))
                            if uid in players:
                                if mode == 1: players[uid]['off'] = points
                                else: players[uid]['deff'] = points
                        except: continue

            if not players: return

            # 3. FILTRACE TOP 10
            top_pop = sorted(players.values(), key=lambda x: x['pop'], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x['off'], reverse=True)[:10]
            top_deff = sorted(players.values(), key=lambda x: x['deff'], reverse=True)[:10]

            # 4. EMBED
            embed = discord.Embed(title="📊 TOP 10 STATISTIKY SERVERU", color=0x2ecc71)
            embed.description = f"Aktualizováno: <t:{int(time.time())}:R>"

            def fmt(data, k): 
                return "\n".join([f"{i}. *{p['name']}* ({p[k]})" for i, p in enumerate(data, 1)])

            embed.add_field(name="🏰 Populace", value=fmt(top_pop, 'pop'), inline=False)
            embed.add_field(name="⚔️ Off Body", value=fmt(top_off, 'off'), inline=True)
            embed.add_field(name="🛡️ Deff Body", value=fmt(top_deff, 'deff'), inline=True)
            embed.set_footer(text="Data: ts1.x1.europe.travian.com")

            await channel.send(embed=embed)
            print("OK: Report odeslan na Discord.")
            del players

        except Exception as e:
            print(f"Chyba pri zpracovani: {e}")

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if _name_ == "_main_":
    Thread(target=run_web, daemon=True).start()
    intents = discord.Intents.default()
    client = TravianBot(intents=intents)
    try:
        client.run(TOKEN)
    except Exception as e:
        print(f"Bot se odpojil: {e}")
