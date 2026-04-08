import discord
import requests
import os
import time
import asyncio
from flask import Flask
from threading import Thread
from discord.ext import tasks

# ======================== KONFIGURACE ========================
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1491485630566498344
SERVER_URL = 'https://ts1.x1.europe.travian.com/map.sql'
# =============================================================

app = Flask(_name_)

@app.route('/')
def home():
    # Vraci pouze OK pro minimalni vyuziti RAM a udrzeni bota na Renderu pres Cron-job
    return "OK", 200

class TravianBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        # Spusti automatickou smycku
        self.stats_report.start()

    @tasks.loop(hours=12)
    async def stats_report(self):
        await self.wait_until_ready()
        channel = self.get_channel(REPORT_CHANNEL_ID)
        if not channel:
            print(f"Chyba: Kanal {REPORT_CHANNEL_ID} nenalezen")
            return

        try:
            print("Stahovani a zpracovani dat...")
            # stream=True zajisti, ze se soubor nestahne cely do RAM najednou
            r = requests.get(SERVER_URL, stream=True, timeout=120)
            r.raise_for_status()
            
            players = {}  # uid: {"name": name, "pop": total_pop}

            for line in r.iter_lines(decode_unicode=True):
                if line and "INSERT INTO" in line:
                    try:
                        # Rozdeleni SQL radku
                        content = line.split("VALUES")[1].strip().strip("();")
                        data = [d.strip().replace("'", "") for d in content.split(",")]
                        
                        # Indexy: 6 = uid, 7 = uname, 10 = populace
                        uid = data[6]
                        name = data[7]
                        pop = int(data[10])
                        
                        if uid in players:
                            players[uid]['pop'] += pop
                        else:
                            players[uid] = {'name': name, 'pop': pop}
                    except (IndexError, ValueError):
                        continue

            # Serazeni TOP 10 hracu podle populace
            top_10 = sorted(players.values(), key=lambda x: x['pop'], reverse=True)[:10]

            embed = discord.Embed(
                title="TOP 10 STATISTIKY - Populace",
                description="Zebricek hracu podle celkove populace",
                color=discord.Color.blue()
            )

            list_text = ""
            for i, p in enumerate(top_10, 1):
                list_text += f"{i}. {p['name']} - {p['pop']} pop\n"

            embed.add_field(name="Hrac - Celkova populace", value=list_text or "Zadna data", inline=False)
            embed.set_footer(text=f"Aktualizace: {time.strftime('%d.%m.%Y %H:%M:%S')}")

            await channel.send(embed=embed)
            print("OK: Report odeslan")

        except Exception as e:
            print(f"Chyba pri zpracovani: {e}")

    async def on_ready(self):
        print(f"Bot {self.user} je online")

def run_web_server():
    # Server pro Render/Cron-job na portu 8080
    app.run(host='0.0.0.0', port=8080)

if _name_ == "_main_":
    # Flask bezi v samostatnem vlakne
    t = Thread(target=run_web_server, daemon=True)
    t.start()

    intents = discord.Intents.default()
    # Zakazani cteni obsahu zprav pro usporu RAM (bot jen posila statistiky)
    intents.message_content = False
    
    client = TravianBot(intents=intents)

    while True:
        try:
            client.run(TOKEN)
        except Exception as e:
            print(f"Restart za 15s: {e}")
            time.sleep(15)
