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

# --- 3. BOT ---
class TravianBot(discord.Client):
    async def on_ready(self):
        print(f'✅ Bot online: {self.user}')
        if not self.stats_loop.is_running():
            self.stats_loop.start()

    @tasks.loop(minutes=20)
    async def stats_loop(self):
        print("🚀 Spouštím hloubkovou analýzu dat (včetně PvE)...")
        # Struktura: [Jméno, Populace, Off, Deff, PvE]
        players = {} 
        
        try:
            await self.wait_until_ready()
            channel = self.get_channel(REPORT_CHANNEL_ID)
            if not channel: return

            # --- A. POPULACE ---
            r_map = requests.get(URL_MAP, timeout=60)
            for line in r_map.iter_lines():
                l = line.decode('utf-8', errors='ignore')
                if "INSERT INTO" in l:
                    try:
                        p = [x.strip("'\" ") for x in l.split("VALUES")[1].strip("(); ").split(",")]
                        uid, name, pop = p[6], p[7], int(p[10])
                        if uid in players: players[uid][1] += pop
                        else: players[uid] = [name, pop, 0, 0, 0]
                    except: continue

            # --- B. STATISTIKY (PvP i PvE) ---
            r_stats = requests.get(URL_STATS, timeout=60)
            mode = 0 # 1=Off, 2=Deff, 3=PvE (Hero/Experience)
            for line in r_stats.iter_lines():
                l = line.decode('utf-8', errors='ignore')
                
                # Detekce sekcí v SQL souboru
                if "x_world_stats_attack" in l: mode = 1
                elif "x_world_stats_defend" in l: mode = 2
                elif "x_world_stats_hero" in l or "x_world_stats_experience" in l: mode = 3
                
                if mode > 0 and "INSERT INTO" in l:
                    try:
                        p = [x.strip("'\" ") for x in l.split("VALUES")[1].strip("(); ").split(",")]
                        uid = p[0]
                        # Zkusíme vytáhnout body (index 3 nebo 2)
                        pts = int(p[3]) if len(p) > 3 and int(p[3]) > 0 else int(p[2])
                        
                        if uid in players:
                            if mode == 1: players[uid][2] = pts # PvP Off
                            if mode == 2: players[uid][3] = pts # PvP Deff
                            if mode == 3: players[uid][4] = pts # PvE / Hero Exp
                    except: continue

            if not players: return

            # --- C. VÝBĚR TOP 10 ---
            t_pop = sorted(players.values(), key=lambda x: x[1], reverse=True)[:10]
            t_off = sorted(players.values(), key=lambda x: x[2], reverse=True)[:10]
            t_def = sorted(players.values(), key=lambda x: x[3], reverse=True)[:10]
            t_pve = sorted(players.values(), key=lambda x: x[4], reverse=True)[:10]

            embed = discord.Embed(title="🏰 KOMPLETNÍ STATISTIKY SERVERU", color=0x3498db)
            embed.description = f"Aktualizováno: <t:{int(time.time())}:R>"
            
            def f(d, i): return "\n".join(f"{idx+1}. *{p[0]}* — {p[i]}" for idx, p in enumerate(d))
            
            embed.add_field(name="🏙️ Populace", value=f(t_pop, 1), inline=False)
            embed.add_field(name="⚔️ PvP Útok (Off)", value=f(t_off, 2), inline=True)
            embed.add_field(name="🛡️ PvP Obrana (Deff)", value=f(t_def, 3), inline=True)
            embed.add_field(name="🦁 PvE (Hrdina/Oázy)", value=f(t_pve, 4), inline=False)
            
            embed.set_footer(text="Travian Automated Intelligence • PvE Enabled")
            
            await channel.send(embed=embed)
            print("✨ Statistiky (včetně PvE) úspěšně odeslány!")

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
    TravianBot(intents=intents).run(TOKEN)
