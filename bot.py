import discord
import requests
import os
import time
import asyncio
from discord.ext import tasks

TOKEN = os.environ.get('DISCORD_TOKEN')
REPORT_CHANNEL_ID = 1491485630566498344

URL_MAP = 'https://ts1.x1.europe.travian.com/map.sql'
URL_STATS = 'https://ts1.x1.europe.travian.com/statistiken.sql'


class TravianBot(discord.Client):
    async def on_ready(self):
        print("Bot ready")
        print(f"Logged as {self.user}")

        try:
            channel = await self.fetch_channel(REPORT_CHANNEL_ID)
            await channel.send("Bot start")
        except Exception as e:
            print(f"Channel error: {e}")

        if not self.stats_loop.is_running():
            self.stats_loop.start()

    @tasks.loop(minutes=10)
    async def stats_loop(self):
        print("Loop start")

        try:
            channel = await self.fetch_channel(REPORT_CHANNEL_ID)
        except Exception as e:
            print(f"Channel fetch error: {e}")
            return

        players = {}

        try:
            # MAPA (POPULACE)
            with requests.get(URL_MAP, stream=True, timeout=30) as r:
                for line in r.iter_lines(decode_unicode=True):
                    if not line or "INSERT INTO" not in line:
                        continue

                    try:
                        parts = line.split("VALUES")[1].strip("(); ").split(",")

                        uid = parts[6].strip("' ")
                        name = parts[7].strip("' ")
                        pop = int(parts[10].strip("' "))

                        if uid in players:
                            players[uid][1] += pop
                        else:
                            players[uid] = [name, pop, 0, 0]

                    except:
                        continue

            # STATISTIKY
            with requests.get(URL_STATS, stream=True, timeout=30) as r:
                mode = 0

                for line in r.iter_lines(decode_unicode=True):
                    if "x_world_stats_attack" in line:
                        mode = 1
                        continue
                    elif "x_world_stats_defend" in line:
                        mode = 2
                        continue

                    if mode == 0 or "INSERT INTO" not in line:
                        continue

                    try:
                        parts = line.split("VALUES")[1].strip("(); ").split(",")

                        uid = parts[0].strip("' ")
                        points = int(parts[3].strip("' "))

                        if uid in players:
                            if mode == 1:
                                players[uid][2] = points
                            else:
                                players[uid][3] = points

                    except:
                        continue

            if not players:
                await channel.send("No data")
                return

            # TOP 10 (bez zbytečných kopií)
            top_pop = sorted(players.values(), key=lambda x: x[1], reverse=True)[:10]
            top_off = sorted(players.values(), key=lambda x: x[2], reverse=True)[:10]
            top_def = sorted(players.values(), key=lambda x: x[3], reverse=True)[:10]

            def format_list(data, index):
                return "\n".join(
                    f"{i+1}. {p[0]} ({p[index]})"
                    for i, p in enumerate(data)
                )

            embed = discord.Embed(
                title="TOP 10 STATISTIKY",
                color=0x00ff00
            )

            embed.description = f"Update: <t:{int(time.time())}:R>"

            embed.add_field(name="Populace", value=format_list(top_pop, 1), inline=False)
            embed.add_field(name="Off", value=format_list(top_off, 2), inline=True)
            embed.add_field(name="Def", value=format_list(top_def, 3), inline=True)

            await channel.send(embed=embed)
            print("Sent")

            # Uvolnění paměti
            players.clear()
            del players

        except Exception as e:
            print(f"Error: {e}")
            try:
                await channel.send("Error during processing")
            except:
                pass


if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True

    client = TravianBot(intents=intents)

    if not TOKEN:
        print("Missing token")
    else:
        client.run(TOKEN)
