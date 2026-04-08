import discord
import requests
import os
import time
import io
from flask import Flask
from threading import Thread
from discord.ext import tasks

# ======================== KONFIGURACE ========================
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1491485630566498344

# Oficiální SQL exporty pro ts1.x1.europe
URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'
# =============================================================

app = Flask(__name__)

@app.route('/')
def ping():
    return "Bot is alive", 200

class TravianBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.first_run = True

    async def setup_hook(self):
        self.stats_report.start()

    @tasks.loop(minutes=5)
    async def stats_report(self):
        await self.wait_until_ready()
        
        # Při úplně prvním startu chvíli počkáme na stabilitu připojení
        if self.first_run:
            await asyncio.sleep(5) 
            self.first_run = False

        channel = self.get_channel(REPORT_CHANNEL_ID)
        if not channel:
            print(f"Chyba: Kanal {REPORT_CHANNEL_ID} nenalezen!")
            return

        try:
            print("--- Zahajuji stahování dat z Travianu ---")
            players = {}

            # 1. ČTENÍ MAPY (Jména a Populace)
            with requests.get(URL_MAP, stream=True, timeout=30) as r:
                for line in r.iter_lines(decode_unicode=True):
                    if line and "INSERT INTO" in line:
                        try:
                            # Čistíme data: uid(6), name(7), pop(10)
                            parts = line.split("VALUES")[1].strip("(); ").split(",")
                            uid = parts[6].strip("' ")
                            name = parts[7].strip("' ")
                            pop = int(parts[10].strip("' "))
                            
                            if uid in players:
                                players[uid]['pop'] += pop
                            else:
                                players[uid] = {'name': name, 'pop': pop, 'off': 0, 'deff': 0}
                        except: continue

            # 2. ČTENÍ STATISTIK (Off a Deff body)
            with requests.get(URL_STATS, stream=True, timeout=30) as r:
                mode = 0 # 1=off, 2=deff
                for line in r.iter_lines(decode_unicode=True):
                    if "x_world_stats_attack" in line: mode = 1
                    elif "x_world_stats_defend" in line: mode = 2
                    
                    if mode > 0 and "INSERT INTO" in line:
                        try:
                            parts = line.split("VALUES")[1].strip("(); ").split(",")
                            uid = parts[0].strip("' ")
                            points = int(parts[3].strip("' "))
                            if uid in players:
                                if mode == 1: players[uid]['off'] = points
                                else: players[uid]['deff'] = points
                        except: continue

            if not players:
                print("Varování: Žádná data nebyla načtena.")
                return

            # 3. FILTRACE TOP 10
            top_pop = sorted(players.values(), key=lambda x: x['pop'], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x['off'], reverse=True)[:10]
            top_deff = sorted(players.values(), key=lambda x: x['deff'], reverse=True)[:10]

            # 4. TVORBA EMBEDU
            embed = discord.Embed(
                title="🏆 TOP 10 STATISTIKY SERVERU",
                color=0x2ecc71, # Krásná zelená
                description=f"Aktualizováno: <t:{int(time.time())}:R>"
            )

            def format_list(data, key):
                return "\n".join([f"{i:2}. *{p['name']}* ({p[key]})" for i, p in enumerate(data, 1)])

            embed.add_field(name="🏰 Největší populace", value=format_list(top_pop, 'pop'), inline=False)
            embed.add_field(name="⚔️ Útočníci (Off)", value=format_list(top_off, 'off'), inline=True)
            embed.add_field(name="🛡️ Obránci (Deff)", value=format_list(top_deff, 'deff'), inline=True)
            
            embed.set_footer(text="Data: ts1.x1.europe.travian.com")

            await channel.send(embed=embed)
            print("Vše OK: Report odeslán.")
            
            # Vyčištění paměti pro free hosting
            del players

        except Exception as e:
            print(f"Kritická chyba: {e}")

import asyncio
def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if _name_ == "_main_":
    # Start webu pro cron-job
    Thread(target=run_web, daemon=True).start()
    
    # Start bota
    intents = discord.Intents.default()
    client = TravianBot(intents=intents)
    
    try:
        client.run(TOKEN)
    except Exception as e:
        print(f"Bot se odpojil: {e}")
