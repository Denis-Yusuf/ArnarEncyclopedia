import discord
import random

TOKEN = 'MTE3NjM2NjAyMTY5NTc4Mjk0Mg.G79yvN.Im3p2AJawpQY7e36X2FE-kcC8wCGPYJztRjZjY'
QUOTES_FILE = 'Arnar_Encyclopedia.txt'

intents = intents=discord.Intents.default()
intents.message_content = True

client = discord.Client(intents = intents)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!egg'):
        quote = get_random_quote()
        await message.channel.send(quote)

def get_random_quote():
    with open(QUOTES_FILE, 'r', encoding='utf-8') as file:
        quotes = file.readlines()
    return random.choice(quotes)

client.run(TOKEN)