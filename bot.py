import discord
import requests
import os
import time
from flask import Flask
from threading import Thread
from discord.ext import tasks

# ======================== KONFIGURACE ========================
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1491485630566498344
URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'
# =============================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "OK", 200

class TravianBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        self.stats_report.start()

    @tasks.loop(minutes=10)
    async def stats_report(self):
        await self.wait_until_ready()
        channel = self.get_channel(REPORT_CHANNEL_ID)
        if not channel: return

        try:
            print("Zpracovavam data (10 min interval)...")
            players = {} 

            # 1. POPULACE
            r_map = requests.get(URL_MAP, stream=True, timeout=120)
            for line in r_map.iter_lines(decode_unicode=True):
                if line and "INSERT INTO" in line:
                    try:
                        content = line.split("VALUES")[1].strip().strip("();")
                        data = [d.strip().replace("'", "") for d in content.split(",")]
                        uid, name, pop = data[6], data[7], int(data[10])
                        if uid in players:
                            players[uid]['pop'] += pop
                        else:
                            players[uid] = {'name': name, 'pop': pop, 'off': 0, 'deff': 0}
                    except: continue

            # 2. OFF/DEFF BODY
            r_stats = requests.get(URL_STATS, stream=True, timeout=120)
            current_type = None 
            for line in r_stats.iter_lines(decode_unicode=True):
                if "x_world_stats_attack" in line: current_type = 1
                elif "x_world_stats_defend" in line: current_type = 2
                
                if line and "INSERT INTO" in line and current_type:
                    try:
                        content = line.split("VALUES")[1].strip().strip("();")
                        data = [d.strip().replace("'", "") for d in content.split(",")]
                        uid, points = data[0], int(data[3])
                        if uid in players:
                            if current_type == 1: players[uid]['off'] = points
                            else: players[uid]['deff'] = points
                    except: continue

            # 3. FILTROVANI TOP 10
            top_pop = sorted(players.values(), key=lambda x: x['pop'], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x['off'], reverse=True)[:10]
            top_deff = sorted(players.values(), key=lambda x: x['deff'], reverse=True)[:10]

            # 4. EMBED ZPRAVA
            embed = discord.Embed(title="TOP 10 STATISTIKY SERVERU", color=discord.Color.blue())
            
            p_list = ""
            for i, p in enumerate(top_pop, 1):
                p_list += f"{i}. {p['name']} - {p['pop']}\n"
            embed.add_field(name="Populace", value=p_list or "Nenalezeno", inline=False)

            o_list = ""
            for i, p in enumerate(top_off, 1):
                o_list += f"{i}. {p['name']} ({p['off']})\n"
            embed.add_field(name="Off Body", value=o_list or "Nenalezeno", inline=True)

            d_list = ""
            for i, p in enumerate(top_deff, 1):
                d_list += f"{i}. {p['name']} ({p['deff']})\n"
            embed.add_field(name="Deff Body", value=d_list or "Nenalezeno", inline=True)
            
            embed.set_footer(text=f"Posledni update: {time.strftime('%H:%M:%S')}")
            await channel.send(embed=embed)
            print("OK: Report odeslan")

            # Uvolneni pameti
            players.clear()

        except Exception as e:
            print(f"Chyba: {e}")

    async def on_ready(self):
        print(f"Bot {self.user} je online")

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_web_server, daemon=True).start()
    intents = discord.Intents.default()
    client = TravianBot(intents=intents)
    while True:
        try: client.run(TOKEN)
        except: time.sleep(15)
