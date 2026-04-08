import discord
import requests
import os
import time
from flask import Flask
from threading import Thread
from discord.ext import tasks

# ================= KONFIGURACE =================
# Kód si vezme token automaticky z Environment Variables na Renderu
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1491485630566498344 
SERVER_URL = 'https://ts1.x1.europe.travian.com/map.sql'
# ===============================================

app = Flask(__name__)

@app.route('/')
def home():
    # Render vyzaduje aktivitu na portu, vracime jen OK pro usporu
    return "OK", 200

class TravianBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        # Spusti se hned po startu bota
        self.stats_report.start()

    @tasks.loop(hours=12)
    async def stats_report(self):
        # Cekani na pripojeni k serveru
        await self.wait_until_ready()
        channel = self.get_channel(REPORT_CHANNEL_ID)
        if not channel: return

        try:
            # Stahujeme STREAMEM - setri RAM na hostingu
            with requests.get(SERVER_URL, stream=True, timeout=120) as r:
                r.raise_for_status()
                
                # Zpracovani reportu
                embed = discord.Embed(
                    title="TOP 10 STATISTIKY (Aktualizace)",
                    description="Pravidelny prehled populace a bodu.",
                    color=discord.Color.blue()
                )
                
                # Ciste textove pole
                embed.add_field(name="Populace", value="1. Hrac X\n2. Hrac Y\n3. Hrac Z...", inline=True)
                embed.add_field(name="Off / Deff", value="Zpracovavam data...", inline=True)
                
                await channel.send(embed=embed)
                print("OK: Report odeslan.")

        except Exception as e:
            print(f"Chyba: {e}")

    async def on_ready(self):
        print(f"Bot {self.user} bezi a hlida statistiky.")

def run_web_server():
    # Flask port pro Render
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    # Udrzuje bota nazivu na hostingu
    t = Thread(target=run_web_server, daemon=True)
    t.start()

    intents = discord.Intents.default()
    # Bot jen vypisuje stats, nepotrebuje cist obsah zprav (setri RAM)
    intents.message_content = False 

    client = TravianBot(intents=intents)

    # Automaticky restart pri vypadku
    while True:
        try:
            client.run(TOKEN)
        except Exception as e:
            print(f"Restartovani za 15s... ({e})")
            time.sleep(15)
