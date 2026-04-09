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

# --- 1. PROVOZ PRO RENDER ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is live and tracking PvE!", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# --- 2. KONFIGURACE ---
TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1191485630566498344
URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'

class TravianBot(discord.Client):
    async def on_ready(self):
        print(f'✅ Bot online: {self.user}')
        if not self.stats_loop.is_running():
            self.stats_loop.start()

    @tasks.loop(minutes=20)
    async def stats_loop(self):
        print("🚀 Spouštím analýzu dat...")
        players = {} 
        
        try:
            await self.wait_until_ready()
            channel = self.get_channel(REPORT_CHANNEL_ID)
            if not channel:
                print(f"❌ Kanál {REPORT_CHANNEL_ID} nenalezen!")
                return

            # --- A. POPULACE (MAP.SQL) ---
            r_map = requests.get(URL_MAP, timeout=60, stream=True)
            for line in r_map.iter_lines():
                if not line: continue
                l = line.decode('utf-8', errors='ignore')
                if "INSERT INTO" in l:
                    try:
                        p = [x.strip("'\" ") for x in l.split("VALUES")[1].strip("(); ").split(",")]
                        # uid=index 6, name=7, pop=10
                        uid, name, pop = p[6], p[7], int(p[10])
                        if uid in players:
                            players[uid][1] += pop
                        else:
                            players[uid] = [name, pop, 0, 0, 0]
                    except: continue

            # --- B. STATISTIKY (STATISTIKEN.SQL) ---
            r_stats = requests.get(URL_STATS, timeout=60, stream=True)
            mode = 0 
            for line in r_stats.iter_lines():
                if not line: continue
                l = line.decode('utf-8', errors='ignore')
                
                if "x_world_stats_attack" in l: mode = 1
                elif "x_world_stats_defend" in l: mode = 2
                elif "x_world_stats_hero" in l or "x_world_stats_experience" in l: mode = 3
                
                if mode > 0 and "INSERT INTO" in l:
                    try:
                        content = l.split("VALUES")[1].strip("(); ")
                        p = [x.strip("'\" ") for x in content.split(",")]
                        uid = p[0]
                        # Body jsou obvykle na indexu 3, u hrdinů to může být index 2 nebo 3 (zkušenosti)
                        pts = int(p[3]) if len(p) > 3 else int(p[2])
                        
                        if uid in players:
                            if mode == 1: players[uid][2] = pts
                            elif mode == 2: players[uid][3] = pts
                            elif mode == 3: players[uid][4] = pts
                    except: continue

            if not players:
                print("⚠️ Žádná data nebyla načtena.")
                return

            # --- C. VÝBĚR TOP 10 ---
            # Filtrujeme pouze ty, co mají v dané kategorii víc než 0, aby žebříček nebyl prázdný
            t_pop = sorted(players.values(), key=lambda x: x[1], reverse=True)[:10]
            t_off = sorted(players.values(), key=lambda x: x[2], reverse=True)[:10]
            t_def = sorted(players.values(), key=lambda x: x[3], reverse=True)[:10]
            t_pve = sorted(players.values(), key=lambda x: x[4], reverse=True)[:10]

            embed = discord.Embed(title="🏰 KOMPLETNÍ STATISTIKY SERVERU", color=0x3498db)
            embed.description = f"Aktualizováno: <t:{int(time.time())}:R>"
            
            def f(d, i):
                res = "\n".join(f"{idx+1}. *{p[0]}* — {p[i]}" for idx, p in enumerate(d) if p[i] > 0)
                return res if res else "Žádná data"
            
            embed.add_field(name="🏙️ Populace", value=f(t_pop, 1), inline=False)
            embed.add_field(name="⚔️ PvP Útok (Off)", value=f(t_off, 2), inline=True)
            embed.add_field(name="🛡️ PvP Obrana (Deff)", value=f(t_def, 3), inline=True)
            embed.add_field(name="🦁 PvE (Hrdina/Zkušenosti)", value=f(t_pve, 4), inline=False)
            
            embed.set_footer(text="Travian Automated Intelligence • PvE Mode")
            
            await channel.send(embed=embed)
            print("✨ Statistiky úspěšně odeslány!")

        except Exception as e:
            print(f"🔥 Chyba: {e}")
            traceback.print_exc()
        finally:
            players.clear()
            gc.collect()

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    intents = discord.Intents.default()
    intents.guilds = True
    # Přidáno kvůli stabilitě na Renderu
    client = TravianBot(intents=intents)
    client.run(TOKEN)
