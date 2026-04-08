import discord
import requests
import os
import time
import io
import asyncio
from flask import Flask
from threading import Thread
from discord.ext import tasks

# ============================== KONFIGURACE ==============================
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1491485630566498344
URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'
# =========================================================================

app = Flask(__name__)

@app.route('/')
def ping():
    return "Bot is alive!", 200

class TravianBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.first_run = True

    async def setup_hook(self):
        # Spustí smyčku hned po startu
        self.stats_report.start()

    @tasks.loop(minutes=30)
    async def stats_report(self):
        await self.wait_until_ready()
        print("--- DEBUG: Smyčka stats_report se právě spustila ---")
        
        if self.first_run:
            print("--- DEBUG: První start - čekám 10 sekund na stabilizaci sítě ---")
            await asyncio.sleep(10)
            self.first_run = False

        channel = self.get_channel(REPORT_CHANNEL_ID)
        
        # Pokud bot kanál nenajde v mezipaměti, zkusí ho načíst přímo z API
        if not channel:
            print(f"--- DEBUG: Kanál {REPORT_CHANNEL_ID} nenalezen v cache, zkouším fetch... ---")
            try:
                channel = await self.fetch_channel(REPORT_CHANNEL_ID)
            except Exception as e:
                print(f"--- CHYBA: Kanál nelze načíst: {e} ---")
                return

        try:
            print("--- DEBUG: Začínám stahovat a zpracovávat data z Travianu ---")
            players = {}

            # 1. ČTENÍ MAPY
            with requests.get(URL_MAP, stream=True, timeout=60) as r:
                for line in r.iter_lines(decode_unicode=True):
                    if line and "INSERT INTO" in line:
                        try:
                            content = line.split("VALUES")[1].strip("(); ")
                            parts = content.split(",")
                            uid = parts[6].strip("' ")
                            name = parts[7].strip("' ")
                            pop = int(parts[10].strip("' "))
                            
                            if uid in players:
                                players[uid]['pop'] += pop
                            else:
                                players[uid] = {'name': name, 'pop': pop, 'off': 0, 'deff': 0}
                        except:
                            continue

            # 2. ČTENÍ STATISTIK
            with requests.get(URL_STATS, stream=True, timeout=60) as r:
                mode = 0
                for line in r.iter_lines(decode_unicode=True):
                    if "x_world_stats_attack" in line: mode = 1
                    elif "x_world_stats_defend" in line: mode = 2
                    
                    if mode > 0 and "INSERT INTO" in line:
                        try:
                            content = line.split("VALUES")[1].strip("(); ")
                            parts = content.split(",")
                            uid = parts[0].strip("' ")
                            points = int(parts[3].strip("' "))
                            
                            if uid in players:
                                if mode == 1: players[uid]['off'] = points
                                else: players[uid]['deff'] = points
                        except:
                            continue

            if not players:
                print("--- DEBUG: Seznam hráčů je prázdný, nebylo co zpracovat ---")
                return

            # 3. FILTRACE TOP 10
            top_pop = sorted(players.values(), key=lambda x: x['pop'], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x['off'], reverse=True)[:10]
            top_deff = sorted(players.values(), key=lambda x: x['deff'], reverse=True)[:10]

            # 4. EMBED (Zpráva)
            embed = discord.Embed(title="📊 TOP 10 STATISTIKY SERVERU", color=0x2ecc71)
            embed.description = f"Aktualizováno: <t:{int(time.time())}:R>"

            def fmt(data, k):
                return "\n".join([f"{i}. *{p['name']}* ({p[k]})" for i, p in enumerate(data, 1)])

            embed.add_field(name="🏰 Populace", value=fmt(top_pop, 'pop'), inline=False)
            embed.add_field(name="⚔️ Off Body", value=fmt(top_off, 'off'), inline=True)
            embed.add_field(name="🛡️ Deff Body", value=fmt(top_deff, 'deff'), inline=True)
            embed.set_footer(text="Zdroj dat: Travian SQL Dump")

            await channel.send(embed=embed)
            print("--- OK: Zpráva byla úspěšně odeslána na Discord! ---")
            
            # Uvolnění paměti
            del players

        except Exception as e:
            print(f"--- CHYBA při zpracování: {e} ---")

def run_web():
    # Render porty
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # Spuštění webu pro Render
    Thread(target=run_web, daemon=True).start()
    
    # Nastavení práv (Intents)
    intents = discord.Intents.default()
    intents.message_content = True
    
    client = TravianBot(intents=intents)
    
    try:
        client.run(TOKEN)
    except Exception as e:
        print(f"--- BOT SE ODPOJIL: {e} ---")
