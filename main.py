import discord
from discord import app_commands
from discord.ext import tasks
import requests
from bs4 import BeautifulSoup
import json
import os
from io import BytesIO

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

try:
    with open("config.json", "r") as f:
        config = json.load(f)
except FileNotFoundError:
    config = {"channels": {}, "bookmarks": []}

def save_config():
    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

def fetch_images(url):
    try:
        if url.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return [url]

        res = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        imgs = []

        for img in soup.find_all("img"):
            src = img.get("src")
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                base = url.split("/")[0] + "//" + url.split("/")[2]
                src = base + src
            imgs.append(src)

        return list(set(imgs))
    except Exception as e:
        print(f"fetch error: {e}")
        return []

async def send_image(channel, url):
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            img_bytes = BytesIO(r.content)
            filename = url.split("/")[-1]
            await channel.send(file=discord.File(img_bytes, filename=filename))
    except Exception as e:
        print(f"image send error: {e}")

# =========================
# スラッシュコマンド
# =========================
@tree.command(name="setup", description="画像送信チャンネルを設定します")
async def setup(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if channel is None:
        channel = interaction.channel
    config["channels"][str(interaction.guild.id)] = channel.id
    save_config()
    await interaction.response.send_message(f"✅ 画像送信チャンネルを {channel.mention} に設定しました！")

@tree.command(name="url", description="指定したURLから全ての画像を送信します（高画質）")
async def url(interaction: discord.Interaction, url: str):
    await interaction.response.defer(thinking=True)
    channel_id = config["channels"].get(str(interaction.guild.id), interaction.channel.id)
    channel = bot.get_channel(channel_id)
    images = fetch_images(url)
    if not images:
        await interaction.followup.send("❌ 画像が見つかりませんでした。")
        return
    await interaction.followup.send(f"📷 {len(images)} 枚の画像を取得しました！送信開始します...")
    for img in images:
        await send_image(channel, img)

@tree.command(name="bookmark", description="URLをブックマークして監視します（高画質）")
async def bookmark(interaction: discord.Interaction, url: str):
    if url not in config["bookmarks"]:
        config["bookmarks"].append(url)
        save_config()
        await interaction.response.send_message(f"✅ {url} をブックマークしました！")
    else:
        await interaction.response.send_message("⚠️ すでに登録済みです。")

# =========================
# ブックマーク監視
# =========================
last_images = {}

@tasks.loop(minutes=2)
async def check_bookmarks():
    for url in config["bookmarks"]:
        new_imgs = fetch_images(url)
        old_imgs = last_images.get(url, [])
        diff = [img for img in new_imgs if img not in old_imgs]

        if diff:
            for guild_id, channel_id in config["channels"].items():
                channel = bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"🆕 {url} で新しい画像を検出しました ({len(diff)} 枚)")
                    for img in diff:
                        await send_image(channel, img)

        last_images[url] = new_imgs

# =========================
# 起動イベント
# =========================
@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot logged in as {bot.user}")
    check_bookmarks.start()

bot.run(TOKEN)
