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

app = Flask(__name__)

@app.route('/')
def home():
    return "OK", 200

class TravianBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        # Spustí smyčku reportování
        self.stats_report.start()

    @tasks.loop(hours=12)
    async def stats_report(self):
        await self.wait_until_ready()
        channel = self.get_channel(REPORT_CHANNEL_ID)
        if not channel:
            print(f"Chyba: Kanál s ID {REPORT_CHANNEL_ID} nebyl nalezen.")
            return

        try:
            print("Stahuji a zpracovávám data z Travianu...")
            r = requests.get(SERVER_URL, stream=True, timeout=120)
            r.raise_for_status()
            
            players = {}  # uid: {"name": name, "pop": total_pop}

            for line in r.iter_lines(decode_unicode=True):
                if line and "INSERT INTO" in line:
                    try:
                        # Vyčištění SQL řádku
                        content = line.split("VALUES")[1].strip().strip("();")
                        data = [d.strip().replace("'", "") for d in content.split(",")]
                        
                        # Indexy: 6 = uid, 7 = uname, 10 = populace vesnice
                        uid = data[6]
                        name = data[7]
                        pop = int(data[10])
                        
                        if uid in players:
                            players[uid]['pop'] += pop
                        else:
                            players[uid] = {'name': name, 'pop': pop}
                    except (IndexError, ValueError):
                        continue

            # Výběr TOP 10 podle populace
            top_10 = sorted(players.values(), key=lambda x: x['pop'], reverse=True)[:10]

            embed = discord.Embed(
                title="📊 TOP 10 STATISTIKY - Populace",
                description=f"Aktuální žebříček ze serveru Travian",
                color=discord.Color.green()
            )

            list_text = ""
            for i, p in enumerate(top_10, 1):
                list_text += f"{i}. *{p['name']}* — {p['pop']} pop\n"

            embed.add_field(name="🏰 Hráč — Celková populace", value=list_text or "Žádná data", inline=False)
            embed.set_footer(text=f"Aktualizováno: {time.strftime('%d.%m.%Y %H:%M:%S')}")

            await channel.send(embed=embed)
            print("OK: Report úspěšně odeslán.")

        except Exception as e:
            print(f"Chyba při zpracování: {e}")

    async def on_ready(self):
        print(f"Bot {self.user} běží a monitoruje {SERVER_URL}")

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    # Spuštění Flasku v jiném vlákně
    t = Thread(target=run_web_server, daemon=True)
    t.start()

    # Nastavení intencí a spuštění bota
    intents = discord.Intents.default()
    # Nepotřebujeme číst zprávy (šetříme RAM), jen posílat reporty
    client = TravianBot(intents=intents)

    while True:
        try:
            client.run(TOKEN)
        except Exception as e:
            print(f"Restartování bota za 15s kvůli chybě: {e}")
            time.sleep(15)
